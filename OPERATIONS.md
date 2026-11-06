# 项目流程

## 总体入口
- 机器人入口: `main.py`
- 业务核心: `logistics_query.py`
- QQ 询问逻辑: `qq_query.py`
- 微信实验逻辑: `wechat_query.py`

## 单聊业务选择
- 单聊首次进入时，机器人不会直接查询，而是先返回业务菜单。
- 回复 `1` 后进入持续 `FBA查询` 模式，直到回复 `重置`。
- 回复 `2` 后进入持续 `跟踪号查询` 模式，直到回复 `重置`。
- 跟踪号查询不查钉钉表格，而是按前缀走平台官网，未命中特殊前缀时回退到 `17track`。
- `uniuni` 当前已接入直达 `tracking-detail` URL 的页面查询，并从详情页 `Tracking History` 直接读取轨迹。
- `gofo` 当前已接入 `Export Summary` 导出流程，并从导出文件中读取 `Current status` 作为状态结果。
- `usps` 当前已接入详情页轨迹抓取，并读取全部 `tb-step` 状态块作为轨迹列表。
- `ups` 当前已接入详情页当前状态抓取，并读取激活中的进度步骤文本作为状态结果。
- `yuntrack` 当前已接入 `Export Summary` 导出流程，并从导出文件中读取 `Delivery Status` 作为状态结果。
- `swiship` 当前已接入页面摘要和 `TRACKING HISTORY` 表格抓取，并同时返回摘要状态与历史轨迹。
- `amazon_us` 当前已接入页面大标题抓取，并读取 `h1.css-alxyr3` 文本作为状态结果。
- `amazon_us` 若直达详情页出现 `We're sorry / We couldn't find the package you're looking for`，会自动回到首页重新输入跟踪号查询，并按设定次数重试。

## 当前主流程
1. 启动时加载 `.env`。
2. 启动钉钉 Stream 客户端，注册 `LogisticsBotHandler`。
3. 收到钉钉文本消息后，把消息内容当作 `FBA` 编号处理。
4. 如果文本中包含 `微信`，则直接走微信分支，不查询钉钉表格。
5. 如果未命中 `微信` 关键字，才调用 `find_order_by_fba` 查询钉钉表格记录。
6. 命中记录后，先整理基础字段并回复。
7. 再根据 `货代公司` 自动选择物流查询平台。
8. 查询结果会追加到钉钉回复中。

## 当前货代分支
- `龙舟` -> `AGL`
  - 使用钉钉表里的 `物流编号` 作为 `BookingID`
  - 通过 Playwright 查询 AGL 页面
- `平谊` -> `平谊系统`
  - 直接使用用户在钉钉中发送的 FBA 编号查询
  - 调用软通宝 `PublicService` 的 `getTrack` 接口，不依赖浏览器或钉钉表里的 `物流编号`
- `堡森` -> `堡森系统`
  - 使用钉钉表里的 `物流编号`
  - 通过 Playwright 查询堡森页面
- `金为` -> `QQ`
  - 使用钉钉表里的 `物流编号`
  - 去指定 QQ 群里 `@李美慧` 询问物流状态
  - 取对方第一条回复
- `大黄蜂` -> `17TRACK`
  - 使用钉钉表里的 `物流编号`
  - 打开 `https://www.17track.net/zh-cn` 查询轨迹
- `盈和` -> `盈和系统`
  - 使用钉钉表里的 `物流编号`
  - 打开 `http://www.gjwl.yhwl.com:8027/`，提交物流编号后展开运单和子单读取轨迹
- 其他货代公司 -> `美通`
  - 使用钉钉表里的 `物流编号`
  - 走接口查询

## 已移除逻辑
- 原先 `大黄蜂 -> QQ群 63017易达工具-DHF -> @DHF-B组报价专员` 这条逻辑已经移除。
- 现在 `大黄蜂` 统一走 `17TRACK`，不再通过 QQ 群询问。

## 各平台说明

## 美通
1. 使用接口查询轨迹。
2. 输入值为钉钉表里的 `物流编号`。

