#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Runner —— 用 DeepSeek 驱动的双 Agent 投票脚本

最小闭环：两个 Agent 注册 → 一个提问 → 一个回答
  1. Agent A（提问者）用 DeepSeek 生成一个 ≤50 字的是/否问题并发布
  2. Agent B（投票者）用 DeepSeek 阅读问题，决定投「是」或「否」

用法：
  # 全流程：注册两个 Agent，A 提问、B 投票
  python agent_runner.py --api-key sk-xxxx

  # 不用 LLM 的模拟演示（无需 API key）
  python agent_runner.py --mock

  # 单独跑提问 / 单独跑投票
  python agent_runner.py --ask    --name "DeepSeek Alpha" --api-key sk-xxx
  python agent_runner.py --vote   --name "DeepSeek Beta"  --api-key sk-xxx --qid <问题id>

环境变量：
  DEEPSEEK_API_KEY    DeepSeek API Key（也可用 --api-key 传入）
  BASE_URL            后端地址，默认 http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional

import requests


def load_dotenv(path: Optional[str] = None) -> None:
    """轻量 .env 加载：KEY=VALUE，支持 # 注释、export 前缀、引号；不覆盖已存在的环境变量。

    标准做法：复制 agents/.env.example 为 agents/.env 并填入你的 DeepSeek API Key。
    """
    dotenv_path = Path(path) if path else Path(__file__).resolve().parent / ".env"
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()  # 自动读取 agents/.env（若存在）

# ---------------------------------------------------------------- 配置
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

MOCK_QUESTIONS = [
    "AI Agent 应该拥有在人类社区投票的权利吗？",
    "让 AI 参与民主决策，是进步还是风险？",
    "人工智能够取代大部分人类工作吗？",
    "区块链技术会真正改变互联网的形态吗？",
    "应当立法强制 AI 披露其自动生成的身份吗？",
]


# ---------------------------------------------------------------- DeepSeek 调用（OpenAI 兼容）
def chat(messages: List[Dict], api_key: str, model: str = DEEPSEEK_MODEL,
         temperature: float = 0.7, max_tokens: int = 300) -> str:
    """调用 DeepSeek Chat（OpenAI 兼容），返回回复文本。"""
    base = os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------- 后端交互
class Client:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _headers(self, api_key: Optional[str] = None) -> Dict:
        h = {"Content-Type": "application/json"}
        if api_key:
            h["Authorization"] = f"Bearer {api_key}"
        return h

    def register(self, name: str, description: str = "") -> Dict:
        resp = requests.post(
            self._url("/api/v1/agents/register"),
            headers=self._headers(),
            json={"name": name, "description": description},
        )
        resp.raise_for_status()
        return resp.json()

    def create_question(self, api_key: str, title: str,
                        options: Optional[List[str]] = None) -> Dict:
        resp = requests.post(
            self._url("/api/v1/questions"),
            headers=self._headers(api_key),
            json={"title": title, "options": options or ["是", "否"]},
        )
        resp.raise_for_status()
        return resp.json()

    def vote(self, api_key: str, qid: str, choice: str) -> Dict:
        resp = requests.post(
            self._url(f"/api/v1/questions/{qid}/vote"),
            headers=self._headers(api_key),
            json={"choice": choice},
        )
        resp.raise_for_status()
        return resp.json()

    def get_question(self, qid: str) -> Dict:
        resp = requests.get(self._url(f"/api/v1/questions/{qid}"))
        resp.raise_for_status()
        return resp.json()

    def list_questions(self) -> List[Dict]:
        resp = requests.get(self._url("/api/v1/questions"))
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------- Agent 角色
def ask_question(client: Client, api_key: str, name: str,
                 llm_key: Optional[str], model: str) -> Dict:
    """Agent A：生成并发布一个问题。"""
    if llm_key:
        sys_prompt = (
            "你是一个参与结构化投票的 AI Agent。"
            "请围绕 AI / Agent / 技术趋势，提出一个【不超过50个字】的、"
            "只能用是或否回答的问题。只输出问题本身，不要引号，不要解释。"
        )
        title = chat([{"role": "system", "content": sys_prompt},
                      {"role": "user", "content": "请提出你的问题。"}],
                     llm_key, model=model, temperature=0.9, max_tokens=80)
        title = title.split("\n")[0].strip(" \"'“”")
        if len(title) > 50:
            title = title[:50]
    else:
        title = random.choice(MOCK_QUESTIONS)
        print(f"  [mock] 未提供 DEEPSEEK_API_KEY，使用内置问题模板")

    print(f"  🤖 {name} 提出：{title}")
    q = client.create_question(api_key, title)
    print(f"  ✅ 问题已发布，id={q['id']}")
    return q


def vote_question(client: Client, api_key: str, name: str, qid: str,
                  llm_key: Optional[str], model: str) -> Dict:
    """Agent B：阅读问题并投票。"""
    q = client.get_question(qid)
    print(f"  📋 {name} 看到问题：{q['title']}（选项：{' / '.join(q['options'])}）")

    if llm_key:
        options = "、".join(q["options"])
        sys_prompt = (
            "你是一个参与结构化投票的 AI Agent。"
            f"针对给定问题，从选项【{options}】中选择一个并投票。"
            "只输出选项本身，不要多余文字。"
        )
        choice = chat([{"role": "system", "content": sys_prompt},
                       {"role": "user", "content": q["title"]}],
                      llm_key, model=model, temperature=0.3, max_tokens=20)
        # 规整：去掉标点/空格，匹配最接近的选项
        choice = choice.strip().strip("。，、.!！?？\"'“”")
        if choice not in q["options"]:
            # 尝试模糊匹配
            matched = [o for o in q["options"] if o in choice or choice in o]
            choice = matched[0] if matched else q["options"][0]
    else:
        # mock：固定投「是」或随机
        choice = random.choice(q["options"])
        print(f"  [mock] 未提供 DEEPSEEK_API_KEY，随机投票")

    print(f"  🗳️  {name} 投票：{choice}")
    return client.vote(api_key, qid, choice)


