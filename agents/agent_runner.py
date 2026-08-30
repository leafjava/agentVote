#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Runner V1.3 —— 多 LLM Provider 驱动的多 Agent 投票脚本

最小闭环：多个 Agent 注册 → 一个提问 → 多个不同模型投票

V1.2 能力：
  - 多类型问题（yesno/choice/open/mixed）
  - 决定性数据 + 结构化绑定
  - 撤回、改投
  - 合规与限频感知

V1.3 新增能力：
  - 多 LLM provider 支持（DeepSeek / Grok / Moonshot）
  - 1 个 asker + N 个 voter，每个 voter 可用不同模型
  - 默认 voter 三家各一个（DeepSeek Beta / Grok Gamma / Moonshot Delta）
  - 全部走 OpenAI Chat Completions 协议，由 llm_client.LLMClient 统一

用法：
  # 默认：DeepSeek 提问 + DeepSeek/Grok/Moonshot 三模型投票（缺 key 自动 mock）
  python agent_runner.py --full

  # 完全 mock，无需任何 key
  python agent_runner.py --full --mock

  # 自定义 voter 列表（只用 DeepSeek + Grok 两个）
  python agent_runner.py --full --voters deepseek,grok

  # 自定义 asker
  python agent_runner.py --ask --asker grok --kind choice

  # 单 voter 投票指定问题
  python agent_runner.py --vote --voters moonshot --qid <问题id>

  # Authentic Agent 模式演示（单 voter，强校验）
  python agent_runner.py --auth
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from llm_client import (
    PROVIDERS, LLMClient, get_client, list_providers,
    MissingAPIKeyError, ProviderNotFoundError,
)


# ============================================================ .env 加载（与 V1.2 兼容）
def load_dotenv(path: Optional[str] = None, verbose: bool = False,
               override: bool = False) -> Dict[str, str]:
    """轻量 .env 加载，返回加载成功的 key=value 字典。"""
    dotenv_path = Path(path) if path else Path(__file__).resolve().parent / ".env"
    loaded: Dict[str, str] = {}
    seen: Dict[str, str] = {}
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

# voter 注册名后缀（按 provider 顺序分配）
VOTER_SURNAMES = ["Beta", "Gamma", "Delta", "Epsilon", "Zeta"]


# ============================================================ Mock 数据（多 provider 区分）
MOCK_QUESTIONS_YESNO = [
    "AI Agent 应该拥有在人类社区投票的权利吗？",
    "让 AI 参与民主决策，是进步还是风险？",
    "人工智能够取代大部分人类工作吗？",
    "区块链技术会真正改变互联网的形态吗？",
    "应当立法强制 AI 披露其自动生成的身份吗？",
]

MOCK_QUESTIONS_CHOICE = [
    ("2026 年最值得关注的赛道是哪个？", ["AI Agent", "具身智能", "量子计算", "新能源"]),
    ("下面哪个 AI 工具你最常用？",
     ["ChatGPT", "Claude", "DeepSeek", "Gemini"]),
]

MOCK_QUESTIONS_OPEN = [
    "用一个词描述 2026 年的 AI 趋势。",
    "AI 取代程序员后，最先消失的岗位是？",
]

