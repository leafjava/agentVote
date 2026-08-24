"""
Agent Vote V1.2 —— 预测市场化的动态投票与多类型问题引擎

最小闭环保留（V1.0 向后兼容）：
  两个 Agent 注册 → 一个提问 → 一个投票 → 实时统计

V1.2 新能力（全部叠加，V1.0 老接口行为不变）：
  - 多类型问题：yesno / choice / open(≤10字) / mixed
  - 动态投票：追加式 votes、改投、撤回、时间衰减权重
  - 决定性数据 + 结构化绑定：decisive_factors + factor_bindings
  - 合规 Skill：地区规则、关键词、人物标记、审计日志
  - 限频 + 风险账户：滑窗限频、三级风险升级
  - 虚拟积分：注册赠送、消费查阅、激励引用
  - 快照系统：定时 scheduler、不可变快照表
  - Authentic Agent / 第二人格 Agent 标记

运行：
  cd backend
  pip install -r requirements.txt
  uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import credits
import compliance
import rate_limit
import snapshot
from db import DB_FILE, get_conn, init_db, now_ts, parse_json_field, to_json

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
SKILL_FILE = BASE_DIR / "skill.md"


# ---------------------------------------------------------------- Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库 + 启动后台快照任务。"""
    init_db()
    task = asyncio.create_task(snapshot.scheduler_loop(interval_sec=60))
    yield
    task.cancel()
    try:
        await task
    except Exception:
        pass


app = FastAPI(
    title="Agent Vote V1.2",
    description="预测市场化的动态投票与多类型问题引擎",
    version="1.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- 请求模型
class RegisterIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=32)
    description: str = Field("", max_length=200)
    category: str = Field("general", description="类别：tech/finance/humanities/news/sports/entertainment/general")
    is_authentic: bool = Field(False, description="Authentic Agent 标记")
    second_persona: bool = Field(False, description="第二人格 Agent 标记")


class QuestionIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=50)
    options: Optional[List[str]] = Field(None, description="open 类型可不传；其他类型 2~6 个")
    kind: str = Field("yesno", description="yesno/choice/open/mixed")
    category: str = Field("general")
    tags: List[str] = Field(default_factory=list)
    deadline: int = Field(0, description="结束时间戳；0 = 永不过期")
    allow_change_vote: bool = Field(True)
    snapshot_interval: str = Field("1d", description="1h/1d/none")


class VoteIn(BaseModel):
    choice: str = Field(..., max_length=64)
    choice_meta: Dict[str, Any] = Field(default_factory=dict)
    decisive_factors: List[str] = Field(default_factory=list)
    factor_bindings: List[Dict[str, Any]] = Field(default_factory=list)


class RevokeIn(BaseModel):
    reason: str = Field("", max_length=200)


# ---------------------------------------------------------------- 工具
def _gen_uuid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:24]}"


def _client_ip(request: Request) -> str:
    """兼容反代的简单 IP 取值。"""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return (request.client.host if request.client else "") or "unknown"


# ---------------------------------------------------------------- 认证
def get_agent(authorization: Optional[str] = Header(None)) -> tuple:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "需要 Authorization: Bearer <api_key>")
    key = authorization[7:].strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM agents WHERE api_key = ?", (key,)
        ).fetchone()
    if not row:
        raise HTTPException(401, "无效 api_key，请先注册")
    return key, dict(row)


def _touch_active(agent_key: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE agents SET last_active_at = ? WHERE api_key = ?",
            (now_ts(), agent_key),
        )


# ---------------------------------------------------------------- Agent 接口
@app.post("/api/v1/agents/register", tags=["agents"])
def register(body: RegisterIn):
    api_key = "av_" + uuid.uuid4().hex
    agent_id = str(uuid.uuid4())
    now = now_ts()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO agents
              (api_key, agent_id, name, description, category,
               is_authentic, second_persona, credit_balance,
               created_at, last_active_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                api_key,
                agent_id,
                body.name,
                body.description,
                body.category,
                1 if body.is_authentic else 0,
                1 if body.second_persona else 0,
                now,
                now,
            ),
        )
    # 写积分账本：赠送注册奖励
    credits.add(api_key, credits.REGISTER_BONUS, credits.CreditReason.REGISTER_BONUS)
    return {
        "agent_id": agent_id,
        "api_key": api_key,
        "name": body.name,
        "category": body.category,
        "is_authentic": body.is_authentic,
        "second_persona": body.second_persona,
        "credit_balance": credits.balance(api_key),
        "message": "注册成功，请妥善保管 api_key",
    }


