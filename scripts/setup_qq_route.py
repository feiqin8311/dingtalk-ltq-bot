#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_DIR / ".env"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from qq_query import NapCatOneBotClient, clean_text


def preload_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


preload_env()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="发现 QQ 群和成员，并可写回 .env")
    parser.add_argument("--group-name", default="璧久FBA海运-杭州金为", help="目标群名称")
    parser.add_argument("--user-name", default="李美慧", help="目标成员名称")
    parser.add_argument("--base-url", default=os.environ.get("QQ_API_BASE_URL", "http://127.0.0.1:6702"))
    parser.add_argument("--token", default=os.environ.get("QQ_API_TOKEN", ""))
    parser.add_argument("--env-file", default=".env", help="要写入的 env 文件")
    parser.add_argument("--write-env", action="store_true", help="将发现的群号和成员号写回 env 文件")
    return parser.parse_args()


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    lines = []
    existing = {}
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, _ = line.split("=", 1)
            existing[key.strip()] = idx

    for key, value in updates.items():
        rendered = f"{key}={value}"
        if key in existing:
            lines[existing[key]] = rendered
        else:
            lines.append(rendered)

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    client = NapCatOneBotClient(
        base_url=args.base_url,
        token=args.token,
        timeout_seconds=15,
    )

    groups = client.get_group_list()
    target_group_name = clean_text(args.group_name)
    matched_groups = [group for group in groups if clean_text(group.get("group_name", "")) == target_group_name]
    if not matched_groups:
        raise SystemExit(f"未找到目标QQ群: {target_group_name}")
    if len(matched_groups) > 1:
        raise SystemExit(f"找到多个同名QQ群，请手动指定群号: {target_group_name}")

    group_id = int(matched_groups[0]["group_id"])
    members = client.get_group_member_list(group_id)
    target_user_name = clean_text(args.user_name)
    matched_users = []
    for member in members:
        candidates = {
            clean_text(member.get("card", "")),
            clean_text(member.get("nickname", "")),
        }
        if target_user_name in candidates:
            matched_users.append(member)

    if not matched_users:
        raise SystemExit(f"群 {group_id} 中未找到成员: {target_user_name}")
    if len(matched_users) > 1:
        raise SystemExit(f"群 {group_id} 中存在多个同名成员，请手动指定成员 QQ 号")

    user = matched_users[0]
    user_id = int(user["user_id"])
    display_name = clean_text(user.get("card") or user.get("nickname") or target_user_name)

    print(f"QQ_JINWEI_GROUP_NAME={target_group_name}")
    print(f"QQ_JINWEI_GROUP_ID={group_id}")
    print(f"QQ_JINWEI_USER_NAME={display_name}")
    print(f"QQ_JINWEI_USER_ID={user_id}")

    if args.write_env:
        env_path = Path(args.env_file).expanduser()
        upsert_env(
            env_path,
            {
                "QQ_JINWEI_GROUP_NAME": target_group_name,
                "QQ_JINWEI_GROUP_ID": str(group_id),
                "QQ_JINWEI_USER_NAME": display_name,
                "QQ_JINWEI_USER_ID": str(user_id),
            },
        )
        print(f"已写入 {env_path}")


if __name__ == "__main__":
    main()
