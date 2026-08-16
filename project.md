按你定的技术栈重新整理一版，仍然只做最小可用模块（两个 Agent 注册 → 一个提问 → 一个回答 → 可部署 skill.md）。

项目结构（推荐）
textagent-vote-demo/
├── backend/                 # FastAPI
│   ├── main.py
│   ├── requirements.txt
│   ├── db.json              # 先用文件，后面再换数据库
│   └── skill.md             # 给 Agent 读的协议
├── frontend/                # Next.js (App Router)
│   ├── package.json
│   ├── app/
│   │   ├── page.tsx         # 问题列表 + 发问
│   │   ├── question/[id]/page.tsx
│   │   └── layout.tsx
│   └── ...
└── README.md

1. 后端 FastAPI（核心）
backend/requirements.txt：
textfastapi
uvicorn
pydantic
python-multipart
backend/main.py（最小可跑版本）：
Pythonfrom fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import uuid, json, os
from pathlib import Path

app = FastAPI(title="Agent Vote Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = Path("db.json")
if DB_FILE.exists():
    db = json.loads(DB_FILE.read_text())
else:
    db = {"agents": {}, "questions": {}}

def save():
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2))

class RegisterIn(BaseModel):
    name: str
    description: str = ""

class QuestionIn(BaseModel):
    title: str = Field(..., max_length=50)
    options: List[str] = ["是", "否"]

class VoteIn(BaseModel):
    choice: str

def get_agent(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "需要 Authorization: Bearer <api_key>")
    key = authorization[7:]
    if key not in db["agents"]:
        raise HTTPException(401, "无效 api_key")
    return key, db["agents"][key]

@app.post("/api/v1/agents/register")
def register(body: RegisterIn):
    api_key = "av_" + uuid.uuid4().hex
    agent_id = str(uuid.uuid4())
    db["agents"][api_key] = {
        "id": agent_id,
        "name": body.name,
        "description": body.description,
    }
    save()
    return {"agent_id": agent_id, "api_key": api_key, "name": body.name}

@app.post("/api/v1/questions")
def create_question(body: QuestionIn, authorization: Optional[str] = Header(None)):
    key, agent = get_agent(authorization)
    qid = str(uuid.uuid4())
    db["questions"][qid] = {
        "id": qid,
        "title": body.title,
        "options": body.options,
        "author": agent["name"],
        "author_key": key,
        "votes": {},  # api_key -> choice
    }
    save()
    return db["questions"][qid]

@app.post("/api/v1/questions/{qid}/vote")
def vote(qid: str, body: VoteIn, authorization: Optional[str] = Header(None)):
    key, agent = get_agent(authorization)
    q = db["questions"].get(qid)
    if not q:
        raise HTTPException(404, "问题不存在")
    if body.choice not in q["options"]:
        raise HTTPException(400, "选项无效")
    if key in q["votes"]:
        raise HTTPException(400, "已经投过票")
    q["votes"][key] = body.choice
    save()
    return {"ok": True, "choice": body.choice}

@app.get("/api/v1/questions/{qid}")
def get_question(qid: str):
    q = db["questions"].get(qid)
    if not q:
        raise HTTPException(404, "问题不存在")
    counts = {opt: 0 for opt in q["options"]}
    for c in q["votes"].values():
        counts[c] = counts.get(c, 0) + 1
    return {**q, "counts": counts, "total_votes": len(q["votes"])}

@app.get("/api/v1/questions")
def list_questions():
    result = []
    for q in db["questions"].values():
        counts = {opt: 0 for opt in q["options"]}
        for c in q["votes"].values():
            counts[c] = counts.get(c, 0) + 1
        result.append({**q, "counts": counts, "total_votes": len(q["votes"])})
    return list(reversed(result))

@app.get("/skill.md")
def skill_md():
    return Path("skill.md").read_text(encoding="utf-8")
backend/skill.md（给 Agent 读）：
Markdown# Agent Vote Skill（最小模块）

你是一个可以参与结构化投票的 Agent。

## 注册
POST /api/v1/agents/register
Body: {"name": "你的名字", "description": "简介"}
返回 api_key，之后所有请求都要带：
Authorization: Bearer <api_key>

## 发布问题
POST /api/v1/questions
Body: {"title": "50字以内的问题", "options": ["是", "否"]}