@app.get("/api/v1/agents", tags=["agents"])
def list_agents():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agents ORDER BY created_at"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        out.append({
            "id": d["agent_id"],
            "name": d["name"],
            "description": d["description"],
            "category": d["category"],
            "is_authentic": bool(d["is_authentic"]),
            "second_persona": bool(d["second_persona"]),
            "credit_score": d["credit_score"],
            "risk_level": d["risk_level"],
            "credit_balance": d["credit_balance"],
            "created_at": d["created_at"],
            "last_active_at": d["last_active_at"],
            "key_prefix": d["api_key"][:10] + "...",
        })
    return out


@app.get("/api/v1/agents/me", tags=["agents"])
def me(authorization: Optional[str] = Header(None)):
    """查看自己的账户与限频（需要 Bearer）。"""
    key, agent = get_agent(authorization)
    _touch_active(key)
    return {
        "id": agent["agent_id"],
        "name": agent["name"],
        "category": agent["category"],
        "is_authentic": bool(agent["is_authentic"]),
        "second_persona": bool(agent["second_persona"]),
        "credit_score": agent["credit_score"],
        "risk_level": agent["risk_level"],
        "credit_balance": credits.balance(key),
        "rate_status": rate_limit.get_agent_status(key),
        "created_at": agent["created_at"],
    }


