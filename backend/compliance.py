"""
Agent Vote V1.2 合规 Skill（compliance/）

文档对应第八节：
  - 关键词黑名单（自动 reject）
  - 地区规则匹配（标记地区 + 限流规则）
  - 人物/事件规则（标记需人工）
  - LLM 复核（warn = 进入 pending）
  - 审计日志写 compliance_logs

地区结算原则（重点）：
  - 中国大陆：仅积分，不接法币
  - 美国：可走稳定币，但需明确条款
  - 欧盟：MiCA 框架内
  - 默认：仅积分

V1.2 阶段规则表为内置常量，后续可改成 JSON / DB 配置。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from db import get_conn, now_ts, parse_json_field, to_json

RULE_VERSION = "v1.2.0"


# ---------------------------------------------------------------- 规则表
# 关键词黑名单：政治极端、违禁、暴力类直接 reject
KEYWORD_BLOCK = [
    r"\b(?:恐怖袭击|爆炸袭击|自杀式)\b",
    r"\b(?:毒品|贩毒)\b",
    r"\b(?:色情|淫秽)\b",
    r"\b(?:种族���绝|种族清洗)\b",
]

# 关键词 warn：财经预测、敏感人物，进入 pending 等人工
KEYWORD_WARN = [
    r"\b(?:股价|股票|财报|收益预期|ipo|上市)\b",
    r"\b(?:美联储|加息|降息|央行)\b",
    r"\b(?:特朗普|拜登|习近平|普京|泽连斯基)\b",
    r"\b(?:比特币|btc|eth|usdt|稳定币)\b",
    r"\b(?:选举结果|大选)\b",
]

# 人物/事件标记：仅记录到合规日志，不直接 reject
SENSITIVE_FIGURES = [
    "特朗普", "拜登", "习近平", "普京", "泽连斯基", "内塔尼亚胡",
]

# 地区推断：根据问题文本里的地区线索决定结算方式
REGION_HINTS = {
    "中国": "CN",
    "大陆": "CN",
    "国内": "CN",
    "美国": "US",
    "欧盟": "EU",
    "欧洲": "EU",
    "日本": "JP",
    "韩国": "KR",
}

# 各地区结算方式
SETTLEMENT_POLICY = {
    "CN": {"fiat": False, "stable": False, "credit": True, "note": "仅积分激励"},
    "US": {"fiat": False, "stable": True, "credit": True,
           "note": "可走稳定币，受 CFTC ��管要求"},
    "EU": {"fiat": False, "stable": True, "credit": True,
           "note": "MiCA 框架内"},
    "JP": {"fiat": False, "stable": True, "credit": True, "note": " FSA 监管要求"},
    "KR": {"fiat": False, "stable": True, "credit": True, "note": " 韩国特定金融信息法"},
    "DEFAULT": {"fiat": False, "stable": False, "credit": True, "note": "默认仅积分"},
}


# ---------------------------------------------------------------- 数据
@dataclass
class ComplianceResult:
    state: str                       # approved / pending / rejected
    region: str = "DEFAULT"
    note: str = ""
    hits: List[Dict] = field(default_factory=list)


# ---------------------------------------------------------------- 匹配
def _match_any(text: str, patterns: List[str]) -> List[str]:
    return [p for p in patterns if re.search(p, text, flags=re.IGNORECASE)]


def infer_region(text: str) -> str:
    for kw, code in REGION_HINTS.items():
        if kw in text:
            return code
    return "DEFAULT"


def settlement_for(region: str) -> Dict:
    return SETTLEMENT_POLICY.get(region, SETTLEMENT_POLICY["DEFAULT"])


def check_question(title: str, options: List[str], category: str = "general") -> ComplianceResult:
    """
    对一个问题做合规校验。
    返回 ComplianceResult，同时把审计日志写进 compliance_logs。
    """
    text = (title or "") + " " + " ".join(options or [])

    hits: List[Dict] = []

    # 1) 关键词 reject
    blocked = _match_any(text, KEYWORD_BLOCK)
    if blocked:
        for p in blocked:
            hits.append({"rule_id": "keyword_block", "pattern": p})
        _log("question", title[:32], "keyword_block", RULE_VERSION, "block",
             {"patterns": blocked})
        return ComplianceResult(state="rejected", note="触发关键词黑名单",
                                hits=hits)

    # 2) 关键词 warn
    warned = _match_any(text, KEYWORD_WARN)
    state = "approved"
    note_parts: List[str] = []
    if warned:
        hits.append({"rule_id": "keyword_warn", "patterns": warned})
        state = "pending"
        note_parts.append("触发关键词预警，需人工复核")

    # 3) 敏感人物
    sensitive = [n for n in SENSITIVE_FIGURES if n in text]
    if sensitive:
        hits.append({"rule_id": "sensitive_figure", "figures": sensitive})
        if state == "approved":
            state = "pending"
        note_parts.append(f"涉敏感人物：{','.join(sensitive)}")

    # 4) 地区推断
    region = infer_region(text)
    settlement = settlement_for(region)
    hits.append({"rule_id": "region_infer", "region": region,
                 "settlement": settlement})

    # 5) 类别合规：finance 默认 pending
    if category == "finance":
        if state == "approved":
            state = "pending"
        note_parts.append("财经类问题默认进入复核")
        hits.append({"rule_id": "category_finance"})

    note = " / ".join(note_parts) if note_parts else "通过"

    _log("question", title[:32], "rule_pack", RULE_VERSION,
         "pass" if state == "approved" else "warn",
         {"hits": hits, "region": region})

    return ComplianceResult(state=state, region=region, note=note, hits=hits)


def check_vote(title: str, choice: str) -> ComplianceResult:
    """投票环节的轻量复核：检查 choice 是否触发了极端表达。"""
    text = f"{choice}"
    blocked = _match_any(text, KEYWORD_BLOCK)
    if blocked:
        _log("vote", choice[:32], "keyword_block", RULE_VERSION, "block",
             {"patterns": blocked})
        return ComplianceResult(state="rejected", note="投票内容触发关键词黑名单")
    return ComplianceResult(state="approved")


# ---------------------------------------------------------------- 审计
def _log(target_type: str, target_id: str, rule_id: str,
         rule_version: str, result: str, detail: Dict) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO compliance_logs
                  (target_type, target_id, rule_id, rule_version, result, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (target_type, target_id, rule_id, rule_version, result,
                 to_json(detail), now_ts()),
            )
    except Exception:
        # 审计失败不应阻塞主流程，但生产环境应当告警
        pass


def recent_logs(limit: int = 50) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM compliance_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "target_type": r["target_type"],
            "target_id": r["target_id"],
            "rule_id": r["rule_id"],
            "rule_version": r["rule_version"],
            "result": r["result"],
            "detail": parse_json_field(r["detail"], {}),
            "created_at": r["created_at"],
        })
    return out