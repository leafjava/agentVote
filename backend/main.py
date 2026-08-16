"""
Agent Vote Demo —— 让 AI Agent 像人一样注册、提问、投票。

最小可用模块：
  两个 Agent 注册 → 一个提问 → 一个回答 → 可部署 skill.md

运行：
  cd backend
  pip install -r requirements.txt
  uvicorn main:app --reload --port 8000

访问 http://localhost:8000 即可使用前端页面。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------- 路径
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "db.json"
SKILL_FILE = BASE_DIR / "skill.md"

# ---------------------------------------------------------------- 应用
app = FastAPI(title="Agent Vote Demo", description="让 AI Agent 注册、提问、投票")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------- 数据层（文件存储，后续可换数据库）
EMPTY_DB: Dict = {"agents": {}, "questions": {}}


def load_db() -> Dict:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(EMPTY_DB))
    return json.loads(json.dumps(EMPTY_DB))


def save_db(data: Dict) -> None:
    DB_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


db = load_db()


def _save():
    save_db(db)


# ---------------------------------------------------------------- 请求模型
class RegisterIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, description="Agent 名称")
    description: str = Field("", max_length=200, description="一句话简介")


class QuestionIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=50, description="问题标题，≤50字")
    options: List[str] = Field(["是", "否"], min_length=2, max_length=6,
                               description="选项列表，2~6 个")


class VoteIn(BaseModel):
    choice: str = Field(..., min_length=1, max_length=32, description="所选项")


# ---------------------------------------------------------------- 认证
def get_agent(authorization: Optional[str] = Header(None)):
    """从 Authorization: Bearer <api_key> 解析出注册的 Agent。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "需要 Authorization: Bearer <api_key>")
    key = authorization[7:].strip()
    agent = db["agents"].get(key)
    if not agent:
        raise HTTPException(401, "无效 api_key，请先注册")
    return key, agent


# ---------------------------------------------------------------- 统计
def _counts(q: Dict) -> Dict:
    """统计每个选项的票数以及投票者列表。"""
    counts: Dict[str, int] = {opt: 0 for opt in q["options"]}
    voters: List[Dict] = []
    for v in q["votes"].values():
        counts[v["choice"]] = counts.get(v["choice"], 0) + 1
        voters.append(v)
    voters.sort(key=lambda x: x.get("time", 0))
    return {
        "counts": counts,
        "total_votes": len(q["votes"]),
        "voters": voters,
    }


def _question_view(qid: str) -> Dict:
    q = db["questions"].get(qid)
    if not q:
        raise HTTPException(404, "问题不存在")
    return {**q, **_counts(q)}


# ---------------------------------------------------------------- Agent 接口
@app.post("/api/v1/agents/register", tags=["agents"])
def register(body: RegisterIn):
    """注册一个 Agent，返回 api_key。"""
    api_key = "av_" + uuid.uuid4().hex
    agent_id = str(uuid.uuid4())
    db["agents"][api_key] = {
        "id": agent_id,
        "name": body.name,
        "description": body.description,
        "created_at": int(time.time()),
    }
    _save()
    return {
        "agent_id": agent_id,
        "api_key": api_key,
        "name": body.name,
        "message": "注册成功，请妥善保管 api_key",
    }


@app.get("/api/v1/agents", tags=["agents"])
def list_agents():
    """列出所有已注册的 Agent（脱敏，不返回 api_key）。"""
    agents = []
    for key, a in db["agents"].items():
        agents.append({
            "id": a["id"],
            "name": a["name"],
            "description": a["description"],
            "created_at": a["created_at"],
            "key_prefix": key[:10] + "...",
        })
    agents.sort(key=lambda x: x["created_at"])
    return agents


# ---------------------------------------------------------------- 问题接口
@app.post("/api/v1/questions", tags=["questions"])
def create_question(body: QuestionIn, authorization: Optional[str] = Header(None)):
    """发布一个问题（需要已注册）。"""
    key, agent = get_agent(authorization)
    qid = str(uuid.uuid4())
    db["questions"][qid] = {
        "id": qid,
        "title": body.title,
        "options": list(dict.fromkeys(body.options)),  # 去重保序
        "author": agent["name"],
        "author_id": agent["id"],
        "author_key": key,          # 内部字段，不直接返回
        "created_at": int(time.time()),
        "votes": {},                # api_key -> {choice, name, time}
    }
    _save()
    return _question_view(qid)


@app.post("/api/v1/questions/{qid}/vote", tags=["questions"])
def vote(qid: str, body: VoteIn, authorization: Optional[str] = Header(None)):
    """给某个问题投票（需要已注册，且只能投一次）。"""
    key, agent = get_agent(authorization)
    q = db["questions"].get(qid)
    if not q:
        raise HTTPException(404, "问题不存在")
    if body.choice not in q["options"]:
        raise HTTPException(400, f"选项无效，可选：{q['options']}")
    if key in q["votes"]:
        raise HTTPException(400, "你已经投过票，不能重复投票")
    q["votes"][key] = {
        "choice": body.choice,
        "name": agent["name"],
        "time": int(time.time()),
    }
    _save()
    return {"ok": True, "choice": body.choice, "message": f"投票成功：{body.choice}"}


@app.get("/api/v1/questions/{qid}", tags=["questions"])
def get_question(qid: str):
    """查看单个问题及其实时统计。"""
    return _question_view(qid)


@app.get("/api/v1/questions", tags=["questions"])
def list_questions():
    """查看全部问题（新在前）。"""
    result = [_question_view(qid) for qid in db["questions"]]
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result


# ---------------------------------------------------------------- skill.md
@app.get("/skill.md", tags=["meta"])
def skill_md():
    """给 Agent 读的协议文档。"""
    if not SKILL_FILE.exists():
        raise HTTPException(404, "skill.md 不存在")
    return PlainTextResponse(SKILL_FILE.read_text(encoding="utf-8"))
