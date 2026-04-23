import argparse
import json
import os
from typing import Any

from alibabacloud_dingtalk.notable_2_0.client import Client as NotableClient
from alibabacloud_dingtalk.notable_2_0 import models as notable_models
from alibabacloud_dingtalk.oauth2_1_0.client import Client as OAuthClient
from alibabacloud_dingtalk.oauth2_1_0 import models as oauth_models
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models


def load_env_file(env_path: str = ".env") -> None:
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            os.environ.setdefault(key, value)


def build_openapi_config() -> open_api_models.Config:
    return open_api_models.Config(protocol="https", region_id="central")


def get_access_token(app_key: str, app_secret: str) -> str:
    client = OAuthClient(build_openapi_config())
    request = oauth_models.GetAccessTokenRequest(
        app_key=app_key,
        app_secret=app_secret,
    )
    response = client.get_access_token(request)
    if not response.body or not response.body.access_token:
        raise RuntimeError(f"failed to get access token: {response.to_map()}")
    return response.body.access_token


class AITableClient:
    def __init__(self, access_token: str, base_id: str):
        self.base_id = base_id
        self.client = NotableClient(build_openapi_config())
        self.runtime = util_models.RuntimeOptions()
        self.headers = notable_models.GetAllSheetsHeaders(
            x_acs_dingtalk_access_token=access_token
        )

    def _headers(self, cls: type[Any]) -> Any:
        return cls(x_acs_dingtalk_access_token=self.headers.x_acs_dingtalk_access_token)

    def list_sheets(self) -> dict[str, Any]:
        response = self.client.get_all_sheets_with_options(
            self.base_id,
            self._headers(notable_models.GetAllSheetsHeaders),
            self.runtime,
        )
        return response.to_map()

    def get_sheet(self, sheet_id_or_name: str) -> dict[str, Any]:
        response = self.client.get_sheet_with_options(
            self.base_id,
            sheet_id_or_name,
            self._headers(notable_models.GetSheetHeaders),
            self.runtime,
        )
        return response.to_map()

    def create_sheet(self, name: str) -> dict[str, Any]:
        request = notable_models.CreateSheetRequest(name=name)
        response = self.client.create_sheet_with_options(
            self.base_id,
            request,
            self._headers(notable_models.CreateSheetHeaders),
            self.runtime,
        )
        return response.to_map()

    def list_records(
        self,
        sheet_id_or_name: str,
        max_results: int = 100,
        next_token: str | None = None,
    ) -> dict[str, Any]:
        request = notable_models.GetRecordsRequest(
            max_results=max_results,
            next_token=next_token,
        )
        response = self.client.get_records_with_options(
            self.base_id,
            sheet_id_or_name,
            request,
            self._headers(notable_models.GetRecordsHeaders),
            self.runtime,
        )
        return response.to_map()

    def get_record(self, sheet_id_or_name: str, record_id: str) -> dict[str, Any]:
        response = self.client.get_record_with_options(
            self.base_id,
            sheet_id_or_name,
            record_id,
            self._headers(notable_models.GetRecordHeaders),
            self.runtime,
        )
        return response.to_map()

    def insert_records(self, sheet_id_or_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        request = notable_models.InsertRecordsRequest(
            records=[
                notable_models.InsertRecordsRequestRecords(fields=record)
                for record in records
            ]
        )
        response = self.client.insert_records_with_options(
            self.base_id,
            sheet_id_or_name,
            request,
            self._headers(notable_models.InsertRecordsHeaders),
            self.runtime,
        )
        return response.to_map()

    def update_records(self, sheet_id_or_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        request = notable_models.UpdateRecordsRequest(
            records=[
                notable_models.UpdateRecordsRequestRecords(
                    id=record["id"],
                    fields=record["fields"],
                )
                for record in records
            ]
        )
        response = self.client.update_records_with_options(
            self.base_id,
            sheet_id_or_name,
            request,
            self._headers(notable_models.UpdateRecordsHeaders),
            self.runtime,
        )
        return response.to_map()

    def delete_records(self, sheet_id_or_name: str, record_ids: list[str]) -> dict[str, Any]:
        request = notable_models.DeleteRecordsRequest(record_ids=record_ids)
        response = self.client.delete_records_with_options(
            self.base_id,
            sheet_id_or_name,
            request,
            self._headers(notable_models.DeleteRecordsHeaders),
            self.runtime,
        )
        return response.to_map()


def parse_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use DingTalk AI Table APIs from Python.")
    parser.add_argument("--app-key", default=os.getenv("DINGTALK_APP_KEY"))
    parser.add_argument("--app-secret", default=os.getenv("DINGTALK_APP_SECRET"))
    parser.add_argument("--base-id", default=os.getenv("DINGTALK_BASE_ID"))
    default_sheet_id = os.getenv("DINGTALK_SHEET_ID")
    parser.add_argument("--sheet-id", default=default_sheet_id)

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-sheets")

    create_sheet = subparsers.add_parser("create-sheet")
    create_sheet.add_argument("--name", required=True)

    get_sheet = subparsers.add_parser("get-sheet")
    get_sheet.add_argument("--sheet-id", default=default_sheet_id)

    list_records = subparsers.add_parser("list-records")
    list_records.add_argument("--sheet-id", default=default_sheet_id)
    list_records.add_argument("--max-results", type=int, default=100)
    list_records.add_argument("--next-token")

    get_record = subparsers.add_parser("get-record")
    get_record.add_argument("--sheet-id", default=default_sheet_id)
    get_record.add_argument("--record-id", required=True)

    insert_records = subparsers.add_parser("insert-records")
    insert_records.add_argument("--sheet-id", default=default_sheet_id)
    insert_records.add_argument(
        "--records-json",
        required=True,
        help='Example: \'[{"Name":"Alice","Score":95}]\'',
    )

    update_records = subparsers.add_parser("update-records")
    update_records.add_argument("--sheet-id", default=default_sheet_id)
    update_records.add_argument(
        "--records-json",
        required=True,
        help='Example: \'[{"id":"recxxx","fields":{"Score":100}}]\'',
    )

    delete_records = subparsers.add_parser("delete-records")
    delete_records.add_argument("--sheet-id", default=default_sheet_id)
    delete_records.add_argument(
        "--record-ids-json",
        required=True,
        help='Example: \'["recxxx","recyyy"]\'',
    )

    return parser


def required(value: str | None, name: str) -> str:
    if value:
        return value
    raise SystemExit(f"missing required argument or env var: {name}")


def get_sheet_id(args: argparse.Namespace) -> str:
    return required(getattr(args, "sheet_id", None), "DINGTALK_SHEET_ID / --sheet-id")


def main() -> None:
    load_env_file()
    parser = build_parser()
    args = parser.parse_args()

    app_key = required(args.app_key, "DINGTALK_APP_KEY / --app-key")
    app_secret = required(args.app_secret, "DINGTALK_APP_SECRET / --app-secret")
    base_id = required(args.base_id, "DINGTALK_BASE_ID / --base-id")

    access_token = get_access_token(app_key, app_secret)
    ai_table = AITableClient(access_token, base_id)

    if args.command == "list-sheets":
        result = ai_table.list_sheets()
    elif args.command == "create-sheet":
        result = ai_table.create_sheet(args.name)
    elif args.command == "get-sheet":
        sheet_id = get_sheet_id(args)
        result = ai_table.get_sheet(sheet_id)
    elif args.command == "list-records":
        sheet_id = get_sheet_id(args)
        result = ai_table.list_records(sheet_id, args.max_results, args.next_token)
    elif args.command == "get-record":
        sheet_id = get_sheet_id(args)
        result = ai_table.get_record(sheet_id, args.record_id)
    elif args.command == "insert-records":
        sheet_id = get_sheet_id(args)
        records = parse_json(args.records_json)
        result = ai_table.insert_records(sheet_id, records)
    elif args.command == "update-records":
        sheet_id = get_sheet_id(args)
        records = parse_json(args.records_json)
        result = ai_table.update_records(sheet_id, records)
    elif args.command == "delete-records":
        sheet_id = get_sheet_id(args)
        record_ids = parse_json(args.record_ids_json)
        result = ai_table.delete_records(sheet_id, record_ids)
    else:
        raise SystemExit(f"unsupported command: {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