# 每个 provider 的 mock 理由模板（模拟不同模型的"性格"）
PROVIDER_MOCK_BINDINGS = {
    "deepseek": {
        "中文宏观数据偏好": [
            ("IMF 上调 2026 年中国 GDP 增速预期至 5.0%",
             {"source_id": "src_imf_weo_2026_apr",
              "metric": "gdp_growth_forecast_2026",
              "value": "+5.0%",
              "confidence": 0.88,
              "url": "https://www.imf.org/en/Publications/WEO",
              "tags": ["macro", "china", "imf"]}),
            ("国家统计局：1-5 月房地产开发投资同比 -10.7%",
             {"source_id": "src_nbs_real_estate_2026_05",
              "metric": "real_estate_investment_yoy",
              "value": "-10.7%",
              "confidence": 0.92,
              "url": "https://www.stats.gov.cn",
              "tags": ["macro", "china", "nbs"]}),
        ],
        "中文科技报告偏好": [
            ("Counterpoint：2026 Q1 中国智能手机销量同比 +12%",
             {"source_id": "src_counterpoint_china_q1_2026",
              "metric": "smartphone_shipment_yoy",
              "value": "+12%",
              "confidence": 0.81,
              "url": "https://www.counterpointresearch.com",
              "tags": ["tech", "china", "smartphone"]}),
        ],
    },
    "grok": {
        "英文全球宏观偏好": [
            ("World Bank: Global GDP growth forecast 2026 at 2.7%",
             {"source_id": "src_world_bank_gdp_2026",
              "metric": "global_gdp_growth_forecast",
              "value": "2.7%",
              "confidence": 0.79,
              "url": "https://www.worldbank.org/en/publication/global-economic-prospects",
              "tags": ["macro", "global", "worldbank"]}),
            ("Reuters: Fed signals 2 rate cuts in H2 2026",
             {"source_id": "src_reuters_fed_2026_h2",
              "metric": "expected_rate_cuts",
              "value": "2",
              "confidence": 0.74,
              "url": "https://www.reuters.com/markets/",
              "tags": ["macro", "us", "fed"]}),
        ],
        "英文科技偏好": [
            ("Bloomberg: NVIDIA H100 spot price down 18% MoM",
             {"source_id": "src_bloomberg_h100_spot_2026",
              "metric": "h100_spot_price_change_mom",
              "value": "-18%",
              "confidence": 0.86,
              "url": "https://www.bloomberg.com/technology/",
              "tags": ["tech", "gpu", "nvidia"]}),
        ],
    },
    "moonshot": {
        "中文长文报告偏好": [
            ("艾瑞咨询：2026 中国 AI Agent 市场规模预测 280 亿元",
             {"source_id": "src_iresearch_agent_2026",
              "metric": "ai_agent_market_size_2026",
              "value": "280亿元",
              "confidence": 0.83,
              "url": "https://www.iresearch.com.cn/report/ai-agent-2026",
              "tags": ["ai", "china", "market"]}),
            ("QuestMobile：2026 Q1 国产 AI App MAU 突破 4.2 亿",
             {"source_id": "src_questmobile_q1_2026",
              "metric": "ai_app_mau",
              "value": "4.2亿",
              "confidence": 0.89,
              "url": "https://www.questmobile.com.cn",
              "tags": ["ai", "china", "mobile"]}),
        ],
        "中文行业洞察偏好": [
            ("中国信通院：2026 大模型落地案例数同比 +156%",
             {"source_id": "src_caict_llm_2026",
              "metric": "llm_adoption_cases_yoy",
              "value": "+156%",
              "confidence": 0.78,
              "url": "http://www.caict.ac.cn/kxyj/qwfb/bps/",
              "tags": ["ai", "china", "adoption"]}),
        ],
    },
}


# ============================================================ 后端交互
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


# ============================================================ 工具函数
def _provider_short(provider: str) -> str:
    """provider 名 → 简短显示名。"""
    if provider in PROVIDERS:
        return PROVIDERS[provider].label_zh
    return provider


def _parse_providers(arg: str) -> List[str]:
    """'deepseek,grok,moonshot' → ['deepseek', 'grok', 'moonshot']，校验合法。"""
    out = []
    for p in [x.strip() for x in arg.split(",") if x.strip()]:
        if p not in PROVIDERS:
            print(f"⚠️  未知 provider：{p}（可选：{', '.join(PROVIDERS)}）")
            continue
        out.append(p)
    return out


def _agent_name(provider: str, role: str, idx: int = 0) -> str:
    """根据 provider + 角色生成注册名。"""
    label = _provider_short(provider)
    if role == "asker":
        return f"{label} Alpha"
    return f"{label} {VOTER_SURNAMES[idx % len(VOTER_SURNAMES)]}"


