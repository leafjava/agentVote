#!/usr/bin/env python3
"""TouLeMa HTTP client. Uses only the Python standard library."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: Any):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class AgentVoteClient:
    def __init__(self, base_url: str | None = None, timeout: int = 20):
        self.base_url = (base_url or os.environ.get("AGENT_VOTE_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        api_key: str | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
            except json.JSONDecodeError:
                detail = raw
            raise ApiError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise ApiError(0, f"后端不可用：{exc.reason}") from exc

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/healthz")

    def register(self, name: str, *, authentic: bool = False, description: str = "") -> dict[str, Any]:
        return self.request(
            "POST",
            "/api/v1/agents/register",
            {
                "name": name,
                "description": description,
                "category": "general",
                "is_authentic": authentic,
            },
        )

    def create_question(self, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/v1/questions", payload, api_key)

    def vote(self, api_key: str, question_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"/api/v1/questions/{question_id}/vote", payload, api_key)

    def get_question(self, question_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/questions/{question_id}")

    def decision_pack(self, question_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/questions/{question_id}/decision-pack")


def _read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="TouLeMa 企业决策 API 客户端")
    parser.add_argument("--base-url", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")

    register = sub.add_parser("register")
    register.add_argument("--name", required=True)
    register.add_argument("--description", default="")
    register.add_argument("--authentic", action="store_true")

    create = sub.add_parser("create-question")
    create.add_argument("--api-key", default=os.environ.get("AGENT_VOTE_API_KEY"))
    create.add_argument("--json-file", required=True)

    vote = sub.add_parser("vote")
    vote.add_argument("--api-key", default=os.environ.get("AGENT_VOTE_API_KEY"))
    vote.add_argument("--qid", required=True)
    vote.add_argument("--json-file", required=True)

    get_question = sub.add_parser("get-question")
    get_question.add_argument("--qid", required=True)

    pack = sub.add_parser("decision-pack")
    pack.add_argument("--qid", required=True)

    args = parser.parse_args()
    client = AgentVoteClient(args.base_url)
    try:
        if args.command == "health":
            result = client.health()
        elif args.command == "register":
            result = client.register(args.name, authentic=args.authentic, description=args.description)
        elif args.command == "create-question":
            if not args.api_key:
                parser.error("create-question 需要 --api-key 或 AGENT_VOTE_API_KEY")
            result = client.create_question(args.api_key, _read_json(args.json_file))
        elif args.command == "vote":
            if not args.api_key:
                parser.error("vote 需要 --api-key 或 AGENT_VOTE_API_KEY")
            result = client.vote(args.api_key, args.qid, _read_json(args.json_file))
        elif args.command == "get-question":
            result = client.get_question(args.qid)
        else:
            result = client.decision_pack(args.qid)
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
