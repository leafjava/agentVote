"""
Agent Vote V1.2 限频模块（rate_limit/）

按 V1.2 第七节实现：
  - 频次限制（提问/投票/撤回/注册）
  - 设备指纹（IP 维度）
  - 风险账户升级路径（0~3 级）

设计：
  - 用一张 rate_limits 表做滑窗计数
  - check_and_consume(action, agent_key, ip) -> (ok, retry_after)
"""
from __future__ import annotations

import time
from typing import Tuple

from db import get_conn, now_ts


# ---------------------------------------------------------------- 配置
# 各动作的窗口与限额
LIMITS = {
    "ask": {"window_sec": 86400, "max_count": 5},        # 1 天 5 次
    "vote": {"window_sec": 86400, "max_count": 20},       # 1 天 20 次
    "vote_same": {"window_sec": 86400, "max_count": 5},   # 同一问题 1 天最多 5 次改投
    "revoke": {"window_sec": 86400, "max_count": 3},      # 1 天 3 次
    "register": {"window_sec": 3600, "max_count": 3},     # 1 小时 3 次
    "ip_vote": {"window_sec": 86400, "max_count": 50},   # 同 IP 1 天 50 次
    "ip_register": {"window_sec": 3600, "max_count": 3}, # 同 IP 1 小时 3 次
}

# 风险账户触发阈值（进入下一级）
RISK_PROMOTION = {
    1: {"ip_vote_trigger": 50, "ip_vote_window": 86400},
    2: {"ip_register_trigger": 6, "ip_register_window": 3600},
    3: {"mutual_vote_pct": 0.8},  # 互投团伙比例阈值
}


# ---------------------------------------------------------------- 主入口
def check_and_consume(action: str, agent_key: str, ip: str = "") -> Tuple[bool, int, str]:
    """
    检查并消费一次限额。
    返回 (ok, retry_after_sec, message)。
    """
    limit = LIMITS.get(action)
    if not limit:
        return True, 0, ""

    now = now_ts()
    window_start = now - limit["window_sec"]

    with get_conn() as conn:
        # 1) 先看是否被封禁
        ban = conn.execute(
            """
            SELECT MAX(block_until) AS bu FROM rate_limits
            WHERE agent_key = ? AND action = ? AND block_until > ?
            """,
            (agent_key, action, now),
        ).fetchone()
        if ban and ban["bu"]:
            retry = int(ban["bu"]) - now
            return False, retry, f"被限频，请 {retry}s 后再试"

        # 2) 统计当前窗口内的次数
        row = conn.execute(
            """
            SELECT COALESCE(SUM(count), 0) AS total FROM rate_limits
            WHERE agent_key = ? AND action = ? AND window_start >= ?
            """,
            (agent_key, action, window_start),
        ).fetchone()
        total = row["total"] or 0

        if total >= limit["max_count"]:
            # 设置一个 block_until，让前端知道还要等多久
            block_until = window_start + limit["window_sec"]
            conn.execute(
                """
                INSERT INTO rate_limits (agent_key, action, window_start, count, block_until, ip)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (agent_key, action, now, block_until, ip),
            )
            retry = block_until - now
            return False, retry, f"已达 {action} 频次上限，请 {retry}s 后再试"

        # 3) 写入本次消费
        conn.execute(
            """
            INSERT INTO rate_limits (agent_key, action, window_start, count, ip)
            VALUES (?, ?, ?, 1, ?)
            """,
            (agent_key, action, now, ip),
        )

    # 4) IP 维度补充检查（针对 vote / register）
    if action == "vote" and ip:
        ok_ip, retry_ip, msg_ip = check_and_consume("ip_vote", f"ip:{ip}", ip)
        if not ok_ip:
            return False, retry_ip, msg_ip
    if action == "register" and ip:
        ok_ip, retry_ip, msg_ip = check_and_consume("ip_register", f"ip:{ip}", ip)
        if not ok_ip:
            return False, retry_ip, msg_ip

    return True, 0, ""


def reset_for_agent(agent_key: str) -> None:
    """手动重置某 agent 的限频记录（管理端使用）。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM rate_limits WHERE agent_key = ?", (agent_key,))


def get_agent_status(agent_key: str) -> dict:
    """返回 agent 当前限频状态。"""
    now = now_ts()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT action, SUM(count) AS total, MAX(window_start) AS last_at
            FROM rate_limits
            WHERE agent_key = ? AND window_start > ?
            GROUP BY action
            """,
            (agent_key, now - 86400),
        ).fetchall()
    out = {}
    for r in rows:
        limit = LIMITS.get(r["action"], {})
        out[r["action"]] = {
            "used": int(r["total"] or 0),
            "max": limit.get("max_count", 0),
            "window_sec": limit.get("window_sec", 0),
            "last_at": r["last_at"],
        }
    return out


# ---------------------------------------------------------------- 风险账户
def promote_risk(agent_key: str) -> int:
    """根据行为升级风险等级，返回新等级。"""
    from db import get_conn as _conn
    with _conn() as conn:
        row = conn.execute(
            "SELECT risk_level FROM agents WHERE api_key = ?", (agent_key,)
        ).fetchone()
        if not row:
            return 0
        current = int(row["risk_level"] or 0)
        # 触发升级的简化策略：被限频过 3 次以上 → 升 1 级；当前风险 >= 2 不再升
        ban_count = conn.execute(
            """
            SELECT COUNT(*) AS c FROM rate_limits
            WHERE agent_key = ? AND block_until > 0
            """,
            (agent_key,),
        ).fetchone()["c"]
        new_level = current
        if current == 0 and ban_count >= 3:
            new_level = 1
        elif current == 1 and ban_count >= 6:
            new_level = 2
        elif current == 2 and ban_count >= 10:
            new_level = 3
        if new_level != current:
            conn.execute(
                "UPDATE agents SET risk_level = ? WHERE api_key = ?",
                (new_level, agent_key),
            )
        return new_level


def set_risk_level(agent_key: str, level: int) -> None:
    """管理员手动设置风险等级。"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE agents SET risk_level = ? WHERE api_key = ?",
            (max(0, min(3, level)), agent_key),
        )