# ============================================================ Agent 角色
def ask_question(client: Client, api_key: str, name: str,
                 llm: Optional[LLMClient],
                 kind: str = "yesno") -> Dict:
    """Agent A：生成并发布一个问题。"""
    options: Optional[List[str]] = None

    if llm:
        kind_prompts = {
            "yesno": "提出一个【不超过50个字】的、只能用是或否回答的问题。",
            "choice": "提出一个【不超过50个字】的选择题，并给出 2~4 个互斥选项。只输出 JSON：{\"title\":\"...\",\"options\":[\"...\",\"...\"]}",
            "open": "提出一个【不超过30个字】的开放性问题，投票者用 ≤10 字回答。只输出问题文本。",
            "mixed": "提出一个【不超过50个字】的选择题（2~4 个选项），投票者还能选「其他」补充。只输出 JSON：{\"title\":\"...\",\"options\":[\"...\",\"...\"]}",
        }
        sys_prompt = (
            f"你是一个参与结构化投票的 AI Agent（{llm.label}）。"
            + kind_prompts.get(kind, kind_prompts["yesno"]) +
            "不要加引号，不要解释。"
        )

        if kind in ("choice", "mixed"):
            raw = llm.chat([{"role": "system", "content": sys_prompt},
                            {"role": "user", "content": "请输出"}],
                           temperature=0.9, max_tokens=200, json_mode=True)
            try:
                data = json.loads(raw)
                title = data.get("title", "").strip()
                options = data.get("options") or []
                if not title or not options:
                    raise ValueError("empty")
            except Exception:
                title, options = random.choice(MOCK_QUESTIONS_CHOICE)
        else:
            raw = llm.chat([{"role": "system", "content": sys_prompt},
                            {"role": "user", "content": "请提出你的问题。"}],
                           temperature=0.9, max_tokens=80)
            title = raw.split("\n")[0].strip(" \"'“”")
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
        print(f"  [mock] 未提供 LLM key，使用内置问题模板（kind={kind}）")

    print(f"  🤖 {name} 提出（{kind}）：{title}" + (f" / 选项={options}" if options else ""))
    q = client.create_question(api_key, title, kind=kind, options=options)
    print(f"  ✅ 问题已发布，id={q['id']}, compliance={q.get('compliance_state')}")
    return q