## AGL
1. 打开 `https://www.agl.amazon.com/freight-puma`。
2. 代码会自动启动本地 CDP Chrome，并通过 `Playwright + CDP` 连接浏览器。
3. 根据品牌选择对应账号密码，账号密码来自 `.env`：`LIBRATON`、`PACMANN` 使用 `AGL_USERNAME`；`YPLUS` 使用 `AGL_YPLUS_USERNAME`。未配置紫鸟环境时，`EZARC`、`TOLESA` 使用 `AGL_EASYCAN_USERNAME`。
4. 配置 `AGL_EASYCAN_ZINIAO_BROWSER_ID` 后，`EZARC`、`TOLESA` 改用同一紫鸟 WebDriver 环境。项目通过紫鸟本机 HTTP 服务启动或复用该环境，从响应的 `debuggingPort` 附加 Playwright 并查询 AGL；不会填写 AGL 账号密码、保存项目会话、退出 AGL、关闭紫鸟环境或关闭紫鸟客户端。可访问的紫鸟调试端口会保存到 `ZINIAO_BROWSER_STATE_PATH`（默认 `tmp/ziniao-browser-ports.json`），供机器人重启后继续复用；只有端口不可达时才会重新调用紫鸟打开环境。须在本机 `.env` 设置 `ZINIAO_COMPANY`、`ZINIAO_USERNAME`、`ZINIAO_PASSWORD`、`ZINIAO_WEBDRIVER_PORT`（默认 `16851`）和 `ZINIAO_CLIENT_PATH`。若服务未启动，项目会以 `ZINIAO_CLIENT_PATH --run_type=web_driver --ipc_type=http --port=<端口>` 启动紫鸟；已有普通紫鸟客户端实例时，应先在客户端侧完全退出，再由项目启动 WebDriver 实例。
5. 非紫鸟账号的会话分别保存到 `AGL_SESSION_STATE_DIR`（默认 `data/agl-sessions`）。首次出现登录页或验证码时，在打开的 AGL 窗口内完成验证，系统默认等待 120 秒；成功后后续查询会复用对应账号会话。可通过 `AGL_MANUAL_VERIFICATION_WAIT_SECONDS` 设置等待时间（30 到 600 秒）。页面登录成功后，轨迹组件默认最多等待 30 秒，可通过 `AGL_TRACKING_RENDER_WAIT_SECONDS` 设置（10 到 60 秒）。
5. 使用 `物流编号` 作为 `BookingID` 打开追踪页。

## 平谊
1. 请求 `http://hzpy.rtb56.com/webservice/PublicService.asmx/ServiceInterfaceUTF8`。
2. 使用 `application/x-www-form-urlencoded` 提交 `appToken`、`appKey`、`serviceMethod=getTrack` 和 `paramsJson`。
3. `paramsJson` 为 `{"tracking_number":"<FBA编号或跟踪号>"}`；FBA 查询默认传用户输入的 FBA 编号。
4. 从 `data[0].details` 读取 `track_occur_date`、`track_description`、`track_location` 和 `track_code`。
5. 在 `.env` 配置 `PINGYI_BASE_URL`、`PINGYI_APP_TOKEN`、`PINGYI_APP_KEY`；可用 `PINGYI_API_TIMEOUT_SECONDS` 设置单次 HTTP 超时，默认 20 秒，范围 5 到 60 秒。

## 堡森
1. 打开堡森官网页面。
2. 通过 Playwright 自动启动本地 CDP Chrome 并连接。
3. 如果检测到未登录，则使用 `.env` 中的账号密码登录。
4. 在页面中输入 `物流编号` 查询。
5. 获取最新轨迹后关闭浏览器。

## QQ
1. 当前只配置了 `金为`。
2. 群名: `璧久FBA海运-杭州金为`
3. 提问对象: `李美慧`
4. 提问内容格式: `@李美慧 <物流编号> 物流状态`
5. 通过 NapCat OneBot HTTP API 发消息并轮询群消息。
6. 命中对方第一条新回复后返回。
7. 本机需要先启动 NapCat，并暴露 HTTP API 到 `QQ_API_BASE_URL`。
8. 在 `.env` 中手动填写 `QQ_JINWEI_GROUP_ID` 和 `QQ_JINWEI_USER_ID`。

## Windows + NapCatQQ 运行
1. 在 Windows 上运行本项目时，建议直接使用 Windows Python，不通过 WSL 启动浏览器。
2. 安装依赖:
   - `conda create -y -n dingtalk-bot python=3.11`
   - `conda run -n dingtalk-bot python -m pip install -r requirements.txt`
   - `conda run -n dingtalk-bot python -m playwright install chromium`
3. 启动 NapCatQQ:
   - 下载 `NapCat.Shell.zip`
   - 解压到本项目 `NapCat.Shell`
   - Windows 11 默认使用 `NapCat.Shell\launcher.bat`
   - Windows 10 在 `.env` 中设置 `NAPCAT_LAUNCHER_PATH=NapCat.Shell\launcher-win10.bat`
   - 打开控制台输出的 WebUI 地址并扫码登录 QQ
