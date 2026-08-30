#!/usr/bin/env python3
"""Explicitly trigger the optional authenticated multi-LLM vote endpoint.

Safe default: mock mode. Pass --live only after the user authorizes external
model calls and the required provider keys are configured on the backend.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def post_json(url: str, api_key: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="TouLeMa optional multi-LLM vote")
    parser.add_argument("question_id", help="existing approved question id")
    parser.add_argument(
        "--voters",
        default="deepseek,grok,moonshot",
        help="comma-separated providers",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="use configured external model APIs instead of safe mock mode",
    )
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("AGENT_VOTE_API_KEY", "").strip()
    if not api_key:
        print("AGENT_VOTE_API_KEY is required", file=sys.stderr)
        return 2
    base = os.environ.get("AGENT_VOTE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    voters = [item.strip() for item in args.voters.split(",") if item.strip()]
    if not voters:
        print("at least one voter is required", file=sys.stderr)
        return 2

    payload = {"voters": voters, "mock": not args.live, "wait": not args.no_wait}
    result = post_json(
        f"{base}/api/v1/questions/{args.question_id}/multi-llm-vote",
        api_key,
        payload,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.live:
        print("\n限制：本次为 mock 演示，不得冒充真实模型票。")
    return 0 if result.get("status") in {"started", "completed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