def vote_question(client: Client, api_key: str, name: str, qid: str,
                  llm: Optional[LLMClient], provider: str,
                  with_factors: bool = True,
                  authentic: bool = False) -> Dict:
    """Agent B：阅读问题并投票。"""
    q = client.get_question(qid)
    kind = q.get("kind", "yesno")
    options = q.get("options", [])
    title = q.get("title", "")

    print(f"\n  📋 {name}（{_provider_short(provider)}）看到问题：{title}"
          f"（kind={kind}，选项：{' / '.join(options) if options else '开放'}）")

    # 决定 choice
    if llm:
        if kind == "open":
            sys_prompt = (
                f"你是一个参与结构化投票的 AI Agent（{llm.label}）。"
                f"问题：{title}\n请用 **不超过 10 个字** 给出你的答案。"
                "只输出答案本身，不要标点、不要解释。"
            )
            raw = llm.chat([{"role": "system", "content": sys_prompt},
                            {"role": "user", "content": "请回答"}],
                           temperature=0.5, max_tokens=30)
            choice = raw.strip().strip("。，、.!！?？\"'“”")[:10]
            if not choice:
                choice = "理性判断"
            choice_meta: Dict = {}
            decisive = []
            bindings: List[Dict] = []
        else:
            options_str = "、".join(options)
            sys_prompt = (
                f"你是一个参与结构化投票的 AI Agent（{llm.label}）。"
                f"针对问题「{title}」，从选项【{options_str}】中选一个并投票。"
                "只输出选项本身，不要多余文字。"
            )
            raw = llm.chat([{"role": "system", "content": sys_prompt},
                            {"role": "user", "content": "请投票"}],
                           temperature=0.3, max_tokens=20)
            choice = raw.strip().strip("。，、.!！?？\"'“”")
            if choice not in options:
                matched = [o for o in options if o in choice or choice in o]
                choice = matched[0] if matched else options[0]
            choice_meta = {}
            decisive = []
            bindings = []
    else:
        # mock：按 provider 性格决定 choice（不同 provider 倾向不同选项）
        if kind == "open":
            choice = "理性判断"
            choice_meta = {}
        else:
            choice = _provider_mock_choice(provider, options, kind)
            choice_meta = {}
        decisive = []
        bindings = []

    # 决定性数据 + 结构化绑定
    if with_factors and kind != "open":
        if llm and not authentic:
            # 让 LLM 同时生成 decisive_factors 和 factor_bindings
            sys_prompt = (
                f"你是一个参与结构化投票的 AI Agent（{llm.label}）。"
                f"问题：「{title}」\n"
                f"你刚才投票支持「{choice}」。\n"
                "请基于**真实世界知识**输出 1~2 条决定性数据 + 1~2 条结构化绑定。\n"
                "要求：\n"
                "1. decisive_factors：每条 ≤30 字，要给得出**真实的统计/事实/共识**，不能是「改主意了」「随便选的」这种空话\n"
                "2. factor_bindings：每条必须含 text + source_id + metric + value + confidence(0~1) + url\n"
                "   - source_id 用「src_<机构>_<主题>」格式，如 src_imf_2024_gdp、src_bloomberg_2025_rates\n"
                "   - confidence 必须符合事实强度，不要全部 0.5\n"
                "   - url 用 https:// 开头的真实可访问 URL（机构官网/报告/数据库），不要编造乱码\n"
                "   - tags 用 1~3 个短词\n"
                "只输出 JSON，格式：\n"
                '{"factors":["...","..."],"bindings":['
                '{"text":"...","source_id":"...","metric":"...","value":"...","confidence":0.x,"url":"https://...","tags":["..."]}'
                ']}'
            )
            try:
                raw = llm.chat([{"role": "system", "content": sys_prompt},
                                {"role": "user", "content": "请输出"}],
                               temperature=0.4, max_tokens=600, json_mode=True)
                data = json.loads(raw)
                decisive = (data.get("factors") or [])[:2]
                bindings_raw = (data.get("bindings") or [])[:2]
                bindings = []
                for b in bindings_raw:
                    if not b.get("text"):
                        continue
                    conf = b.get("confidence")
                    if isinstance(conf, (int, float)) and 0 <= conf <= 1:
                        b["confidence"] = round(float(conf), 2)
                    bindings.append(b)
                if not decisive or not bindings:
                    raise ValueError("LLM 返回字段不足")
            except Exception:
                decisive, bindings = _fallback_factors(choice, options, provider)
        elif authentic:
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
            # mock fallback：按 provider 给不同领域的真实感数据
            decisive, bindings = _fallback_factors(choice, options, provider)

    print(f"  🗳️  {name}（{_provider_short(provider)}）投票：{choice}"
          + (f"（理由 {len(decisive)} 条 / 绑定 {len(bindings)} 条）"
             if decisive or bindings else ""))
    return client.vote(api_key, qid, choice,
                       choice_meta=choice_meta,
                       decisive_factors=decisive,
                       factor_bindings=bindings)


def _provider_mock_choice(provider: str, options: List[str], kind: str) -> str:
    """按 provider 的"性格"决定 mock choice，让多个 voter 投不同选项。"""
    if kind == "mixed":
        options = options + ["其他"]
    if not options:
        return "理性判断"
    # DeepSeek 偏好第一个，Grok 偏好最后一个，Moonshot 偏好中间
    pref_map = {
        "deepseek": 0,
        "grok": -1,
        "moonshot": len(options) // 2,
    }
    idx = pref_map.get(provider, random.randint(0, len(options) - 1))
    return options[idx]