4. 在 NapCat WebUI 的网络配置中新建并启用 `HTTP 服务端`:
   - `host`: `127.0.0.1`
   - `port`: `6702`
   - `messagePostFormat`: `array`
   - `token`: 留空或自定义；如果自定义，需要同步写入本项目 `QQ_API_TOKEN`
5. 本项目 `.env` 中保持:
   - `QQ_API_BASE_URL=http://127.0.0.1:6702`
   - `QQ_API_TOKEN=`
   - `NAPCAT_LAUNCHER_PATH=NapCat.Shell\launcher.bat`
   - `NAPCAT_WAIT_SECONDS=90`
   - `LOCAL_CDP_USER_DATA_DIR=./data/chrome-cdp-windows`
6. 直接双击 `start_all.bat` 启动 NapCatQQ、本地 API 和机器人。
   - 使用 `dingtalk-bot` Conda 环境，需确保 `conda` 已加入 PATH。

## 17TRACK
1. 当前只配置了 `大黄蜂`。
2. 当前跟踪号查询模式会直接打开新版英文直达页：
   - `https://t.17track.net/en#nums=<物流编号>`
3. 页面加载后直接提取轨迹时间线。
4. 如果出现引导弹窗，会尝试关闭或完成引导后继续查询。
5. 如果遇到验证码或人工验证，程序会暂停等待人工处理，再继续抓取结果。
6. 单次查询默认最多等待 25 秒，超时后关闭查询页并走重试；可通过 `TRACKING_17TRACK_MAX_WAIT_SECONDS` 配置，取值范围为 10 到 90 秒。
7. 当前运行方式为本机直接启动浏览器。

## 查询超时
- 异步网页查询平台单次默认最多运行 45 秒，超时会关闭页面、释放浏览器队列并重试。
- 可用 `TRACKING_QUERY_ATTEMPT_TIMEOUT_SECONDS` 配置全局单次上限，取值范围为 10 到 180 秒。
- 单个平台可用 `TRACKING_<平台>_ATTEMPT_TIMEOUT_SECONDS` 覆盖，例如 `TRACKING_USPS_ATTEMPT_TIMEOUT_SECONDS=75`。
- AGL、QQ、美通使用各自的同步调用与网络超时，不走协程强制取消，避免旧任务仍在运行时误释放队列；平谊已改用 HTTP API，不再占用浏览器队列。

## 本机运行现状
- 应用直接在本机 Python 环境中运行。
- Playwright 浏览器和本地 Chrome CDP 都在本机启动。
- 当前 17TRACK、堡森等网页自动化使用本机浏览器能力。
- 当前策略是“按需启动浏览器，单次查询结束后自动关闭项目专用 CDP 浏览器”。

## 微信现状
- `wechat_query.py` 已接入关键字分流。
- 只要钉钉消息中包含 `微信`，就不查钉钉表格，直接走微信分支。
- 当前支持两个 provider:
  - `WECHAT_PROVIDER=gui`
    - 使用 Linux 桌面微信 + `xdotool/wmctrl/xclip` 自动化
    - 支持两种打开会话策略:
      - `WECHAT_GUI_OPEN_MODE=search`
        - 默认值，始终通过微信搜索打开目标群，稳定但略慢
      - `WECHAT_GUI_OPEN_MODE=sidebar_recent`
        - 适合目标群已置顶或稳定出现在左侧最近会话列表
        - 可配 `WECHAT_GUI_RECENT_CHAT_POINTS=群名=x,y;另一个群=x,y`
        - 如果 OCR 没找到群名，会回退到这里配置的固定坐标
  - `WECHAT_PROVIDER=gewechat`
    - 通过 Gewechat HTTP API 发消息，不依赖桌面微信
    - 需要配置 `GEWECHAT_BASE_URL / GEWECHAT_TOKEN / GEWECHAT_APP_ID / GEWECHAT_CHAT_WXID`
- 当前微信分支默认只负责发送。
- `gewechat_webhook.py` 已提供最小 webhook 接收器，会把回调原始事件落到 `tmp/gewechat-callback-events.jsonl`。
- 因此微信能力当前状态是“已完成 provider 抽象，GUI 可发，Gewechat 可接入发送，回读链路待按真实回调格式联调”。

## Gewechat 接入说明
1. 部署 Gewechat 服务，拿到本地 API 地址。
   - 例如 `http://127.0.0.1:2531/v2/api`
2. 拿到登录后的 `token` 和 `appId`。
3. 找到目标群的 `wxid`，以及被 @ 对象的 `wxid`。
4. 启动本项目 webhook 接收器。
   - `python3 gewechat_webhook.py --host 0.0.0.0 --port 8788`
