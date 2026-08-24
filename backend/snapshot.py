"""
Agent Vote V1.2 快照生成器（snapshot/）

按 V1.2 第 6.2 节实现：
  - 后台任务按 snapshot_interval 对当前票面做不可变快照
  - 同 (question_id, bucket_end) 已存在则跳过（幂等）
  - 一次扫描所有 active 问题，到点才生成快照

V1.2 简化：scheduler 由 main.py 在 lifespan 里启动。
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from db import get_conn, now_ts, parse_json_field, to_json


# ---------------------------------------------------------------- 桶大小
INTERVAL_SECONDS = {
    "1h": 3600,
    "1d": 86400,
    "none": 0,  # 不自动切片
}


def _bucket_bounds(ts: int, interval: str) -> tuple:
    """计算 ts 所在桶的 [bucket_start, bucket_end)。"""
    sec = INTERVAL_SECONDS.get(interval, INTERVAL_SECONDS["1d"])
    if sec <= 0:
        return ts, ts
    # 以桶大小对齐 epoch
    bucket_start = (ts // sec) * sec
    bucket_end = bucket_start + sec
    return bucket_start, bucket_end


# ----------------------------------------------------------------
def snapshot_question(question_id: str, force: bool = False) -> Optional[dict]:
    """为单个问题生成一次快照（幂等）。"""
    with get_conn() as conn:
        q = conn.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        if not q:
            return None
        if q["status"] != "active":
            return None

        interval = q["snapshot_interval"] or "1d"
        sec = INTERVAL_SECONDS.get(interval, INTERVAL_SECONDS["1d"])
        if sec <= 0:
            return None  # none 不切

        now = now_ts()
        bucket_start, bucket_end = _bucket_bounds(now, interval)

        # 幂等：同 bucket_end 已存在则跳过
        if not force:
            exist = conn.execute(
                "SELECT id FROM vote_snapshots WHERE question_id = ? AND bucket_end = ?",
                (question_id, bucket_end),
            ).fetchone()
            if exist:
                return None

        # 收集当前票面（is_current=1 且未撤回）
        rows = conn.execute(
            """
            SELECT choice, weight FROM votes
            WHERE question_id = ? AND is_current = 1 AND is_revoked = 0
            """,
            (question_id,),
        ).fetchall()

        options = parse_json_field(q["options"], [])
        counts: Dict[str, float] = {o: 0 for o in options}
        weighted: Dict[str, float] = {o: 0.0 for o in options}
        total = 0
        for r in rows:
            c = r["choice"]
            w = float(r["weight"] or 1.0)
            if c not in counts:
                # 兼容 open/mixed 题的开放答案或 "其他" 文本
                counts[c] = 0
                weighted[c] = 0.0
            counts[c] += 1
            weighted[c] += w
            total += 1

        # 转成 int 计数（兼容 JSON）
        counts_json = {k: int(v) for k, v in counts.items()}
        weighted_json = {k: round(v, 3) for k, v in weighted.items()}

        conn.execute(
            """
            INSERT OR IGNORE INTO vote_snapshots
              (question_id, bucket_start, bucket_end, counts, total_votes,
               weighted_counts, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_id,
                bucket_start,
                bucket_end,
                to_json(counts_json),
                total,
                to_json(weighted_json),
                now,
            ),
        )

    return {
        "question_id": question_id,
        "bucket_start": bucket_start,
        "bucket_end": bucket_end,
        "counts": counts_json,
        "total_votes": total,
        "weighted_counts": weighted_json,
    }


def snapshot_all_active() -> List[dict]:
    """对所有 active 问题生成快照（被 scheduler 调用）。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM questions WHERE status = 'active'"
        ).fetchall()
    out = []
    for r in rows:
        snap = snapshot_question(r["id"])
        if snap:
            out.append(snap)
    return out


def list_snapshots(question_id: str, limit: int = 50) -> List[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT bucket_start, bucket_end, counts, total_votes,
                   weighted_counts, created_at
            FROM vote_snapshots
            WHERE question_id = ?
            ORDER BY bucket_end DESC
            LIMIT ?
            """,
            (question_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "bucket_start": r["bucket_start"],
            "bucket_end": r["bucket_end"],
            "counts": parse_json_field(r["counts"], {}),
            "total_votes": r["total_votes"],
            "weighted_counts": parse_json_field(r["weighted_counts"], {}),
            "created_at": r["created_at"],
        })
    return out


# ---------------------------------------------------------------- 后台 scheduler
async def scheduler_loop(interval_sec: int = 60):
    """每 60 秒扫一次所有 active 问题，到点生成快照。"""
    while True:
        try:
            snapshot_all_active()
        except Exception as e:
            print(f"[snapshot] error: {e}")
        await asyncio.sleep(interval_sec)