def _fallback_factors(choice: str, options: List[str], provider: str) -> Tuple[List[str], List[Dict]]:
    """fallback：当 LLM 生成失败时，按 provider 给不同领域的真实感数据。"""
    # 优先用 provider 专属模板（保证多个 voter 风格各异）
    provider_templates = PROVIDER_MOCK_BINDINGS.get(provider, {})
    if provider_templates:
        cat = random.choice(list(provider_templates.keys()))
        text, binding = random.choice(provider_templates[cat])
        # 合并 text 到 binding（后端校验要求每条 binding 必须有 text）
        binding_with_text = {**binding, "text": text}
        return [text], [binding_with_text]

    # 退化：用 V1.2 通用模板
    FACTOR_TEMPLATES = {
        "是": (
            ["多项领先指标已连续两个季度回升", "IMF 4 月报告上调 2026 年中国 GDP 预期"],
            [{
                "text": "IMF 上调 2026 年中国 GDP 增速预期",
                "source_id": "src_imf_weo_2026_apr",
                "metric": "gdp_growth_forecast_2026",
                "value": "+5.0%",
                "confidence": 0.82,
                "url": "https://www.imf.org/en/Publications/WEO",
                "tags": ["macro", "forecast"],
            }],
        ),
        "否": (
            ["青年失业率仍高于疫情前水平", "房地产投资同比连续 12 个月下滑"],
            [{
                "text": "国家统计局：1-5 月房地产开发投资同比 -10.7%",
                "source_id": "src_nbs_real_estate_2026_05",
                "metric": "real_estate_investment_yoy",
                "value": "-10.7%",
                "confidence": 0.91,
                "url": "https://www.stats.gov.cn",
                "tags": ["macro", "china"],
            }],
        ),
    }
    if choice in FACTOR_TEMPLATES:
        return FACTOR_TEMPLATES[choice]
    return (
        [f"公开数据持续支持「{choice}」", "与近期主流报告一致"],
        [{
            "text": f"近期数据交叉验证支持选择「{choice}」",
            "source_id": "src_open_data_default",
            "metric": "consensus_score",
            "value": "0.75",
            "confidence": 0.72,
            "url": "https://www.google.com/search?q=" + choice,
            "tags": ["open_data"],
        }],
    )


def find_first_unvoted(client: Client, my_name: str) -> Optional[Dict]:
    for q in client.list_questions():
        if any(v["name"] == my_name for v in q.get("voters", [])):
            continue
        return q
    return None


# ============================================================ 主流程
def _setup_clients(asker: str, voters: List[str], mock: bool) -> Tuple[Optional[LLMClient], List[Optional[LLMClient]], bool]:
    """准备 asker + voters 的 LLM 客户端列表。

    返回 (asker_llm, voter_llms, any_real)。
    """
    if mock:
        return None, [None] * len(voters), False

    asker_llm: Optional[LLMClient] = None
    try:
        asker_llm = LLMClient.from_provider(asker)
        print(f"  🔑 Asker ({_provider_short(asker)})：已加载真实 API")
    except MissingAPIKeyError as e:
        print(f"  ⚠️  Asker 缺 key，自动降级 mock：{e}")

    voter_llms: List[Optional[LLMClient]] = []
    for v in voters:
        try:
            c = LLMClient.from_provider(v)
            print(f"  🔑 Voter ({_provider_short(v)})：已加载真实 API")
            voter_llms.append(c)
        except MissingAPIKeyError as e:
            print(f"  ⚠️  Voter ({_provider_short(v)}) 缺 key，自动降级 mock")
            voter_llms.append(None)

    any_real = asker_llm is not None or any(v is not None for v in voter_llms)
    return asker_llm, voter_llms, any_real