5. 在 `.env` 中配置：
   - `WECHAT_PROVIDER=gewechat`
   - `GEWECHAT_BASE_URL=...`
   - `GEWECHAT_TOKEN=...`
   - `GEWECHAT_APP_ID=...`
   - `GEWECHAT_REGION_ID=...`
   - `GEWECHAT_PROXY_IP=...`
   - `GEWECHAT_USERNAME=...`
   - `GEWECHAT_CHAT_WXID=...`
   - `GEWECHAT_AT_WXID=...`
   - `GEWECHAT_CALLBACK_URL=http://<本机内网地址>:8788`
     - 优先用 Gewechat 服务可直连的内网地址，不要先用公网地址
6. 之后钉钉消息里只要包含 `微信 <单号>`，就会走 Gewechat 发送分支。

## Gewechat 首次登录
1. 启动 Gewechat 服务和本项目 webhook。
2. 执行：
   - `python3 gewechat_bootstrap.py`
3. 脚本会自动：
   - 调 `getTokenId`
   - 调 `getLoginQrCode`
   - 输出 `app_id / uuid / qr_url`
   - 轮询 `checkLogin`
   - 登录成功后把 `GEWECHAT_TOKEN / GEWECHAT_APP_ID` 写回 `.env`
   - 自动调用 `setCallback`
4. 如果 `getLoginQrCode` 返回“创建设备失败”：
   - 先补 `GEWECHAT_REGION_ID`
   - 如需走指定代理，再补 `GEWECHAT_PROXY_IP`
   - 如果当前网络无法连设备节点，优先切换到稳定的中国大陆网络，最好与手机同省

## Windows 运行约定
- 统一本地 API 端口: `18081`
- 统一本地 CDP 端口: `19444`
- API 和机器人统一连接同一套 CDP 浏览器；`LOCAL_CDP_EXTERNAL_ONLY=true` 时，业务进程不会再自行启动第二个浏览器
- `LOCAL_CDP_STOP_WHEN_IDLE=false` 时查询结束后保留共享浏览器；改成 `true` 才会在所有会话结束后自动关闭
- Windows 启动脚本会优先复用 `LOCAL_CDP_URL`，不可用时用系统 Chrome/Edge 启动共享 CDP，不再自动选择 Playwright 的 `Google for Testing`
- Windows 配置模板: `.env.windows.example`
- Windows 启动脚本会优先读取 `.env.windows`，再回退到 `.env`
- Windows 启动: 直接双击 `start_all.bat`（同时启动 API 和机器人）
- `start_all.bat` 会在同一个终端聚合 API 和机器人日志，日志前缀分别为 `[api]`、`[bot]`
- Windows 主执行环境继续优先承载 `QQ / NapCat / Windows Playwright` 相关能力。

## 公网 API 网关方案
- 推荐架构:
  - 阿里云服务器只部署 Docker 网关
  - 本机继续运行 `api_server.py` 和浏览器自动化查询
  - 优先通过 Tailscale 让服务器直连本机 API
  - 反向 SSH 隧道仅作为备用链路，把 `127.0.0.1:18081` 转发到云主机 `127.0.0.1:18781`
  - Docker 网关优先转发到 Tailscale 上游，必要时再切回本地隧道端口
- 网关修改 `deploy/gateway/.env` 后，必须执行
  `docker compose --env-file deploy/gateway/.env -f deploy/docker-compose.gateway.yml up -d --force-recreate --no-build logistics-query-gateway`
  才会让新上游地址进入容器环境。
- 参考文档:
  - `docs/deployment-public-api-gateway.md`
- 关键端口:
  - 公网网关: `18743`
  - 云主机本地隧道: `18781`
  - 本机 API: `18081`

## USPS 风控应对
- USPS 查询不要用 headless；优先复用宿主 Chrome 的默认 context，避免空 cookie/context 触发 Akamai 风控。
- 首次使用时，可在共享 Chrome 中手动打开 `usps.com` / `tools.usps.com`，保存 cookie 和本地存储。
- USPS 被拦或最终失败时，会把调试文件写到 `tmp/usps-debug/<日期>/<单号>/attempt-*/`。
- 调试目录至少包含 `dom.html`、`screenshot.png`、`url.txt`、`title.txt`，先看这些再决定是否继续调 stealth。

## 当前代码里的真实平台枚举
- `auto`
- `agl`
- `meitong`
- `pingyi`
- `baosen`
- `qq`
- `17track`
- `yinghe`
- `none`
