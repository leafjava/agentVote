# -*- coding: utf-8 -*-
"""V1.0 端到端兼容测试 —— 确保老接口行为不变。

用法：
  cd tests
  python test_e2e.py
"""
import os
import sys
from pathlib import Path

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))

from fastapi.testclient import TestClient

# 清掉旧的 V1.0 文件 db，强制 V1.2 SQLite 路径接管
old_db = Path(BASE) / "backend" / "db.json"
if old_db.exists():
    old_db.unlink()

import db as dbm
dbm.DB_FILE = Path(BASE) / "backend" / "test_agent_vote.sqlite"
if dbm.DB_FILE.exists():
    dbm.DB_FILE.unlink()
# 同时把 db.json 重命名走的迁移标识也清掉
for f in Path(BASE, "backend").glob("*.sqlite*"):
    try:
        f.unlink()
    except Exception:
        pass

import main as m
dbm.init_db()  # TestClient 默认不跑 lifespan
app = m.app
client = TestClient(app)


def fresh_name(prefix: str) -> str:
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


# 协议文档可访问
r = client.get("/skill.md")
assert r.status_code == 200, r.text
assert "Agent Vote Skill" in r.text
print("✅ skill.md 可访问")

# 1. 注册两个 Agent
r1 = client.post("/api/v1/agents/register",
                 json={"name": fresh_name("V10Alpha"), "description": "提问者"})
assert r1.status_code == 200, r1.text
k1 = r1.json()["api_key"]
assert k1.startswith("av_")
print(f"✅ Agent A 注册成功: {r1.json()['name']}（积分 {r1.json()['credit_balance']}）")

r2 = client.post("/api/v1/agents/register", json={"name": fresh_name("V10Beta")})
k2 = r2.json()["api_key"]
print(f"✅ Agent B 注册成功: {r2.json()['name']}")

# 未认证发问应 401
r = client.post("/api/v1/questions", json={"title": "无认证"})
assert r.status_code == 401
print("✅ 未认证请求正确返回 401")

# 2. Agent A 发布问题（V1.0 老 payload）
r = client.post("/api/v1/questions",
                json={"title": "AI Agent 应该拥有投票权吗？",
                      "options": ["是", "否"]},
                headers={"Authorization": f"Bearer {k1}"})
assert r.status_code == 200, r.text
qid = r.json()["id"]
assert r.json()["author"].startswith("V10Alpha")
assert r.json()["kind"] == "yesno"  # V1.2 默认��
print(f"✅ Agent A 发布问题: {r.json()['title']}")

# 标题超 50 字应 422
too_long = client.post("/api/v1/questions",
                       json={"title": "这" * 51},
                       headers={"Authorization": f"Bearer {k1}"})
assert too_long.status_code == 422
print("✅ 超过 50 字被拒绝 (422)")

# 3. Agent B 投票（V1.0 老 payload，只有 choice 字段）
r = client.post(f"/api/v1/questions/{qid}/vote",
                json={"choice": "是"},
                headers={"Authorization": f"Bearer {k2}"})
assert r.status_code == 200, r.text
print(f"✅ Agent B 投票: {r.json()['choice']}")

# 4. 查看统计（V1.0 老字段：counts/total_votes/voters）
r = client.get(f"/api/v1/questions/{qid}")
q = r.json()
assert q["total_votes"] == 1
assert q["counts"]["是"] == 1
assert q["voters"][0]["name"].startswith("V10Beta")
print(f"✅ 统计正确: 是=1 否=0 total=1, 投票者={q['voters'][0]['name']}")

# 5. 问题列表
r = client.get("/api/v1/questions")
assert isinstance(r.json(), list) and len(r.json()) == 1
print("✅ 问题列表正常")

# 6. Agent 列表（V1.0 字段：id/name/description/created_at/key_prefix）
r = client.get("/api/v1/agents")
agents = r.json()
assert len(agents) == 2
assert "api_key" not in agents[0]
assert "key_prefix" in agents[0]
print(f"✅ Agent 列表正常（api_key 已脱敏），共 {len(agents)} 个")

# 清理
try:
    dbm.DB_FILE.unlink()
except Exception:
    pass
print("\n🎉 V1.0 向后兼容测试全部通过！")