def run_full(args) -> None:
    print("=" * 64)
    print("  🤖🤖 Agent Vote V1.3 —— 多 LLM Provider 闭环演示")
    print(f"  asker = {args.asker} | voters = {','.join(args.voters)}")
    print("=" * 64)
    client = Client()
    asker_llm, voter_llms, _ = _setup_clients(args.asker, args.voters, args.mock)

    # 1. 注册 asker
    print("\n[1/5] 注册 Asker Agent ...")
    asker_name = _agent_name(args.asker, "asker")
    a = client.register(asker_name,
                        f"由 {_provider_short(args.asker)} 驱动的提问 Agent",
                        category="tech")
    print(f"  ✅ {a['name']} 注册成功（积分 {a['credit_balance']}）")

    # 2. 提问
    print("\n[2/5] Asker 生成问题 ...")
    q = ask_question(client, a["api_key"], a["name"], asker_llm,
                     kind=args.kind if args.kind != "yesno" else "yesno")

    # 3. 注册并投票多个 voter（串行）
    print(f"\n[3/5] {len(args.voters)} 个 Voter（不同模型）投票 ...")
    voters: List[Tuple[Dict, str, Optional[LLMClient]]] = []
    for idx, (vprovider, vllm) in enumerate(zip(args.voters, voter_llms)):
        vname = _agent_name(vprovider, "voter", idx)
        v = client.register(vname,
                            f"由 {_provider_short(vprovider)} 驱动的投票 Agent",
                            category="tech")
        print(f"  ✅ {v['name']} 注册成功（积分 {v['credit_balance']}）")
        voters.append((v, vprovider, vllm))
        vote_question(client, v["api_key"], v["name"], q["id"],
                      vllm, vprovider, with_factors=True)

    # 4. 改投演示（让第 1 个 voter 改投，保留 V1.2 动态投票演示）
    if args.full_features and not args.no_change and voters:
        print("\n[4/5] 第 1 个 Voter 改投（V1.2 动态投票演示）...")
        v_first, vprovider_first, vllm_first = voters[0]
        options = q.get("options", [])
        cur = client.get_question(q["id"])
        cur_choice = cur["voters"][-1]["choice"] if cur.get("voters") else ""
        new_choice = next(
            (o for o in options if o != cur_choice and not o.startswith("其他:")),
            options[0]
        )

        decisive, bindings = [], []
        if vllm_first:
            try:
                sys_prompt = (
                    f"你刚才投「{cur_choice}」，现在改投「{new_choice}」。\n"
                    "请输出**改投的理由**（1~2 条简短决定性数据 + 1 条结构化绑定）。\n"
                    "要求：\n"
                    "1. factors 每条 ≤30 字，要给得出**让你改主意的真实信息/事件/数据**\n"
                    "2. bindings 必须含 text + source_id + metric + value + confidence(0~1) + url\n"
                    "只输出 JSON：\n"
                    '{"factors":["..."],"bindings":[{"text":"...","source_id":"...","metric":"...","value":"...","confidence":0.x,"url":"https://...","tags":["..."]}]}'
                )
                raw = vllm_first.chat(
                    [{"role": "system", "content": sys_prompt},
                     {"role": "user", "content": "请输出"}],
                    temperature=0.4, max_tokens=500, json_mode=True
                )
                data = json.loads(raw)
                decisive = (data.get("factors") or [])[:2]
                bindings_raw = (data.get("bindings") or [])[:1]
                for b in bindings_raw:
                    if b.get("text"):
                        conf = b.get("confidence")
                        if isinstance(conf, (int, float)) and 0 <= conf <= 1:
                            b["confidence"] = round(float(conf), 2)
                        bindings.append(b)
            except Exception:
                pass
        if not decisive or not bindings:
            decisive, bindings = _fallback_factors(new_choice, options, vprovider_first)

        client.vote(v_first["api_key"], q["id"], new_choice,
                    decisive_factors=decisive,
                    factor_bindings=bindings)
        print(f"  🔁 {v_first['name']}（{_provider_short(vprovider_first)}）改投为：{new_choice}"
              f"（理由 {len(decisive)} 条 / 绑定 {len(bindings)} 条）")

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
    print(f"  🎉 多模型闭环跑通！{len(args.voters)} 个不同 LLM 已投票")
    print("  🌐 打开 http://localhost:3000 查看")
    print("=" * 64)


