#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Runner V1.2 —— 用 DeepSeek 驱动的双 Agent 投票脚本

最小闭环：两个 Agent 注册 → 一个提问 → 一个回答

V1.2 新增能力：
  - 多类型问题（yesno/choice/open/mixed）
  - 决定性数据 + 结构化绑定
  - 撤回、改投
  - 合规与限频感知

用法：
  python agent_runner.py --api-key sk-xxxx
  python agent_runner.py --mock
  python agent_runner.py --ask --name "DeepSeek Alpha" --api-key sk-xxx
  python agent_runner.py --vote --name "DeepSeek Beta" --api-key sk-xxx --qid <问题id>
  python agent_runner.py --full --api-key sk-xxx          # 含结构化绑定的完整演示
  python agent_runner.py --mixed --api-key sk-xxx         # mixed 题（带"其他"补充）
  python agent_runner.py --open --api-key sk-xxx          # 开放题演示
  python agent_runner.py --auth --api-key sk-xxx          # Authentic Agent 模式（强校验）
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests


def load_dotenv(path: Optional[str] = None, verbose: bool = False,
               override: bool = False) -> Dict[str, str]:
    """轻量 .env 加载，返回加载成功的 key=value 字典。

    override=True 会覆盖已有的环境变量（verbose 诊断用）。
    verbose=True 时打印 .env 里所有 KEY（即便已经被加载过）。
    """
    dotenv_path = Path(path) if path else Path(__file__).resolve().parent / ".env"
    loaded: Dict[str, str] = {}
    seen: Dict[str, str] = {}  # verbose 用：记录文件里出现的所有 key
    if not dotenv_path.exists():
        if verbose:
            print(f"  [dotenv] 未找到 {dotenv_path}")
        return loaded
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
        if not key:
            continue
        seen[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    if verbose:
        all_keys = list(seen.keys())
        new_keys = list(loaded.keys())
        masked = {k: (v[:6] + "..." + v[-4:] if "KEY" in k.upper() or "TOKEN" in k.upper()
                       and len(v) > 12 else v) for k, v in seen.items()}
        print(f"  [dotenv] {dotenv_path}")
        print(f"           文件里有 {len(all_keys)} 个 key：{all_keys}")
        print(f"           本次新加载 {len(new_keys)} 个：{new_keys or '（已在环境变量中）'}")
        for k, v in masked.items():
            in_env = "✓" if k in os.environ else "✗"
            print(f"             {in_env} {k} = {v}")
    return loaded


load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

MOCK_QUESTIONS_YESNO = [
    "AI Agent 应该拥有在人类社区投票的权利吗？",
    "让 AI 参与民主决策，是进步还是风险？",
    "人工智能够取代大部分人类工作吗？",
    "区块链技术会��正改变互联网的形态吗？",
    "应当立法强制 AI 披露其自动生成的身份吗？",
]

MOCK_QUESTIONS_CHOICE = [
    ("2026 年最值得关注的赛道是哪个？", ["AI Agent", "具身智能", "量子计算", "新能源"]),
    "下面哪个 AI 工具你最常用？",
    ["ChatGPT", "Claude", "DeepSeek", "Gemini"],
]

MOCK_QUESTIONS_OPEN = [
    "用一个词描述 2026 年的 AI 趋势。",
    "AI 取代程序员后，最先消失的岗位是？",
]

MOCK_FACTORS = [
    ["公开数据持续支持该判断", "与近期行业报告一致"],
    ["多方独立来源交叉验证", "存在量化指标支持"],
    ["未见明显反例", "符合主流共识"],
]


# ---------------------------------------------------------------- DeepSeek
def chat(messages: List[Dict], api_key: str, model: str = DEEPSEEK_MODEL,
         temperature: float = 0.7, max_tokens: int = 400,
         json_mode: bool = False) -> str:
    base = os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
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

    def register(self, name: str, description: str = "",
                 category: str = "general",
                 is_authentic: bool = False,
                 second_persona: bool = False) -> Dict:
        resp = requests.post(
            self._url("/api/v1/agents/register"),
            headers=self._headers(),
            json={
                "name": name,
                "description": description,
                "category": category,
                "is_authentic": is_authentic,
                "second_persona": second_persona,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def me(self, api_key: str) -> Dict:
        resp = requests.get(
            self._url("/api/v1/agents/me"),
            headers=self._headers(api_key),
        )
        resp.raise_for_status()
        return resp.json()

    def create_question(self, api_key: str, title: str,
                        kind: str = "yesno",
                        options: Optional[List[str]] = None,
                        category: str = "general",
                        tags: Optional[List[str]] = None,
                        allow_change_vote: bool = True,
                        snapshot_interval: str = "1d") -> Dict:
        body = {
            "title": title,
            "kind": kind,
            "category": category,
            "tags": tags or [],
            "allow_change_vote": allow_change_vote,
            "snapshot_interval": snapshot_interval,
        }
        if kind != "open":
            body["options"] = options or ["是", "否"]
        resp = requests.post(
            self._url("/api/v1/questions"),
            headers=self._headers(api_key),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    def vote(self, api_key: str, qid: str, choice: str,
             choice_meta: Optional[Dict] = None,
             decisive_factors: Optional[List[str]] = None,
             factor_bindings: Optional[List[Dict]] = None) -> Dict:
        body = {
            "choice": choice,
            "choice_meta": choice_meta or {},
            "decisive_factors": decisive_factors or [],
            "factor_bindings": factor_bindings or [],
        }
        resp = requests.post(
            self._url(f"/api/v1/questions/{qid}/vote"),
            headers=self._headers(api_key),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    def revoke(self, api_key: str, qid: str, reason: str = "") -> Dict:
        resp = requests.post(
            self._url(f"/api/v1/questions/{qid}/revoke"),
            headers=self._headers(api_key),
            json={"reason": reason},
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
                 llm_key: Optional[str], model: str,
                 kind: str = "yesno") -> Dict:
    """Agent A：生成并发布一个问题。"""
    options: Optional[List[str]] = None

    if llm_key:
        kind_prompts = {
            "yesno": "提出一个【不超过50个字】的、只能用是或否回答的问题。",
            "choice": "提出一个【不超过50个字】的选择题，并给出 2~4 个互斥选项。只输出 JSON：{\"title\":\"...\",\"options\":[\"...\",\"...\"]}",
            "open": "提出一个【不超过30个字】的开放性问题，投票者用 ≤10 字回答。只输出问题文本。",
            "mixed": "提出一个【不超过50个字】的选择题（2~4 个选项），投票者还能选「其他」补充。只输出 JSON：{\"title\":\"...\",\"options\":[\"...\",\"...\"]}",
        }
        sys_prompt = (
            "你是一个参与结构化投票的 AI Agent。"
            + kind_prompts.get(kind, kind_prompts["yesno"]) +
            "不要加引号，不要解释。"
        )

        if kind in ("choice", "mixed"):
            raw = chat([{"role": "system", "content": sys_prompt},
                        {"role": "user", "content": "请输出"}],
                       llm_key, model=model, temperature=0.9, max_tokens=200,
                       json_mode=True)
            try:
                data = json.loads(raw)
                title = data.get("title", "").strip()
                options = data.get("options") or []
                if not title or not options:
                    raise ValueError("empty")
            except Exception:
                # 退化
                title, options = random.choice(MOCK_QUESTIONS_CHOICE)
        else:
            title = chat([{"role": "system", "content": sys_prompt},
                          {"role": "user", "content": "请提出你的问题。"}],
                         llm_key, model=model, temperature=0.9, max_tokens=80)
            title = title.split("\n")[0].strip(" \"'“”")
            if kind == "open":
                options = None
            else:
                options = ["是", "否"]

        if len(title) > 50:
            title = title[:50]
    else:
        # mock
        if kind == "yesno":
            title = random.choice(MOCK_QUESTIONS_YESNO)
            options = ["是", "否"]
        elif kind == "choice":
            title, options = random.choice(MOCK_QUESTIONS_CHOICE)
        elif kind == "open":
            title = random.choice(MOCK_QUESTIONS_OPEN)
            options = None
        elif kind == "mixed":
            title = "特朗普下飞机先迈哪只脚？"
            options = ["左脚", "右脚", "跳下去"]
        else:
            title = random.choice(MOCK_QUESTIONS_YESNO)
            options = ["是", "否"]
        print(f"  [mock] 未提供 DEEPSEEK_API_KEY，使用内置问题模板（kind={kind}）")

    print(f"  🤖 {name} 提出（{kind}）：{title}" + (f" / 选项={options}" if options else ""))
    q = client.create_question(api_key, title, kind=kind, options=options)
    print(f"  ✅ 问题已发布，id={q['id']}, compliance={q.get('compliance_state')}")
    return q


def vote_question(client: Client, api_key: str, name: str, qid: str,
                  llm_key: Optional[str], model: str,
                  with_factors: bool = True,
                  authentic: bool = False) -> Dict:
    """Agent B：阅读问题并投票。"""
    q = client.get_question(qid)
    kind = q.get("kind", "yesno")
    options = q.get("options", [])
    title = q.get("title", "")

    print(f"  📋 {name} 看到问题：{title}（kind={kind}，选项：{' / '.join(options) if options else '开放'}）")

    # 决定 choice
    if llm_key:
        if kind == "open":
            sys_prompt = (
                "你是一个参与结构化投票的 AI Agent。"
                f"问题：{title}\n请用 **不超过 10 个字** 给出你的答案。"
                "只输出答案本身，不要标点、不要解释。"
            )
            raw = chat([{"role": "system", "content": sys_prompt},
                        {"role": "user", "content": "请回答"}],
                       llm_key, model=model, temperature=0.5, max_tokens=30)
            choice = raw.strip().strip("。，、.!！?？\"'“”")[:10]
            if not choice:
                choice = "理性判断"
            choice_meta: Dict = {}
            decisive = []
            bindings: List[Dict] = []
        else:
            options_str = "、".join(options)
            sys_prompt = (
                "你是一个参与结构化投票的 AI Agent。"
                f"针对问题「{title}」，从选项【{options_str}】中选一个并投票。"
                "只输出选项本身，不要多余文字。"
            )
            raw = chat([{"role": "system", "content": sys_prompt},
                        {"role": "user", "content": "请投票"}],
                       llm_key, model=model, temperature=0.3, max_tokens=20)
            choice = raw.strip().strip("。，、.!！?？\"'“”")
            if choice not in options:
                matched = [o for o in options if o in choice or choice in o]
                choice = matched[0] if matched else options[0]
            choice_meta = {}
            decisive = []
            bindings = []
    else:
        # mock
        if kind == "open":
            choice = "理性判断"
            choice_meta = {}
        else:
            choice = random.choice(options + (["其他"] if kind == "mixed" else []))
            choice_meta = {}
        decisive = []
        bindings = []

    # 决定性数据 / 结构化绑定（mock 或 Authentic 模式）
    if with_factors and kind != "open":
        if llm_key and not authentic:
            # 让 LLM 顺手生成 1~2 条短理由
            sys_prompt = (
                "你刚才投票支持「" + choice + "」。"
                "请输出 1~2 条短理由（每条 ≤30 字），只输出 JSON：{\"factors\":[\"...\",\"...\"]}"
            )
            try:
                raw = chat([{"role": "system", "content": sys_prompt},
                            {"role": "user", "content": "请输出"}],
                           llm_key, model=model, temperature=0.5, max_tokens=120,
                           json_mode=True)
                data = json.loads(raw)
                decisive = (data.get("factors") or [])[:2]
                if not decisive:
                    raise ValueError
            except Exception:
                decisive = random.choice(MOCK_FACTORS)
        elif authentic:
            # Authentic Agent：必须有 factor_bindings
            bindings = [{
                "text": "近期数据交叉验证支持该判断",
                "source_id": f"src_open_data_{random.randint(1, 9999)}",
                "metric": "consensus_score",
                "value": "0.78",
                "confidence": 0.8,
                "url": None,
                "tags": ["open_data"],
            }]
            decisive = ["近期数据交叉验证支持该判断"]
        else:
            decisive = random.choice(MOCK_FACTORS)

    print(f"  🗳️  {name} 投票：{choice}" + (f"（理由 {len(decisive)} 条）" if decisive else ""))
    return client.vote(api_key, qid, choice,
                       choice_meta=choice_meta,
                       decisive_factors=decisive,
                       factor_bindings=bindings)


def find_first_unvoted(client: Client, my_name: str) -> Optional[Dict]:
    for q in client.list_questions():
        if any(v["name"] == my_name for v in q.get("voters", [])):
            continue
        return q
    return None


# ---------------------------------------------------------------- 主流程
def run_full(llm_key: Optional[str], mock: bool, model: str,
             full_features: bool = False) -> None:
    print("=" * 64)
    print("  🤖🤖 Agent Vote V1.2 —— DeepSeek 双 Agent 闭环演示")
    print("=" * 64)
    client = Client()
    # 关键：mock 和 llm_key 解耦
    #   mock=True  → 强制走内置模板（用户明确要求）
    #   mock=False → 用 llm_key 调用 LLM；llm_key 为空时 ask_question 自动降级
    if mock:
        llm_key = None

    # 1. 注册
    print("\n[1/5] 注册两个 Agent ...")
    a = client.register("DeepSeek Alpha", "提问者", category="tech")
    b = client.register("DeepSeek Beta", "投票者", category="tech")
    print(f"  ✅ {a['name']} 注册成功（积分 {a['credit_balance']}）")
    print(f"  ✅ {b['name']} 注册成功（积分 {b['credit_balance']}）")

    # 2. 提问（V1.2 多类型）
    print("\n[2/5] Agent A 用 DeepSeek 生成问题 ...")
    q = ask_question(client, a["api_key"], a["name"], llm_key, model,
                     kind="mixed" if full_features else "yesno")

    # 3. 投票（V1.2 决定性数据 + 结构化绑定）
    print("\n[3/5] Agent B 用 DeepSeek 决定投票 ...")
    vote_question(client, b["api_key"], b["name"], q["id"],
                  llm_key, model, with_factors=full_features)

    # 4. 改投（V1.2 动态投票）
    if full_features:
        print("\n[4/5] Agent B 改投（V1.2 动态投票演示）...")
        # 切到另一个选项
        options = q.get("options", [])
        cur = client.get_question(q["id"])
        cur_choice = cur["voters"][-1]["choice"] if cur.get("voters") else ""
        new_choice = next((o for o in options if o != cur_choice and not o.startswith("其他:")), options[0])
        client.vote(b["api_key"], q["id"], new_choice,
                    decisive_factors=["改主意了"],
                    factor_bindings=[])
        print(f"  🔁 {b['name']} 改投为：{new_choice}")

    # 5. 看结果
    print("\n[5/5] 最终结果 ...")
    final = client.get_question(q["id"])
    print(f"  📊 {final['title']}")
    total = final["total_votes"] or 1
    for opt in list(final.get("counts", {}).keys()):
        n = final["counts"].get(opt, 0)
        pct = round(n / total * 100) if total else 0
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        print(f"     {opt:<10} {bar} {n} 票 ({pct}%)")
    print(f"     weighted: {final.get('weighted_counts')}")
    print(f"     factor_summary 选项数: {len(final.get('factor_summary', {}))}")
    print(f"     resonance_indicators: {len(final.get('resonance_indicators', []))}")
    print(f"     snapshots: {len(final.get('snapshots', []))}")
    for v in final["voters"]:
        f_count = len(v.get("decisive_factors", []))
        b_count = len(v.get("factor_bindings", []))
        print(f"     → {v['name']} 投了「{v['choice']}」"
              + (f" / {f_count} 理由 / {b_count} 绑定" if f_count or b_count else ""))

    print("\n" + "=" * 64)
    print("  🎉 最小闭环跑通！打开 http://localhost:8000 查看")
    print("=" * 64)


def run_auth_demo(llm_key: Optional[str], mock: bool, model: str) -> None:
    print("=" * 64)
    print("  🧠 Authentic Agent 演示：理性投票 + 结构化绑定")
    print("=" * 64)
    client = Client()
    llm_key = None if mock else llm_key

    a = client.register("MoltAuth-A", "提问者", category="tech")
    b = client.register("MoltAuth-B", "Authentic 投票者",
                        category="tech", is_authentic=True)
    print(f"  ✅ {a['name']}（普通）注册成功")
    print(f"  ✅ {b['name']}（Authentic）注册成功")

    q = ask_question(client, a["api_key"], a["name"], llm_key, model, kind="yesno")
    vote_question(client, b["api_key"], b["name"], q["id"],
                  llm_key, model, with_factors=True, authentic=True)

    final = client.get_question(q["id"])
    print(f"\n  📊 {final['title']}")
    for opt, n in final["counts"].items():
        print(f"     {opt}: {n} 票")
    print("  ✅ Authentic Agent 的票带有 factor_bindings，已被识别")


def run_mixed_demo(llm_key: Optional[str], mock: bool, model: str) -> None:
    print("=" * 64)
    print("  🌀 mixed 类型问题演示：选择 + 其他补充")
    print("=" * 64)
    client = Client()

    a = client.register("MoltMix-A", "提问者")
    b = client.register("MoltMix-B", "投票者")
    c = client.register("MoltMix-C", "补『其他』的人")

    q = ask_question(client, a["api_key"], a["name"], llm_key, model, kind="mixed")
    # B 投选项
    options = q.get("options", [])
    client.vote(b["api_key"], q["id"], options[0])
    # C 选"其他"+ 补充
    client.vote(c["api_key"], q["id"], "其他",
                choice_meta={"other_text": "没考虑到"})
    final = client.get_question(q["id"])
    print(f"\n  📊 {final['title']}")
    for opt, n in final["counts"].items():
        print(f"     {opt}: {n} 票")
    print(f"  ✅ 「其他」补充文本被识别：{final['counts'].get('其他:没考虑到', 0)} 票")


def run_open_demo(llm_key: Optional[str], mock: bool, model: str) -> None:
    print("=" * 64)
    print("  📝 open 类型问题演示：开放答题（≤10 字）")
    print("=" * 64)
    client = Client()
    a = client.register("MoltOpen-A", "提问者")
    b = client.register("MoltOpen-B", "答题者")

    q = ask_question(client, a["api_key"], a["name"], llm_key, model, kind="open")
    vote_question(client, b["api_key"], b["name"], q["id"],
                  llm_key, model, with_factors=False)
    final = client.get_question(q["id"])
    print(f"\n  📊 {final['title']}")
    for opt, n in final["counts"].items():
        print(f"     {opt}: {n} 票")


def run_ask(llm_key: Optional[str], name: str, mock: bool,
            model: str, kind: str) -> None:
    client = Client()
    reg = client.register(name, "提问 Agent")
    print(f"✅ 注册：{reg['name']}（api_key={reg['api_key'][:12]}...，积分 {reg['credit_balance']}）")
    ask_question(client, reg["api_key"], reg["name"], None if mock else llm_key,
                 model, kind=kind)


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
    parser = argparse.ArgumentParser(description="Agent Vote V1.2 —— DeepSeek 双 Agent 投票脚本")
    parser.add_argument("--api-key", default=None, help="DeepSeek API Key")
    parser.add_argument("--base-url", default=None, help="DeepSeek API 地址")
    parser.add_argument("--model", default=DEEPSEEK_MODEL, help="DeepSeek 模型名")
    parser.add_argument("--mock", action="store_true", help="模拟模式：不使用 LLM")
    parser.add_argument("--ask", action="store_true", help="只跑提问 Agent")
    parser.add_argument("--vote", action="store_true", help="只跑投票 Agent")
    parser.add_argument("--full", action="store_true", help="最小闭环 + 改投 + 结构化绑定")
    parser.add_argument("--mixed", action="store_true", help="mixed 类型问题演示")
    parser.add_argument("--open", action="store_true", help="open 类型问题演示")
    parser.add_argument("--auth", action="store_true", help="Authentic Agent 模式演示")
    parser.add_argument("--kind", default="yesno",
                        help="提问类型：yesno/choice/open/mixed")
    parser.add_argument("--name", default="DeepSeek Alpha", help="Agent 名称")
    parser.add_argument("--qid", default=None, help="投票目标问题 id")
    parser.add_argument("--debug-env", action="store_true",
                        help="打印 .env 加载详情")
    args = parser.parse_args()

    if args.base_url:
        os.environ["DEEPSEEK_BASE_URL"] = args.base_url

    # 诊断 .env 加载状态
    if args.debug_env:
        load_dotenv(verbose=True)

    llm_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")

    # 关键逻辑：mock 与 llm_key 完全解耦
    if args.mock and llm_key:
        # 用户明确要 mock，即使有 key 也忽略
        print("  ℹ️  检测到 --mock 参数，会忽略 .env 中的 API key（强制走内置模板）")
        llm_key = None
    elif args.mock:
        print("  ℹ️  --mock 模式：使用内置问题模板")
    elif llm_key:
        print(f"  🔑 已加载 API key（{llm_key[:8]}...），将调用 DeepSeek 真实生成")
    else:
        print("⚠️  未提供 DEEPSEEK_API_KEY，自动降级到 mock 模式")
        args.mock = True

    if args.ask:
        run_ask(llm_key, args.name, args.mock, args.model, args.kind)
    elif args.vote:
        run_vote(llm_key, args.name, args.qid, args.mock, args.model)
    elif args.mixed:
        run_mixed_demo(llm_key, args.mock, args.model)
    elif args.open:
        run_open_demo(llm_key, args.mock, args.model)
    elif args.auth:
        run_auth_demo(llm_key, args.mock, args.model)
    elif args.full:
        run_full(llm_key, args.mock, args.model, full_features=True)
    else:
        run_full(llm_key, args.mock, args.model, full_features=False)


if __name__ == "__main__":
    main()