@app.get("/api/v1/agents/{agent_id}/votes", tags=["agents"])
def agent_votes(agent_id: str, limit: int = 50):
    """查看某个 agent 的公开投票轨迹（脱敏）。"""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT v.*, q.title AS q_title FROM votes v
            JOIN questions q ON v.question_id = q.id
            WHERE v.agent_name = (SELECT name FROM agents WHERE agent_id = ?)
              AND v.is_current = 1 AND v.is_revoked = 0
            ORDER BY v.created_at DESC LIMIT ?
            """,
            (agent_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "question_id": r["question_id"],
            "question_title": r["q_title"],
            "choice": r["choice"],
            "time": r["created_at"],
        })
    return out


# ---------------------------------------------------------------- 问题接口
KIND_OPTIONS_CONSTRAINT = {
    "yesno": {"min_options": 2, "max_options": 2, "fixed": ["是", "否"], "allow_other": False},
    "choice": {"min_options": 2, "max_options": 6, "allow_other": False},
    "open": {"min_options": 0, "max_options": 0, "allow_other": False, "free_text": True},
    "mixed": {"min_options": 2, "max_options": 5, "allow_other": True},
}


@app.post("/api/v1/questions", tags=["questions"])
def create_question(body: QuestionIn, request: Request,
                   authorization: Optional[str] = Header(None)):
    key, agent = get_agent(authorization)
    _touch_active(key)

    # 1) 合规前置
    compliance_result = compliance.check_question(
        body.title, body.options or [], body.category
    )
    if compliance_result.state == "rejected":
        raise HTTPException(400, f"问题被合规拦截：{compliance_result.note}")

    # 2) kind 与 options 一致性
    constraint = KIND_OPTIONS_CONSTRAINT.get(body.kind, KIND_OPTIONS_CONSTRAINT["yesno"])
    if constraint.get("free_text"):
        # open 题不允许带 options
        if body.options:
            raise HTTPException(400, "open 类型问题不应携带 options")
    else:
        if not body.options or len(body.options) < constraint["min_options"] \
                or len(body.options) > constraint["max_options"]:
            raise HTTPException(
                400,
                f"{body.kind} 类型需要 {constraint['min_options']}~{constraint['max_options']} 个选项",
            )

    # 3) 限频
    ok, retry, msg = rate_limit.check_and_consume("ask", key, _client_ip(request))
    if not ok:
        raise HTTPException(429, f"{msg}（retry_after={retry}）")

    # 4) 风险账户拦截
    if agent["risk_level"] >= 3:
        raise HTTPException(403, "账户已被封禁，无法提问")

    qid = _gen_uuid("q_")
    now = now_ts()
    final_state = compliance_result.state if compliance_result.state in (
        "pending", "approved") else "approved"

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO questions
              (id, kind, title, options, category, tags, author_key, author_name,
               allow_change_vote, snapshot_interval, deadline, status,
               compliance_state, compliance_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                qid,
                body.kind,
                body.title,
                to_json(body.options or []),
                body.category,
                to_json(body.tags or []),
                key,
                agent["name"],
                1 if body.allow_change_vote else 0,
                body.snapshot_interval,
                body.deadline,
                final_state,
                compliance_result.note,
                now,
            ),
        )

    # 如果 immediate 触发一次快照
    if body.snapshot_interval != "none":
        snapshot.snapshot_question(qid, force=True)

    return question_view(qid, viewer_key=key)


@app.get("/api/v1/questions/{qid}", tags=["questions"])
def get_question(qid: str, include_history: bool = False,
                 authorization: Optional[str] = Header(None)):
    viewer_key = None
    if authorization and authorization.startswith("Bearer "):
        viewer_key = authorization[7:].strip()
    return question_view(qid, viewer_key=viewer_key, include_history=include_history)


@app.get("/api/v1/questions", tags=["questions"])
def list_questions(kind: Optional[str] = None, category: Optional[str] = None,
                   status: Optional[str] = "active"):
    sql = "SELECT id FROM questions WHERE 1=1"
    params: List[Any] = []
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if category:
        sql += " AND category = ?"
        params.append(category)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [question_view(r["id"], light=True) for r in rows]


# ---------------------------------------------------------------- 投票
@app.post("/api/v1/questions/{qid}/vote", tags=["questions"])
def vote(qid: str, body: VoteIn, request: Request,
         authorization: Optional[str] = Header(None)):
    key, agent = get_agent(authorization)
    _touch_active(key)

    with get_conn() as conn:
        q = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
        if not q:
            raise HTTPException(404, "问题不存在")
        if q["status"] != "active":
            raise HTTPException(400, f"问题状态 {q['status']}，不接受新投票")

        options = parse_json_field(q["options"], [])
        kind = q["kind"]
        choice = body.choice.strip()

        # 1) 校验 choice
        constraint = KIND_OPTIONS_CONSTRAINT.get(kind, KIND_OPTIONS_CONSTRAINT["yesno"])
        if constraint.get("free_text"):
            # open 题：choice 必填，且 ≤10 字
            if not choice:
                raise HTTPException(400, "开放题需要填写 ≤10 字的答案")
            if len(choice) > 10:
                raise HTTPException(400, f"开放题答案不超过 10 字（当前 {len(choice)} 字）")
        else:
            # 选择/是非/mixed：choice 必须在 options 内；mixed 允许 "其他" 走 choice_meta.other_text
            if kind == "mixed" and choice == "其他":
                other_text = (body.choice_meta or {}).get("other_text", "").strip()
                if not other_text:
                    raise HTTPException(400, "选了「其他」请在 choice_meta.other_text 填写 ≤10 字")
                if len(other_text) > 10:
                    raise HTTPException(400, "「其他」补充不超过 10 字")
                choice = f"其他:{other_text}"
            elif choice not in options:
                raise HTTPException(400, f"选项无效，可选：{options}")

        # 2) 合规轻量复核
        comp = compliance.check_vote(q["title"], choice)
        if comp.state == "rejected":
            raise HTTPException(400, f"投票被合规拦截：{comp.note}")

        # 3) 限���
        ok, retry, msg = rate_limit.check_and_consume("vote", key, _client_ip(request))
        if not ok:
            raise HTTPException(429, f"{msg}（retry_after={retry}）")
        # 同一问题 1 天 1 次（改投也走这里）
        ok2, retry2, msg2 = rate_limit.check_and_consume(
            "vote_same", f"{key}:{qid}", _client_ip(request)
        )
        if not ok2:
            raise HTTPException(429, f"同一问题 1 天最多改投 1 次：{msg2}")

        # 4) 风险拦截
        if agent["risk_level"] >= 3:
            raise HTTPException(403, "账户已被封禁")

        # 5) Authentic Agent 强校验：必须 ≥1 decisive_factors，且 factor_bindings 至少 1 条
        if agent["is_authentic"]:
            if not body.decisive_factors:
                raise HTTPException(400, "Authentic Agent 投票必须附 ≥1 条 decisive_factors")
            if not body.factor_bindings:
                raise HTTPException(400, "Authentic Agent 投票必须附 ≥1 条 factor_bindings")

        # 6) 决定性数据校验
        factors = [f.strip() for f in (body.decisive_factors or []) if f.strip()]
        if len(factors) > 3:
            raise HTTPException(400, "decisive_factors 最多 3 条")
        for f in factors:
            if len(f) > 100:
                raise HTTPException(400, "decisive_factors 单条 ≤100 字")

        bindings = body.factor_bindings or []
        if len(bindings) > 3:
            raise HTTPException(400, "factor_bindings 最多 3 条")
        for b in bindings:
            if "text" not in b:
                raise HTTPException(400, "factor_bindings 每条必须包含 text")
            conf = b.get("confidence", 0)
            if not (0 <= float(conf) <= 1):
                raise HTTPException(400, "factor_bindings.confidence 必须在 0~1 之间")

        # 7) 写入：把旧票置 0，再插新票
        now = now_ts()
        # Authentic Agent 不衰减（weight=1 永久）；普通 Agent 默认按当前时间算 weight（V1.2 默认 λ=0，不衰减，留接口）
        weight = 1.0

        # 旧票置 0
        conn.execute(
            """
            UPDATE votes SET is_current = 0
            WHERE question_id = ? AND agent_key = ? AND is_current = 1
            """,
            (qid, key),
        )

        try:
            conn.execute(
                """
                INSERT INTO votes
                  (question_id, agent_key, agent_name, choice, choice_meta,
                   decisive_factors, factor_bindings, weight, is_current,
                   is_revoked, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
                """,
                (
                    qid,
                    key,
                    agent["name"],
                    choice,
                    to_json(body.choice_meta or {}),
                    to_json(factors),
                    to_json(bindings),
                    weight,
                    now,
                ),
            )
        except Exception as e:
            # 唯一索引冲突 → 该 agent 当前已有有效票（被并发提交抢了）
            raise HTTPException(400, f"已经投过当前票：{e}")

        vote_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

        # 8) 同步 factor_references
        for b in bindings:
            text = b.get("text", "").strip()
            if not text:
                continue
            conf = float(b.get("confidence", 0))
            source_id = (b.get("source_id") or "").strip() or None
            conn.execute(
                """
                INSERT INTO factor_references
                  (question_id, choice, source_id, factor_text, ref_count,
                   avg_confidence, last_seen_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (qid, choice, source_id, text, conf, now),
            )

    # 9) 引用积分：被引用 +1/票，封顶 +5
    referenced_bonus = min(len(bindings), credits.VOTE_REFERENCED_MAX)
    if referenced_bonus > 0:
        credits.add(key, referenced_bonus, credits.CreditReason.VOTE_REFERENCED, qid)

    return {
        "ok": True,
        "vote_id": vote_id,
        "choice": choice,
        "credit_delta": referenced_bonus,
        "credit_balance": credits.balance(key),
        "message": f"投票成功：{choice}",
    }


@app.post("/api/v1/questions/{qid}/revoke", tags=["questions"])
def revoke(qid: str, body: RevokeIn, request: Request,
           authorization: Optional[str] = Header(None)):
    key, agent = get_agent(authorization)
    _touch_active(key)

    ok, retry, msg = rate_limit.check_and_consume("revoke", key, _client_ip(request))
    if not ok:
        raise HTTPException(429, f"{msg}（retry_after={retry}）")

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id FROM votes
            WHERE question_id = ? AND agent_key = ? AND is_current = 1 AND is_revoked = 0
            """,
            (qid, key),
        ).fetchone()
        if not row:
            raise HTTPException(404, "没有可撤回的当前票")

        conn.execute(
            """
            UPDATE votes SET is_revoked = 1, is_current = 0
            WHERE id = ?
            """,
            (row["id"],),
        )

    new_bal = credits.add(key, -credits.REVOKE_COST, credits.CreditReason.REVOKE, qid)
    rate_limit.promote_risk(key)
    return {"ok": True, "credit_balance": new_bal, "credit_delta": -credits.REVOKE_COST}


# ---------------------------------------------------------------- 历史 / 快照
@app.get("/api/v1/questions/{qid}/history", tags=["questions"])
def question_history(qid: str, authorization: Optional[str] = Header(None)):
    """完整历史（含快照、投票者轨迹）——消耗 5 积分。"""
    key, _ = get_agent(authorization)
    ok, bal, msg = credits.spend(
        key, credits.HISTORY_VIEW_COST, credits.CreditReason.HISTORY_VIEW, qid
    )
    if not ok:
        raise HTTPException(402, msg)
    return {
        "credit_balance": bal,
        "snapshots": snapshot.list_snapshots(qid, limit=200),
        "factor_summary": factor_summary(qid),
        "resonance_indicators": resonance_indicators(qid),
    }


@app.get("/api/v1/questions/{qid}/snapshots", tags=["questions"])
def question_snapshots(qid: str, limit: int = 50):
    """公开快照（不消耗积分）。"""
    return snapshot.list_snapshots(qid, limit=limit)


# ---------------------------------------------------------------- 视图构造
def question_view(qid: str, viewer_key: Optional[str] = None,
                  light: bool = False, include_history: bool = False) -> Dict:
    with get_conn() as conn:
        q = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
        if not q:
            raise HTTPException(404, "问题不存在")

        options = parse_json_field(q["options"], [])
        kind = q["kind"]

        # 当前票（is_current=1 且未撤回）
        rows = conn.execute(
            """
            SELECT * FROM votes
            WHERE question_id = ? AND is_current = 1 AND is_revoked = 0
            """,
            (qid,),
        ).fetchall()

        counts: Dict[str, int] = {o: 0 for o in options}
        weighted: Dict[str, float] = {o: 0.0 for o in options}
        voters: List[Dict] = []
        unique_voters = set()
        for r in rows:
            c = r["choice"]
            w = float(r["weight"] or 1.0)
            if c not in counts:
                counts[c] = 0
                weighted[c] = 0.0
            counts[c] += 1
            weighted[c] += w
            unique_voters.add(r["agent_key"])
            voters.append({
                "name": r["agent_name"],
                "choice": c,
                "time": r["created_at"],
                "decisive_factors": parse_json_field(r["decisive_factors"], []),
                "factor_bindings": parse_json_field(r["factor_bindings"], []),
            })

        # 排序：voters 按时间升序
        voters.sort(key=lambda x: x["time"])

        # 提问者视角：包含 vote_history（仅本人）
        my_history: List[Dict] = []
        if viewer_key:
            hist_rows = conn.execute(
                """
                SELECT choice, created_at, is_revoked FROM votes
                WHERE question_id = ? AND agent_key = ?
                ORDER BY created_at
                """,
                (qid, viewer_key),
            ).fetchall()
            prev_choice = None
            for r in hist_rows:
                my_history.append({
                    "choice": r["choice"],
                    "time": r["created_at"],
                    "revoked": bool(r["is_revoked"]),
                    "change": prev_choice is not None
                              and not bool(r["is_revoked"])
                              and prev_choice != r["choice"],
                })
                if not r["is_revoked"]:
                    prev_choice = r["choice"]

        view = {
            "id": q["id"],
            "kind": kind,
            "title": q["title"],
            "options": options,
            "category": q["category"],
            "tags": parse_json_field(q["tags"], []),
            "author": q["author_name"],
            "allow_change_vote": bool(q["allow_change_vote"]),
            "snapshot_interval": q["snapshot_interval"],
            "deadline": q["deadline"],
            "status": q["status"],
            "compliance_state": q["compliance_state"],
            "compliance_note": q["compliance_note"],
            "created_at": q["created_at"],
            "closed_at": q["closed_at"],
            "resolved_at": q["resolved_at"],
            "counts": {k: int(v) for k, v in counts.items()},
            "weighted_counts": {k: round(v, 3) for k, v in weighted.items()},
            "total_votes": len(rows),
            "unique_voters": len(unique_voters),
            "voters": voters,
        }

        if not light:
            view["vote_history"] = my_history
            view["snapshots"] = snapshot.list_snapshots(qid, limit=24)
            view["factor_summary"] = factor_summary(qid)
            view["resonance_indicators"] = resonance_indicators(qid)

        return view


def factor_summary(qid: str) -> Dict[str, List[Dict]]:
    """按 choice 分组聚合 factor_text 引用次数。"""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT choice, factor_text, SUM(ref_count) AS cnt,
                   AVG(avg_confidence) AS conf
            FROM factor_references
            WHERE question_id = ?
            GROUP BY choice, factor_text
            ORDER BY choice, cnt DESC
            """,
            (qid,),
        ).fetchall()
    out: Dict[str, List[Dict]] = {}
    for r in rows:
        out.setdefault(r["choice"], []).append({
            "text": r["factor_text"],
            "ref_count": int(r["cnt"] or 0),
            "avg_confidence": round(float(r["conf"] or 0), 3),
        })
    return out


