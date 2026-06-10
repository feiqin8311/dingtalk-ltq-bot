#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
钉钉物流查询机器人
接收FBA编号，查询钉钉表格并回复物流信息
"""

import asyncio
import json
import logging
import mimetypes
import re
import sys
import time
from datetime import datetime
import dingtalk_stream
import requests
from dotenv import load_dotenv

from logistics_query import (
    BaosenLoginError,
    SERIAL_BROWSER_TRACKING_PLATFORMS,
    attach_tracking_result_link,
    query_tracking_number,
    load_env,
    find_order_by_fba,
    query_meitong,
    query_agl,
    query_17track,
    query_baosen,
    query_pingyi,
    decide_platform,
    decide_tracking_platform,
    get_primary_logistics_no,
    get_dingtalk_access_token,
    run_browser_tracking_query_with_queue,
)
from qq_query import query_qq, send_qq_question
from wechat_query import get_wechat_provider, query_wechat
from pathlib import Path
from dingtalk_stream.utils import DINGTALK_OPENAPI_ENDPOINT

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
)
logger = logging.getLogger(__name__)

_MESSAGE_DEDUP_TTL_SECONDS = 300
_TRACK_QUERY_MAX_ATTEMPTS = 3
_TRACK_QUERY_RETRY_DELAY_SECONDS = 2
_BUSINESS_MENU_TEXT = (
    "请选择要办理的业务：\n"
    "1. FBA查询\n"
    "2. 跟踪号查询\n\n"
    "回复【重置】➡️ 放弃本次并重新选择业务"
)


def _parse_track_time(value: str) -> datetime | None:
    text = (value or '').strip()
    if not text:
        return None

    chinese_match = __import__('re').match(
        r'^(\d{4})年(\d{1,2})月(\d{1,2})日(?:\s*GMT[+-]\d+)?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?$',
        text,
    )
    if chinese_match:
        year, month, day, hour, minute, second = chinese_match.groups()
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second or 0),
        )

    normalized = text.replace('UTC', '').replace('T', ' ').strip()
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y %H:%M',
        '%m/%d/%Y',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _sort_tracks_newest_first(tracks: list[dict]) -> list[dict]:
    indexed = list(enumerate(tracks))

    def sort_key(item):
        index, track = item
        parsed = _parse_track_time(str(track.get('时间', '')))
        return (parsed is not None, parsed or datetime.min, -index)

    sorted_items = sorted(indexed, key=sort_key, reverse=True)
    return [track for _, track in sorted_items]


def _normalize_track_content(track: dict) -> dict:
    normalized = dict(track)
    content = str(normalized.get('内容', '') or '').strip()
    if content:
        half = len(content) // 2
        if half > 0 and len(content) % 2 == 0 and content[:half] == content[half:]:
            normalized['内容'] = content[:half]
            return normalized

        for prefix in ('已预订：', '装货港口：', '运输途中：', '卸货港口：', '正在配送：', '已配送至亚马逊运营中心：'):
            if content.startswith(prefix):
                payload = content[len(prefix):].strip()
                half = len(payload) // 2
                if half > 0 and len(payload) % 2 == 0 and payload[:half] == payload[half:]:
                    normalized['内容'] = f"{prefix}{payload[:half]}"
                break
    return normalized


def _deduplicate_tracks(tracks: list[dict]) -> list[dict]:
    deduplicated: list[dict] = []
    seen_signatures: set[tuple[str, str, str]] = set()

    for track in tracks:
        signature = (
            str(track.get('时间', '') or '').strip(),
            str(track.get('内容', '') or track.get('地点', '') or '').strip(),
            str(track.get('消息类型', '') or '').strip(),
        )
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduplicated.append(track)

    return deduplicated


def _extract_wechat_query_value(message_content: str) -> str:
    compact = (message_content or '').strip()
    if '微信' not in compact:
        return ''

    without_keyword = compact.replace('微信', ' ')
    tokens = [
        token.strip()
        for token in re.split(r'[\s,，;；|｜]+', without_keyword)
        if token.strip()
    ]
    if not tokens:
        return ''
    return tokens[-1]


class LogisticsBotHandler(dingtalk_stream.ChatbotHandler):
    """物流查询机器人处理器"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._message_seen_at: dict[str, float] = {}
        self._conversation_modes: dict[str, str] = {}
        self._browser_query_lock = asyncio.Lock()
        self._browser_queue_waiting = 0
        self._qq_query_lock = asyncio.Lock()
        self._qq_queue_waiting = 0
        self._background_tasks: set[asyncio.Task] = set()

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        """处理接收到的消息"""
        try:
            incoming_message = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
            self._purge_expired_messages()

            # 获取发送者信息
            sender_nick = incoming_message.sender_nick
            conversation_id = incoming_message.conversation_id
            text_body = getattr(incoming_message, 'text', None)
            message_content = ''
            if text_body is not None:
                message_content = (getattr(text_body, 'content', '') or '').strip()
            dedup_key = self._build_message_dedup_key(callback, incoming_message, message_content)

            if self._is_duplicate_message(dedup_key):
                self.logger.info("忽略重复消息 - 发送者: %s, 内容: %s", sender_nick, message_content)
                return dingtalk_stream.AckMessage.STATUS_OK, 'DUPLICATE'

            self._mark_message_seen(dedup_key)

            self.logger.info(f"收到消息 - 发送者: {sender_nick}, 内容: {message_content}")

            # 简单处理：只处理文本消息
            if incoming_message.message_type == 'text':
                if not message_content:
                    self.logger.info("收到空文本消息 - 发送者: %s", sender_nick)
                    self.reply_text("请发送纯文本格式的FBA编号进行查询", incoming_message)
                    return dingtalk_stream.AckMessage.STATUS_OK, 'EMPTY_TEXT'
                await self._handle_text_message(incoming_message, message_content)
            else:
                self.logger.info(
                    "收到非文本消息 - 发送者: %s, message_type: %s",
                    sender_nick,
                    incoming_message.message_type,
                )
                self.reply_text("请发送FBA编号进行查询", incoming_message)

            return dingtalk_stream.AckMessage.STATUS_OK, 'OK'

        except Exception as e:
            self.logger.error(f"处理消息失败: {e}", exc_info=True)
            return dingtalk_stream.AckMessage.STATUS_OK, 'ERROR'

    def _build_message_dedup_key(self, callback, incoming_message, message_content: str) -> str:
        candidates = [
            getattr(callback, 'message_id', None),
            getattr(incoming_message, 'message_id', None),
            getattr(incoming_message, 'msg_id', None),
        ]
        for candidate in candidates:
            if candidate:
                return f"msg:{candidate}"

        sender = getattr(incoming_message, 'sender_staff_id', None) or getattr(incoming_message, 'sender_id', None) or incoming_message.sender_nick
        conversation = getattr(incoming_message, 'conversation_id', '')
        return f"fallback:{conversation}:{sender}:{message_content}"

    def _is_duplicate_message(self, dedup_key: str) -> bool:
        seen_at = self._message_seen_at.get(dedup_key)
        if seen_at is None:
            return False
        return time.time() - seen_at < _MESSAGE_DEDUP_TTL_SECONDS

    def _mark_message_seen(self, dedup_key: str) -> None:
        self._message_seen_at[dedup_key] = time.time()

    def _purge_expired_messages(self) -> None:
        now = time.time()
        expired = [key for key, seen_at in self._message_seen_at.items() if now - seen_at >= _MESSAGE_DEDUP_TTL_SECONDS]
        for key in expired:
            self._message_seen_at.pop(key, None)

    def _get_conversation_mode(self, conversation_id: str) -> str:
        mode = self._conversation_modes.get(conversation_id, '')
        return mode if mode in {'menu', 'fba', 'tracking'} else ''

    def _set_conversation_mode(self, conversation_id: str, mode: str) -> None:
        self._conversation_modes[conversation_id] = mode

    def _reply_business_menu(self, incoming_message) -> None:
        self.reply_text(_BUSINESS_MENU_TEXT, incoming_message)

    async def _handle_fba_message(self, incoming_message, text_content: str):
        await self._handle_fba_query(incoming_message, text_content)

    async def _handle_tracking_message(self, incoming_message, text_content: str):
        await self._handle_tracking_query(incoming_message, text_content)

    async def _handle_text_message(self, incoming_message, text_content: str):
        """处理文本消息"""
        conversation_id = getattr(incoming_message, 'conversation_id', '')
        normalized_text = text_content.strip()
        mode = self._get_conversation_mode(conversation_id)

        if normalized_text == '重置':
            self._set_conversation_mode(conversation_id, 'menu')
            self._reply_business_menu(incoming_message)
            return

        if not mode:
            self._set_conversation_mode(conversation_id, 'menu')
            self._reply_business_menu(incoming_message)
            return

        if mode == 'menu':
            if normalized_text == '1':
                self._set_conversation_mode(conversation_id, 'fba')
                self.reply_text(
                    '已切换到 FBA查询。后续消息将按 FBA 查询处理，回复【重置】可重新选择业务。',
                    incoming_message,
                )
                return
            if normalized_text == '2':
                self._set_conversation_mode(conversation_id, 'tracking')
                self.reply_text(
                    '已切换到 跟踪号查询。后续消息将按跟踪号查询处理，回复【重置】可重新选择业务。',
                    incoming_message,
                )
                return
            self._reply_business_menu(incoming_message)
            return

        if mode == 'fba':
            await self._handle_fba_message(incoming_message, text_content)
            return

        if mode == 'tracking':
            await self._handle_tracking_message(incoming_message, text_content)
            return

        self._set_conversation_mode(conversation_id, 'menu')
        self._reply_business_menu(incoming_message)
        return

    async def _handle_fba_query(self, incoming_message, text_content: str):
        """处理 FBA 文本消息"""

        fba_code = text_content.strip()

        if not fba_code:
            self.reply_text("请发送要查询的FBA编号", incoming_message)
            return

        wechat_query_value = _extract_wechat_query_value(text_content)
        if wechat_query_value:
            self.logger.info("开始微信查询 query=%s", wechat_query_value)
            self.reply_text(f"收到，开始走微信查询 {wechat_query_value} ...", incoming_message)
            try:
                result = await asyncio.to_thread(query_wechat, wechat_query_value)
                error = str(result.get('错误', '') or '').strip()
                if error:
                    reply_text = f"❌ 微信查询失败: {error}"
                else:
                    reply_lines = [
                        f"📱 微信查询已发送\n"
                        f"群聊: {result.get('群名', '')}\n"
                        f"询问对象: {result.get('询问对象', '')}\n"
                        f"查询值: {result.get('查询值', '')}\n"
                        f"提问内容: {result.get('提问内容', '')}"
                    ]
                    latest_track = result.get('最新轨迹') or {}
                    track_content = str(latest_track.get('内容', '') or '').strip()
                    if get_wechat_provider() == 'gewechat' and track_content:
                        track_time = str(latest_track.get('时间', '') or '').strip()
                        reply_lines.append(
                            "\n\n💬 微信最新回复:\n"
                            + (f"{track_time}: {track_content}" if track_time else track_content)
                        )
                    reply_text = ''.join(reply_lines)
                self.reply_text(reply_text, incoming_message)
                self.logger.info("微信查询完成 query=%s", wechat_query_value)
            except Exception as e:
                self.logger.error("微信查询失败: %s", e, exc_info=True)
                self.reply_text(f"❌ 微信查询失败: {str(e)}", incoming_message)
            return

        # 先回复收到
        self.logger.info("开始查询 FBA=%s", fba_code)
        self.reply_text(f"收到，开始查询 {fba_code} ...", incoming_message)

        # 查询表格
        try:
            order = find_order_by_fba(fba_code)

            if order:
                # 格式化回复消息
                reply_text = self._format_order_info(order, fba_code)
                platform = decide_platform(order, 'auto')
                if platform == 'qq':
                    qq_result = await self._query_qq_preview(order, fba_code)
                    if qq_result.get('需要QQ询问'):
                        reply_text += self._format_tracking_result(qq_result, 'qq')
                        self.reply_text(reply_text, incoming_message)
                        self._schedule_qq_question(order, fba_code)
                    elif qq_result.get('需要异步跟进'):
                        reply_text += self._build_qq_pending_reply(order)
                        self.reply_text(reply_text, incoming_message)
                        self._schedule_qq_follow_up(incoming_message, order, fba_code)
                    else:
                        reply_text += self._format_tracking_result(qq_result, 'qq')
                        self.reply_text(reply_text, incoming_message)
                    self.logger.info("查询完成 FBA=%s", fba_code)
                    return

                tracking_reply = await self._query_tracking_info(order, fba_code)
                if tracking_reply:
                    reply_text += f"\n\n{tracking_reply}"
            else:
                reply_text = f"❌ 未找到FBA编号 {fba_code} 的记录"

            self.reply_text(reply_text, incoming_message)
            self.logger.info("查询完成 FBA=%s", fba_code)

        except Exception as e:
            self.logger.error(f"查询失败: {e}", exc_info=True)
            self.reply_text(f"❌ 查询失败: {str(e)}", incoming_message)

    async def _handle_tracking_query(self, incoming_message, text_content: str):
        tracking_no = text_content.strip()
        if not tracking_no:
            self.reply_text("请发送要查询的跟踪号", incoming_message)
            return
        self.reply_text(f"收到，开始查询跟踪号 {tracking_no} ...", incoming_message)
        platform_key = decide_tracking_platform(tracking_no)
        if platform_key in SERIAL_BROWSER_TRACKING_PLATFORMS:
            result = await run_browser_tracking_query_with_queue(
                platform=platform_key.upper(),
                query_value=tracking_no,
                operation=lambda: query_tracking_number(tracking_no),
            )
        else:
            result = await query_tracking_number(tracking_no)
        reply_text = self._format_tracking_result(result, 'tracking')
        if reply_text:
            self.reply_text(reply_text, incoming_message)

    def _build_qq_pending_reply(self, order: dict) -> str:
        tracking_no = get_primary_logistics_no(order)
        if not tracking_no:
            return '\n\n⚠️ 钉钉表格中缺少物流编号，暂时无法发起 QQ 人工查询'
        return (
            f"\n\n⏳ 已发起 QQ 人工查询({tracking_no})"
            "\n💬 该查询依赖人工回复，结果会在收到回复后单独补发"
        )

    async def _query_qq_preview(self, order: dict, fba_code: str) -> dict:
        tracking_no = get_primary_logistics_no(order)
        if not tracking_no:
            return {
                '平台': 'QQ',
                '查询值': '',
                '物流轨迹': [],
                '最新轨迹': {},
                '错误': '钉钉表格中缺少物流编号，暂时无法查询物流轨迹',
            }
        self.logger.info("轨迹查询预判: 平台=QQ 物流编号=%s", tracking_no)
        return await self._run_qq_query_with_queue(
            platform='QQ',
            query_value=tracking_no,
            operation=lambda: asyncio.to_thread(query_qq, order, tracking_no, True),
        )

    def _schedule_qq_follow_up(self, incoming_message, order: dict, fba_code: str) -> None:
        task = asyncio.create_task(self._run_qq_follow_up(incoming_message, order, fba_code))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _schedule_qq_question(self, order: dict, fba_code: str) -> None:
        task = asyncio.create_task(self._run_qq_question(order, fba_code))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _run_qq_question(self, order: dict, fba_code: str) -> None:
        tracking_no = get_primary_logistics_no(order)
        if not tracking_no:
            self.logger.info("QQ 人工询问跳过: FBA=%s 缺少物流编号", fba_code)
            return
        try:
            result = await self._run_qq_query_with_queue(
                platform='QQ',
                query_value=tracking_no,
                operation=lambda: asyncio.to_thread(send_qq_question, order, tracking_no),
            )
            error = str(result.get('错误', '') or '').strip()
            if error:
                self.logger.warning("QQ 人工询问发送失败 FBA=%s error=%s", fba_code, error)
                return
            self.logger.info("QQ 人工询问已发送 FBA=%s message_id=%s", fba_code, result.get('发送消息ID', ''))
        except Exception as e:
            self.logger.error("QQ 人工询问发送异常 FBA=%s error=%s", fba_code, e, exc_info=True)

    async def _run_qq_follow_up(self, incoming_message, order: dict, fba_code: str) -> None:
        try:
            result = await self._query_qq_result(order, fba_code)
            self._reply_qq_result(incoming_message, fba_code, result)
            self.logger.info("QQ 异步回推完成 FBA=%s", fba_code)
        except Exception as e:
            self.logger.error("QQ 异步回推失败 FBA=%s error=%s", fba_code, e, exc_info=True)
            self.reply_text(f"📦 FBA编号: {fba_code}\n\n❌ QQ 查询失败: {str(e)}", incoming_message)

    async def _query_qq_result(self, order: dict, fba_code: str) -> dict:
        tracking_no = get_primary_logistics_no(order)
        if not tracking_no:
            return {
                '平台': 'QQ',
                '查询值': '',
                '物流轨迹': [],
                '最新轨迹': {},
                '错误': '钉钉表格中缺少物流编号，暂时无法查询物流轨迹',
            }
        self.logger.info("轨迹查询: 平台=QQ 物流编号=%s", tracking_no)
        return await self._run_qq_query_with_queue(
            platform='QQ',
            query_value=tracking_no,
            operation=lambda: asyncio.to_thread(query_qq, order, tracking_no),
        )

    def _reply_qq_result(self, incoming_message, fba_code: str, result: dict) -> None:
        tracking_info = self._format_tracking_result(result, 'qq')
        if not tracking_info:
            self.logger.info("QQ 异步回推跳过空结果 FBA=%s", fba_code)
            return
        reply_text = f"📦 FBA编号: {fba_code}{tracking_info}"
        self.reply_text(reply_text, incoming_message)

        latest_track = result.get('最新轨迹') or {}
        attachments = latest_track.get('附件') or []
        if attachments:
            self._reply_qq_attachments(incoming_message, attachments)

    def _reply_qq_attachments(self, incoming_message, attachments: list[dict]) -> None:
        for index, attachment in enumerate(attachments, start=1):
            asset_type = str(attachment.get('类型', '') or '').strip()
            name = str(attachment.get('名称', '') or '').strip()
            url = str(attachment.get('链接', '') or '').strip()
            if not url:
                fallback = f"附件{index}"
                label = f"[{asset_type}] {name}".strip() if asset_type or name else fallback
                self.reply_text(f"⚠️ {label}\n未提供可下载链接", incoming_message)
                continue

            try:
                if asset_type == '图片':
                    self._reply_dingtalk_image(incoming_message, url, name or f'qq-image-{index}.jpg')
                elif asset_type == '文件':
                    self._reply_dingtalk_file(incoming_message, url, name or f'qq-file-{index}')
                else:
                    self.reply_markdown(
                        title='QQ附件',
                        text=f"[{asset_type or '附件'}] {name or url}\n\n{url}",
                        incoming_message=incoming_message,
                    )
            except Exception as exc:
                self.logger.warning("转发 QQ 附件失败: type=%s name=%s url=%s error=%s", asset_type, name, url, exc)
                label = f"[{asset_type}] {name}".strip() if asset_type or name else url
                self.reply_text(f"⚠️ 附件转发失败: {label}\n{url}", incoming_message)

    def _reply_qq_attachment_link(self, incoming_message, asset_type: str, name: str, url: str) -> None:
        label = name or url
        title = f"QQ{asset_type or '附件'}"
        self.reply_markdown(
            title=title,
            text=f"**{title}**\n\n{label}\n\n{url}",
            incoming_message=incoming_message,
        )

    def _download_remote_asset(self, url: str) -> tuple[bytes, str]:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        return response.content, content_type

    def _normalize_upload_filename(self, filename: str, content_type: str, default_stem: str) -> str:
        raw_name = (filename or '').strip()
        suffix = Path(raw_name).suffix
        guessed_suffix = mimetypes.guess_extension(content_type or '') or ''

        if not suffix and guessed_suffix:
            suffix = guessed_suffix

        stem = Path(raw_name).stem if raw_name else ''
        if not stem or stem.startswith('['):
            stem = default_stem

        safe_stem = re.sub(r'[^A-Za-z0-9._-]+', '-', stem).strip('-._') or default_stem
        return f'{safe_stem}{suffix}'

    def _reply_dingtalk_robot_message(self, incoming_message, msg_key: str, msg_param: dict) -> dict | None:
        access_token = self.dingtalk_client.get_access_token()
        if not access_token:
            raise RuntimeError('无法获取钉钉 access token')

        headers = {
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'x-acs-dingtalk-access-token': access_token,
        }
        body = {
            'msgKey': msg_key,
            'msgParam': json.dumps(msg_param, ensure_ascii=False),
            'robotCode': self.dingtalk_client.credential.client_id,
        }

        if incoming_message.conversation_type == '2':
            if not incoming_message.conversation_id:
                raise RuntimeError('缺少 conversation_id，无法发送群附件消息')
            body['openConversationId'] = incoming_message.conversation_id
            endpoint = '/v1.0/robot/groupMessages/send'
        elif incoming_message.conversation_type == '1':
            sender_staff_id = getattr(incoming_message, 'sender_staff_id', '') or getattr(incoming_message, 'sender_id', '')
            if not sender_staff_id:
                raise RuntimeError('缺少 sender_staff_id，无法发送单聊附件消息')
            body['userIds'] = [sender_staff_id]
            self.logger.info(
                "钉钉单聊附件发送: sender_staff_id=%s sender_id=%s conversation_id=%s msgKey=%s",
                sender_staff_id,
                getattr(incoming_message, 'sender_id', '') or '',
                incoming_message.conversation_id,
                msg_key,
            )
            endpoint = '/v1.0/robot/oToMessages/batchSend'
        else:
            raise RuntimeError(f'不支持的会话类型，无法发送附件消息: {incoming_message.conversation_type}')

        response = requests.post(
            DINGTALK_OPENAPI_ENDPOINT + endpoint,
            headers=headers,
            json=body,
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f'钉钉附件消息发送失败: status={response.status_code} body={response.text}'
            ) from exc
        return response.json()

    def _reply_dingtalk_image(self, incoming_message, url: str, filename: str) -> None:
        self._reply_dingtalk_robot_message(
            incoming_message,
            msg_key='sampleImageMsg',
            msg_param={
                'photoURL': url,
            },
        )

    def _reply_dingtalk_file(self, incoming_message, url: str, filename: str) -> None:
        content, content_type = self._download_remote_asset(url)
        filename = self._normalize_upload_filename(filename, content_type, 'qq-file')
        suffix = Path(filename).suffix.lower().lstrip('.')
        if not suffix:
            guessed = mimetypes.guess_extension(content_type or '') or ''
            suffix = guessed.lstrip('.')
            if guessed and not filename.endswith(guessed):
                filename = f'{filename}{guessed}'
        media_id = self.dingtalk_client.upload_to_dingtalk(
            content,
            filetype='file',
            filename=filename,
            mimetype=content_type or 'application/octet-stream',
        )
        if not media_id:
            raise RuntimeError('文件上传到钉钉失败')
        self._reply_dingtalk_robot_message(
            incoming_message,
            msg_key='sampleFile',
            msg_param={
                'mediaId': media_id,
                'fileName': filename,
                'fileType': suffix or 'pdf',
            },
        )

    def _format_tracking_result(self, result: dict, platform: str, query_value: str | None = None) -> str:
        if platform == 'tracking':
            result = attach_tracking_result_link(result)
        normalized_platform = str(result.get('平台', platform) or platform).strip()
        display_query_value = (query_value or result.get('查询值') or '').strip()
        tracks = _deduplicate_tracks(
            [_normalize_track_content(track) for track in _sort_tracks_newest_first(result.get('物流轨迹') or [])]
        )

        if not tracks:
            error = str(result.get('错误', '') or '').strip()
            if error:
                if normalized_platform.upper() == 'QQ' and '等待 QQ 回复超时' in error:
                    self.logger.info(
                        "轨迹查询结果: 平台=%s 查询值=%s QQ超时无回复，按空结果处理",
                        normalized_platform,
                        display_query_value,
                    )
                    return ''
                self.logger.warning(
                    "轨迹查询结果: 平台=%s 查询值=%s 错误=%s",
                    normalized_platform,
                    display_query_value,
                    error,
                )
                return f"⚠️ 物流轨迹查询失败: {error}"
            self.logger.info(
                "轨迹查询结果: 平台=%s 查询值=%s 无轨迹",
                normalized_platform,
                display_query_value,
            )
            return f"暂无{normalized_platform.upper()}物流轨迹信息"

        latest_track = tracks[0]
        self.logger.info(
            "轨迹查询结果: 平台=%s 查询值=%s 条数=%s 最新=%s | %s",
            normalized_platform,
            display_query_value,
            len(tracks),
            latest_track.get('时间', ''),
            latest_track.get('内容', '') or latest_track.get('地点', ''),
        )

        lines = []
        if display_query_value:
            lines.append(f"正在查询物流轨迹({display_query_value})...")
        lines.append(f"📦 最新物流轨迹({normalized_platform}) - 按时间倒序:")

        result_source = str(result.get('结果来源', '') or '').strip()
        if result_source:
            lines.append(f"📚 结果来源: {result_source}")

        tracking_link = str(result.get('物流链接', '') or '').strip()
        if platform == 'tracking' and tracking_link:
            lines.append(f"🔗 物流详情: {tracking_link}")

        for track in tracks[:5]:
            time_str = str(track.get('时间', '') or '').strip()
            content = str(track.get('内容', '') or track.get('地点', '') or '').strip()
            tracking_no = str(track.get('单号', '') or '').strip()
            if tracking_no and time_str and content:
                lines.append(f"• {time_str} [{tracking_no}]: {content}")
            elif tracking_no and content:
                lines.append(f"• [{tracking_no}] {content}")
            elif time_str and content:
                lines.append(f"• {time_str}: {content}")
            elif content:
                lines.append(f"• {content}")
        if len(tracks) > 5:
            lines.append(f"• ... 仅显示最新5条（共{len(tracks)}条）")
        return '\n'.join(lines)

    def _format_order_info(self, order: dict, fba_code: str) -> str:
        """格式化订单信息为文本"""
        lines = [
            f"📦 FBA编号: {fba_code}",
        ]

        # 品牌
        brand = order.get('品牌', {})
        if isinstance(brand, dict):
            brand_name = brand.get('name', '')
        else:
            brand_name = brand
        if brand_name:
            lines.append(f"🏷️ 品牌: {brand_name}")

        # 国家
        country = order.get('国家', {})
        if isinstance(country, dict):
            country_name = country.get('name', '')
        else:
            country_name = country
        if country_name:
            lines.append(f"🌍 国家: {country_name}")

        # 物流编号
        wlbh = order.get('物流编号', '/')
        if wlbh and wlbh != '/':
            lines.append(f"📜 物流编号: {wlbh}")

        # 出运渠道
        channel = order.get('出运渠道', '/')
        if channel and channel != '/':
            lines.append(f"🚢 出运渠道: {channel}")

        # 预计到港时间
        eta = order.get('预计到港时间', '/')
        if eta and eta != '/':
            if isinstance(eta, int):
                from datetime import datetime
                eta_date = datetime.fromtimestamp(eta / 1000)
                eta = eta_date.strftime('%Y-%m-%d')
            lines.append(f"📅 预计到港: {eta}")

        # 实际到港时间
        actual_arrival = order.get('实际到港时间', '/')
        if actual_arrival and actual_arrival != '/':
            if isinstance(actual_arrival, int):
                from datetime import datetime
                actual_arrival_date = datetime.fromtimestamp(actual_arrival / 1000)
                actual_arrival = actual_arrival_date.strftime('%Y-%m-%d')
            lines.append(f"✅ 实际到港: {actual_arrival}")

        # 货代公司
        forwarder = order.get('货代公司', '/')
        if forwarder and forwarder != '/':
            lines.append(f"🏢 货代公司: {forwarder}")

        # 发票号
        invoice = order.get('发票号', '/')
        if invoice and invoice != '/':
            lines.append(f"🧾 发票号: {invoice}")

        return '\n'.join(lines)

    async def _query_tracking_info(self, order: dict, fba_code: str) -> str:
        platform = decide_platform(order, 'auto')
        tracking_no = get_primary_logistics_no(order)

        if platform == 'none':
            return ''

        if platform in {'meitong', 'agl', 'baosen', 'qq', '17track'} and not tracking_no:
            return '\n\n⚠️ 钉钉表格中缺少物流编号，暂时无法查询物流轨迹'

        try:
            if platform == 'meitong':
                query_value = tracking_no
                self.logger.info("轨迹查询: 平台=美通 物流编号=%s", query_value)
                result = await self._run_tracking_query_with_retry(
                    platform='美通',
                    query_value=query_value,
                    operation=lambda: query_meitong(query_value),
                )
            elif platform == 'agl':
                query_value = tracking_no
                self.logger.info("轨迹查询: 平台=AGL BookingID=%s", query_value)
                result = await self._run_tracking_query_with_queue(
                    platform='AGL',
                    platform_key=platform,
                    query_value=query_value,
                    operation=lambda: asyncio.to_thread(query_agl, query_value, order, False),
                )
            elif platform == 'pingyi':
                # 平谊直接使用用户发送的单号查询，不依赖钉钉表里的物流编号
                query_value = fba_code
                self.logger.info("轨迹查询: 平台=平谊 运单号=%s", query_value)
                result = await self._run_tracking_query_with_queue(
                    platform='平谊',
                    platform_key=platform,
                    query_value=query_value,
                    operation=lambda: query_pingyi(query_value),
                )
            elif platform == 'baosen':
                query_value = tracking_no
                self.logger.info("轨迹查询: 平台=堡森 物流编号=%s", query_value)
                result = await self._run_tracking_query_with_queue(
                    platform='堡森',
                    platform_key=platform,
                    query_value=query_value,
                    operation=lambda: query_baosen(query_value),
                )
            elif platform == 'qq':
                query_value = tracking_no
                self.logger.info("轨迹查询: 平台=QQ 物流编号=%s", query_value)
                result = await self._run_qq_query_with_queue(
                    platform='QQ',
                    query_value=query_value,
                    operation=lambda: asyncio.to_thread(query_qq, order, query_value),
                )
            elif platform == '17track':
                query_value = tracking_no
                self.logger.info("轨迹查询: 平台=17TRACK 物流编号=%s", query_value)
                result = await self._run_tracking_query_with_queue(
                    platform='17TRACK',
                    platform_key=platform,
                    query_value=query_value,
                    operation=lambda: query_17track(query_value),
                )
            else:
                return ''
        except Exception as e:
            self.logger.warning(f"查询物流轨迹失败: {e}")
            return '\n\n⚠️ 物流轨迹查询失败'

        return self._format_tracking_result(result, platform, query_value=query_value)

    async def _run_tracking_query_with_queue(self, platform: str, platform_key: str, query_value: str, operation):
        if platform_key not in SERIAL_BROWSER_TRACKING_PLATFORMS:
            return await self._run_tracking_query_with_retry(platform, query_value, operation)

        return await run_browser_tracking_query_with_queue(
            platform=platform,
            query_value=query_value,
            operation=lambda: self._run_tracking_query_with_retry(platform, query_value, operation),
        )

    async def _run_qq_query_with_queue(self, platform: str, query_value: str, operation):
        queued_ahead = self._qq_queue_waiting
        if self._qq_query_lock.locked():
            self._qq_queue_waiting += 1
            queued_ahead = self._qq_queue_waiting
            self.logger.info(
                "QQ查询队列: 查询值=%s 排队中 queued_ahead=%s",
                query_value,
                queued_ahead,
            )

        await self._qq_query_lock.acquire()
        if queued_ahead:
            self._qq_queue_waiting = max(0, self._qq_queue_waiting - 1)

        try:
            self.logger.info(
                "QQ查询队列: 查询值=%s 开始执行 waiting=%s",
                query_value,
                self._qq_queue_waiting,
            )
            return await self._run_tracking_query_with_retry(platform, query_value, operation)
        finally:
            self._qq_query_lock.release()
            self.logger.info(
                "QQ查询队列: 查询值=%s 执行结束 remaining_waiting=%s",
                query_value,
                self._qq_queue_waiting,
            )

    async def _run_tracking_query_with_retry(self, platform: str, query_value: str, operation):
        last_error: Exception | None = None
        last_result: dict | None = None

        for attempt in range(1, _TRACK_QUERY_MAX_ATTEMPTS + 1):
            try:
                result = operation()
                if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                    result = await result

                if self._should_retry_tracking_result(platform, result):
                    error = str((result or {}).get('错误', '')).strip() or '未知错误'
                    last_result = result
                    self.logger.warning(
                        "轨迹查询失败，准备重试: 平台=%s 查询值=%s attempt=%s/%s 错误=%s",
                        platform,
                        query_value,
                        attempt,
                        _TRACK_QUERY_MAX_ATTEMPTS,
                        error,
                    )
                    if attempt < _TRACK_QUERY_MAX_ATTEMPTS:
                        await asyncio.sleep(_TRACK_QUERY_RETRY_DELAY_SECONDS)
                        continue
                return result
            except Exception as exc:
                last_error = exc
                if isinstance(exc, BaosenLoginError):
                    self.logger.warning(
                        "轨迹查询遇到不可重试错误: 平台=%s 查询值=%s 错误=%s",
                        platform,
                        query_value,
                        exc,
                    )
                    raise
                self.logger.warning(
                    "轨迹查询异常，准备重试: 平台=%s 查询值=%s attempt=%s/%s 错误=%s",
                    platform,
                    query_value,
                    attempt,
                    _TRACK_QUERY_MAX_ATTEMPTS,
                    exc,
                )
                if attempt < _TRACK_QUERY_MAX_ATTEMPTS:
                    await asyncio.sleep(_TRACK_QUERY_RETRY_DELAY_SECONDS)
                    continue
                raise

        if last_result is not None:
            return last_result
        if last_error is not None:
            raise last_error
        raise RuntimeError(f'轨迹查询失败: 平台={platform} 查询值={query_value}')

    def _should_retry_tracking_result(self, platform: str, result: dict | None) -> bool:
        if not isinstance(result, dict):
            return False
        error = str(result.get('错误', '') or '').strip()
        if not error:
            return False
        if result.get('物流轨迹'):
            return False
        normalized_platform = str(platform or '').strip().upper()
        if normalized_platform == 'QQ':
            non_retryable_markers = (
                '等待 QQ 回复超时',
                'token verify failed',
                'QQ API HTTP 异常: status=403',
                'action=send_group_msg error=Timeout',
                'NodeIKernelMsgService/sendMsg',
                '未找到目标QQ群',
                '中未找到成员',
                '存在多个同名成员',
                '当前货代公司未配置 QQ 查询规则',
            )
            if any(marker in error for marker in non_retryable_markers):
                return False
        return True


