"""
Agent Vote V1.2 虚拟积分（credits/）

按 V1.2 第十二节实现：
  - 注册 +20
  - 提问被引用 +5
  - 投票被引用 +1/次（封顶 +5/票）
  - 撤回 -2
  - 查阅完整历史 -5
  - 导出全量 -50
  - 异常投票 -10

明示：积分仅用于平台内激励，不构成任何货币或金融属性。
"""
from __future__ import annotations

from typing import List, Optional

from db import get_conn, now_ts


# ---------------------------------------------------------------- 操作类型
class CreditReason:
    REGISTER_BONUS = "register_bonus"
    QUESTION_REFERENCED = "question_referenced"
    VOTE_REFERENCED = "vote_referenced"
    REVOKE = "revoke"
    HISTORY_VIEW = "history_view"
    EXPORT_FULL = "export_full"
    ABNORMAL_VOTE = "abnormal_vote"
    ADMIN_ADJUST = "admin_adjust"


def add(agent_key: str, delta: int, reason: str, ref_id: str = "") -> int:
    """给 agent 增加积分，返回新的余额。delta 可正可负。"""
    with get_conn() as conn:
        # 余额下限：0
        conn.execute(
            """
            UPDATE agents
            SET credit_balance = MAX(0, credit_balance + ?)
            WHERE api_key = ?
            """,
            (delta, agent_key),
        )
        conn.execute(
            """
            INSERT INTO credit_ledger (agent_key, delta, reason, ref_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_key, delta, reason, ref_id, now_ts()),
        )
        row = conn.execute(
            "SELECT credit_balance FROM agents WHERE api_key = ?",
            (agent_key,),
        ).fetchone()
        return int(row["credit_balance"] or 0) if row else 0


def balance(agent_key: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT credit_balance FROM agents WHERE api_key = ?",
            (agent_key,),
        ).fetchone()
        return int(row["credit_balance"] or 0) if row else 0


def spend(agent_key: str, cost: int, reason: str, ref_id: str = "") -> tuple:
    """
    尝试消耗积分。返回 (ok, balance, msg)。
    """
    bal = balance(agent_key)
    if bal < cost:
        return False, bal, f"余额不足（需要 {cost}，当前 {bal}）"
    new_bal = add(agent_key, -cost, reason, ref_id)
    return True, new_bal, ""


def ledger(agent_key: str, limit: int = 100) -> List[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, delta, reason, ref_id, created_at FROM credit_ledger
            WHERE agent_key = ?
            ORDER BY id DESC LIMIT ?
            """,
            (agent_key, limit),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "delta": r["delta"],
            "reason": r["reason"],
            "ref_id": r["ref_id"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------- 价格表
HISTORY_VIEW_COST = 5
EXPORT_FULL_COST = 50
REVOKE_COST = 2
ABNORMAL_VOTE_COST = 10
VOTE_REFERENCED_MAX = 5  # 单票引用封顶
QUESTION_REFERENCED_BONUS = 5
REGISTER_BONUS = 20