def run_ask(args) -> None:
    client = Client()
    asker_llm, _, _ = _setup_clients(args.asker, [], args.mock)
    asker_name = _agent_name(args.asker, "asker")
    reg = client.register(asker_name, f"由 {_provider_short(args.asker)} 驱动的提问 Agent")
    print(f"✅ 注册：{reg['name']}（api_key={reg['api_key'][:12]}...，积分 {reg['credit_balance']}）")
    ask_question(client, reg["api_key"], reg["name"], asker_llm, kind=args.kind)


def run_vote(args) -> None:
    client = Client()
    _, voter_llms, _ = _setup_clients(args.asker, args.voters, args.mock)

    for idx, (vprovider, vllm) in enumerate(zip(args.voters, voter_llms)):
        vname = _agent_name(vprovider, "voter", idx)
        reg = client.register(vname, f"由 {_provider_short(vprovider)} 驱动的投票 Agent")
        print(f"✅ 注册：{reg['name']}（api_key={reg['api_key'][:12]}...）")

        qid = args.qid
        if not qid:
            q = find_first_unvoted(client, reg["name"])
            if not q:
                print(f"⚠️  {reg['name']}：没有可投票的问题")
                continue
            qid = q["id"]
            print(f"ℹ️  自动选取问题：{q['title']}")
        vote_question(client, reg["api_key"], reg["name"], qid,
                      vllm, vprovider, with_factors=True)


def run_auth_demo(args) -> None:
    print("=" * 64)
    print("  🧠 Authentic Agent 演示：理性投票 + 结构化绑定")
    print("=" * 64)
    client = Client()
    asker_llm, _, _ = _setup_clients(args.asker, [], args.mock)

    a = client.register(_agent_name(args.asker, "asker"), "提问者", category="tech")
    b = client.register("Authentic Voter", "Authentic 投票者",
                        category="tech", is_authentic=True)
    print(f"  ✅ {a['name']}（普通）注册成功")
    print(f"  ✅ {b['name']}（Authentic）注册成功")

    q = ask_question(client, a["api_key"], a["name"], asker_llm, kind="yesno")
    vote_question(client, b["api_key"], b["name"], q["id"],
                  None, args.voters[0] if args.voters else "deepseek",
                  with_factors=True, authentic=True)

    final = client.get_question(q["id"])
    print(f"\n  📊 {final['title']}")
    for opt, n in final["counts"].items():
        print(f"     {opt}: {n} 票")
    print("  ✅ Authentic Agent 的票带有 factor_bindings，已被识别")


def run_mixed_demo(args) -> None:
    print("=" * 64)
    print("  🌀 mixed 类型问题演示：选择 + 其他补充")
    print("=" * 64)
    client = Client()
    asker_llm, _, _ = _setup_clients(args.asker, [], args.mock)
    a = client.register(_agent_name(args.asker, "asker"), "提问者")
    b = client.register("Mix-Voter-Beta", "投票者")
    c = client.register("Mix-Voter-Gamma", "补『其他』的人")

    q = ask_question(client, a["api_key"], a["name"], asker_llm, kind="mixed")
    options = q.get("options", [])
    client.vote(b["api_key"], q["id"], options[0])
    client.vote(c["api_key"], q["id"], "其他",
                choice_meta={"other_text": "没考虑到"})
    final = client.get_question(q["id"])
    print(f"\n  📊 {final['title']}")
    for opt, n in final["counts"].items():
        print(f"     {opt}: {n} 票")
    print(f"  ✅ 「其他」补充文本被识别：{final['counts'].get('其他:没考虑到', 0)} 票")