def main():
    """主函数"""
    # 加载环境变量
    env_path = Path(__file__).with_name('.env')
    load_dotenv(env_path)

    logger.info("=" * 50)
    logger.info("钉钉物流查询机器人启动中...")
    logger.info("=" * 50)

    # 获取凭证
    from logistics_query import get_env
    try:
        client_id = get_env('DINGTALK_APP_KEY')
        client_secret = get_env('DINGTALK_APP_SECRET')
    except ValueError as e:
        logger.error(f"❌ {e}")
        logger.error("请在 .env 文件中配置 DINGTALK_APP_KEY 和 DINGTALK_APP_SECRET")
        sys.exit(1)

    logger.info(f"📱 Client ID: {client_id[:10]}...")

    # 预加载表格数据
    try:
        load_env()
        logger.info("✅ 环境变量加载成功")
    except Exception as e:
        logger.warning(f"⚠️ 环境变量加载失败: {e}")

    # 创建钉钉Stream客户端
    credential = dingtalk_stream.Credential(client_id, client_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential)

    # 注册消息处理器
    logger.info("📝 注册消息处理器...")
    client.register_callback_handler(
        dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
        LogisticsBotHandler()
    )

    logger.info("✅ 钉钉机器人启动成功！")
    logger.info("💡 发送FBA编号进行查询...")

    # 启动客户端
    try:
        client.start_forever()
    except KeyboardInterrupt:
        logger.info("\n⏹️  收到停止信号，正在关闭...")
    except Exception as e:
        logger.error(f"❌ 运行时发生错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