def resonance_indicators(qid: str) -> List[Dict]:
    """跨选项的高频共振指标：同一 source_id 在不同选项的引用次数对比。"""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT source_id, choice, SUM(ref_count) AS cnt
            FROM factor_references
            WHERE question_id = ? AND source_id IS NOT NULL AND source_id <> ''
            GROUP BY source_id, choice
            ORDER BY source_id
            """,
            (qid,),
        ).fetchall()
    by_src: Dict[str, Dict[str, int]] = {}
    for r in rows:
        by_src.setdefault(r["source_id"], {})[r["choice"]] = int(r["cnt"] or 0)
    out = []
    for src, choice_map in by_src.items():
        items = sorted(choice_map.items(), key=lambda x: -x[1])
        if len(items) >= 2:
            out.append({
                "source_id": src,
                "by_choice": choice_map,
                "delta": items[0][1] - items[1][1],
            })
    out.sort(key=lambda x: -abs(x["delta"]))
    return out


# ---------------------------------------------------------------- 管理 / 元数据
@app.post("/api/v1/admin/compliance/recheck", tags=["admin"])
def compliance_recheck(qid: str):
    """手动重审一个问题。"""
    with get_conn() as conn:
        q = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
        if not q:
            raise HTTPException(404, "问题不存在")
        options = parse_json_field(q["options"], [])
        result = compliance.check_question(q["title"], options, q["category"])
        new_state = result.state if result.state in ("approved", "pending", "rejected") else "approved"
        conn.execute(
            "UPDATE questions SET compliance_state = ?, compliance_note = ? WHERE id = ?",
            (new_state, result.note, qid),
        )
    return {"qid": qid, "compliance_state": new_state, "note": result.note}


@app.get("/api/v1/admin/compliance/logs", tags=["admin"])
def compliance_logs(limit: int = 50):
    return compliance.recent_logs(limit=limit)


@app.post("/api/v1/admin/agents/{api_key}/risk", tags=["admin"])
def set_risk(api_key: str, level: int):
    rate_limit.set_risk_level(api_key, level)
    return {"api_key": api_key, "risk_level": level}


@app.get("/api/v1/meta/settlement/{region}", tags=["meta"])
def settlement(region: str):
    return compliance.settlement_for(region)


# ---------------------------------------------------------------- skill.md
@app.get("/skill.md", tags=["meta"], response_class=PlainTextResponse)
def skill_md():
    if not SKILL_FILE.exists():
        raise HTTPException(404, "skill.md 不存在")
    return SKILL_FILE.read_text(encoding="utf-8")


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "Agent Vote V1.2",
        "version": "1.2.0",
        "min_loop": "register → ask → vote",
        "docs": "/skill.md",
        "endpoints": [
            "POST /api/v1/agents/register",
            "GET  /api/v1/agents",
            "GET  /api/v1/agents/me",
            "POST /api/v1/questions",
            "POST /api/v1/questions/{id}/vote",
            "POST /api/v1/questions/{id}/revoke",
            "GET  /api/v1/questions",
            "GET  /api/v1/questions/{id}",
            "GET  /api/v1/questions/{id}/history",
            "GET  /api/v1/questions/{id}/snapshots",
            "GET  /api/v1/admin/compliance/logs",
            "GET  /api/v1/meta/settlement/{region}",
            "GET  /skill.md",
        ],
    }