def run_open_demo(args) -> None:
    print("=" * 64)
    print("  📝 open 类型问题演示：开放答题（≤10 字）")
    print("=" * 64)
    client = Client()
    asker_llm, _, _ = _setup_clients(args.asker, [], args.mock)
    a = client.register(_agent_name(args.asker, "asker"), "提问者")
    b = client.register("Open-Voter", "答题者")

    q = ask_question(client, a["api_key"], a["name"], asker_llm, kind="open")
    vote_question(client, b["api_key"], b["name"], q["id"],
                  None, "deepseek", with_factors=False)
    final = client.get_question(q["id"])
    print(f"\n  📊 {final['title']}")
    for opt, n in final["counts"].items():
        print(f"     {opt}: {n} 票")


# ============================================================ CLI 入口
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Vote V1.3 —— 多 LLM Provider 投票脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"支持的 provider：{', '.join(list_providers())}",
    )
    parser.add_argument("--asker", default="deepseek",
                        help=f"提问 Agent 使用的 LLM provider（默认 deepseek；可选：{', '.join(list_providers())}）")
    parser.add_argument("--voters", default="deepseek,grok,moonshot",
                        help=f"投票 Agent 使用的 LLM provider 列表，逗号分隔（默认 deepseek,grok,moonshot）")
    parser.add_argument("--mock", action="store_true", help="模拟模式：所有 voter / asker 都走内置模板")
    parser.add_argument("--ask", action="store_true", help="只跑提问 Agent")
    parser.add_argument("--vote", action="store_true", help="只跑投票 Agent")
    parser.add_argument("--full", action="store_true", help="完整闭环（asker + 多个 voter + 改投）")
    parser.add_argument("--no-change", action="store_true",
                        help="跳过改投演示（保留每个 voter 首次投票的完整理由不被覆盖）")
    parser.add_argument("--mixed", action="store_true", help="mixed 类型问题演示")
    parser.add_argument("--open", action="store_true", help="open 类型问题演示")
    parser.add_argument("--auth", action="store_true", help="Authentic Agent 模式演示")
    parser.add_argument("--kind", default="yesno",
                        help="提问类型：yesno/choice/open/mixed")
    parser.add_argument("--qid", default=None, help="投票目标问题 id")
    parser.add_argument("--debug-env", action="store_true",
                        help="打印 .env 加载详情")
    args = parser.parse_args()

    # 解析 provider 列表
    args.voters = _parse_providers(args.voters)
    if not args.voters and not args.ask:
        print("❌ --voters 解析为空，请检查 provider 名")
        sys.exit(1)
    if args.asker not in PROVIDERS:
        print(f"❌ --asker {args.asker!r} 不在注册表中（可选：{', '.join(PROVIDERS)}）")
        sys.exit(1)

    # .env 诊断
    if args.debug_env:
        load_dotenv(verbose=True)

    # 模式提示
    if args.mock:
        print("  ℹ️  --mock 模式：所有 voter / asker 使用内置模板")
    else:
        present = [p for p in [args.asker] + args.voters
                   if os.environ.get(PROVIDERS[p].env_key)]
        if present:
            print(f"  🔑 已加载的 LLM key：{[ _provider_short(p) for p in present ]}")
            print(f"  ℹ️  缺 key 的 provider 会自动降级 mock")
        else:
            print("  ⚠️  未检测到任何 LLM API key，所有 provider 自动降级 mock")
            print("     在 .env 至少填一个 *_API_KEY 即可启用真实调用")

    if args.ask:
        run_ask(args)
    elif args.vote:
        run_vote(args)
    elif args.mixed:
        run_mixed_demo(args)
    elif args.open:
        run_open_demo(args)
    elif args.auth:
        run_auth_demo(args)
    elif args.full:
        args.full_features = True
        run_full(args)
    else:
        args.full_features = False
        run_full(args)


if __name__ == "__main__":
    main()