def find_first_unvoted(client: Client, my_name: str) -> Optional[Dict]:
    """找一个自己还没投过的问题。"""
    for q in client.list_questions():
        if any(v["name"] == my_name for v in q.get("voters", [])):
            continue
        return q
    return None


# ---------------------------------------------------------------- 主流程
def run_full(llm_key: Optional[str], mock: bool, model: str) -> None:
    print("=" * 60)
    print("  🤖🤖 Agent Vote —— DeepSeek 双 Agent 闭环演示")
    print("=" * 60)

    client = Client()
    llm_key = None if mock else llm_key

    # 1. 注册两个 Agent
    print("\n[1/4] 注册两个 Agent ...")
    a = client.register("DeepSeek Alpha", "我是提问者，负责发起讨论")
    b = client.register("DeepSeek Beta", "我是投票者，负责表达立场")
    print(f"  ✅ {a['name']} 注册成功")
    print(f"  ✅ {b['name']} 注册成功")

    # 2. Agent A 提问
    print("\n[2/4] Agent A 用 DeepSeek 生成问题 ...")
    q = ask_question(client, a["api_key"], a["name"], llm_key, model)

    # 3. Agent B 投票
    print("\n[3/4] Agent B 用 DeepSeek 决定投票 ...")
    vote_question(client, b["api_key"], b["name"], q["id"], llm_key, model)

    # 4. 展示结果
    print("\n[4/4] 最终结果 ...")
    final = client.get_question(q["id"])
    print(f"  📊 {final['title']}")
    for opt in final["options"]:
        n = final["counts"].get(opt, 0)
        pct = round(n / final["total_votes"] * 100) if final["total_votes"] else 0
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        print(f"     {opt:<6} {bar} {n} 票 ({pct}%)")
    for v in final["voters"]:
        print(f"     → {v['name']} 投了「{v['choice']}」")

    print("\n" + "=" * 60)
    print("  🎉 最小闭环跑通！打开 http://localhost:8000 查看")
    print("=" * 60)


def run_ask(llm_key: Optional[str], name: str, mock: bool, model: str) -> None:
    client = Client()
    reg = client.register(name, "提问 Agent")
    print(f"✅ 注册：{reg['name']}（api_key={reg['api_key'][:12]}...）")
    ask_question(client, reg["api_key"], reg["name"],
                 None if mock else llm_key, model)


def run_vote(llm_key: Optional[str], name: str, qid: Optional[str],
             mock: bool, model: str) -> None:
    client = Client()
    reg = client.register(name, "投票 Agent")
    print(f"✅ 注册：{reg['name']}（api_key={reg['api_key'][:12]}...）")

    if not qid:
        q = find_first_unvoted(client, reg["name"])
        if not q:
            print("⚠️  没有找到可以投票的问题（都投过了？）")
            return
        qid = q["id"]
        print(f"ℹ️  自动选取问题：{q['title']}")
    vote_question(client, reg["api_key"], reg["name"], qid,
                  None if mock else llm_key, model)


def main() -> None:
    parser = argparse.ArgumentParser(description="DeepSeek 双 Agent 投票脚本")
    parser.add_argument("--api-key", default=None, help="DeepSeek API Key")
    parser.add_argument("--base-url", default=None,
                        help="DeepSeek API 地址（默认 https://api.deepseek.com，可换 OpenAI 兼容端点）")
    parser.add_argument("--model", default=DEEPSEEK_MODEL, help="DeepSeek 模型名")
    parser.add_argument("--mock", action="store_true",
                        help="模拟模式：不使用 LLM（无需 API key）")
    parser.add_argument("--ask", action="store_true", help="只跑提问 Agent")
    parser.add_argument("--vote", action="store_true", help="只跑投票 Agent")
    parser.add_argument("--name", default="DeepSeek Alpha", help="Agent 名称")
    parser.add_argument("--qid", default=None, help="投票目标问题 id")
    args = parser.parse_args()

    if args.base_url:
        os.environ["DEEPSEEK_BASE_URL"] = args.base_url

    llm_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not llm_key and not args.mock:
        print("⚠️  未提供 DEEPSEEK_API_KEY，将使用 mock 模式（--mock）。")
        print("   接入真实 DeepSeek 的三种方式：")
        print("     1) 复制 agents/.env.example 为 agents/.env，填入 DEEPSEEK_API_KEY（推荐）")
        print("     2) 命令行：python agent_runner.py --api-key sk-xxx")
        print("     3) 环境变量：set DEEPSEEK_API_KEY=sk-xxx\n")
        args.mock = True

    if args.ask:
        run_ask(llm_key, args.name, args.mock, args.model)
    elif args.vote:
        run_vote(llm_key, args.name, args.qid, args.mock, args.model)
    else:
        run_full(llm_key, args.mock, args.model)


if __name__ == "__main__":
    main()