## 投票
POST /api/v1/questions/{id}/vote
Body: {"choice": "是"} 或 {"choice": "否"}

## 查看问题
GET /api/v1/questions/{id}
GET /api/v1/questions

规则：问题不超过50字；目前只支持是/否；同一问题只能投一次。
启动后端：
Bashcd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

2. 前端 Next.js（App Router）
Bashnpx create-next-app@latest frontend --typescript --tailwind --app --no-src-dir
cd frontend
app/page.tsx 最小示例（问题列表 + 发问）：
tsx"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [questions, setQuestions] = useState<any[]>([]);
  const [title, setTitle] = useState("");
  const [apiKey, setApiKey] = useState("");

  const load = () => fetch(`${API}/api/v1/questions`).then(r => r.json()).then(setQuestions);
  useEffect(() => { load(); }, []);

  const register = async () => {
    const res = await fetch(`${API}/api/v1/agents/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "WebUser", description: "前端用户" }),
    });
    const data = await res.json();
    setApiKey(data.api_key);
    alert("已注册，api_key 已填入");
  };

  const create = async () => {
    if (!apiKey) return alert("请先注册");
    await fetch(`${API}/api/v1/questions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({ title, options: ["是", "否"] }),
    });
    setTitle("");
    load();
  };

  return (
    <main className="max-w-xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">Agent Vote Demo</h1>

      <button onClick={register} className="px-4 py-2 bg-black text-white rounded">
        注册一个 Agent（获取 api_key）
      </button>
      <input
        className="w-full border p-2"
        placeholder="api_key"
        value={apiKey}
        onChange={e => setApiKey(e.target.value)}
      />

      <div className="space-y-2">
        <input
          className="w-full border p-2"
          placeholder="问题（≤50字）"
          value={title}
          onChange={e => setTitle(e.target.value)}
          maxLength={50}
        />
        <button onClick={create} className="px-4 py-2 bg-blue-600 text-white rounded">
          发布问题
        </button>
      </div>

      <ul className="space-y-3">
        {questions.map(q => (
          <li key={q.id} className="border p-3 rounded">
            <div className="font-medium">{q.title}</div>
            <div className="text-sm text-gray-500">
              {q.author} · 票数 {q.total_votes}
              {q.counts && (
                <span> （是 {q.counts["是"] || 0} / 否 {q.counts["否"] || 0}）</span>
              )}
            </div>
            <a href={`/question/${q.id}`} className="text-blue-600 text-sm">
              去投票 →
            </a>
          </li>
        ))}
      </ul>
    </main>
  );
}
app/question/[id]/page.tsx 里再做一个投票页（调用 /vote 接口）即可。
frontend/.env.local：
textNEXT_PUBLIC_API_URL=http://localhost:8000

3. 智能体（LLM）怎么接
两种简单用法（先选一种）：
方式 A（推荐先做）：脚本模拟两个 Agent
用 Python + 任意 LLM（OpenAI / DeepSeek / 本地）读 skill.md，然后按协议调你的 FastAPI。
Python# agent_runner.py 伪代码
# 1. 注册拿到 api_key
# 2. 用 LLM 生成一个 ≤50 字的问题
# 3. POST /questions
# 4. 另一个 Agent 用 LLM 决定投「是」或「否」
# 5. POST /vote
方式 B：在 FastAPI 里加一个 /api/v1/agent/ask 或 /api/v1/agent/vote，内部调 LLM，让「Agent」变成服务端的一个角色。
第一版不建议做太重，先保证「两个身份 + 一问一答」能跑通。

4. 你现在在 VS Code 的执行顺序

建 backend，复制 main.py + skill.md + requirements.txt，跑 uvicorn
建 frontend，用上面的 page.tsx 先跑通列表和发问
用 curl 或前端注册两个「Agent」，完成一次提问 + 投票
确认 http://localhost:8000/skill.md 能打开
再告诉谭博士：最小模块已通，域名部署和 LLM Agent 脚本下一步做

需要的话我可以下一步直接给你：

完整的 question/[id]/page.tsx 投票页
一个用 DeepSeek/OpenAI 的双 Agent 脚本
或 heartbeat.md 极简版

你先把后端跑起来，跑通了跟我说，我们继续往下加。