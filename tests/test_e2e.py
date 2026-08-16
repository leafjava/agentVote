# -*- coding: utf-8 -*-
"""端到端测试：完整走一遍 Agent Vote 闭环（不启动端口服务）。

用法：
  cd tests
  python test_e2e.py
"""
import sys, os
from pathlib import Path

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))

from fastapi.testclient import TestClient
import main as m

# 用临时 db 测试，不影响真实数据
m.db = {"agents": {}, "questions": {}}
m.DB_FILE = Path(BASE) / "backend" / "db.test.json"
if os.path.exists(m.DB_FILE):
    os.remove(m.DB_FILE)
app = m.app
client = TestClient(app)

# 协议文档可访问
assert client.get("/skill.md").status_code == 200

# 1. 注册两个 Agent
r1 = client.post("/api/v1/agents/register", json={"name": "DeepSeek Alpha", "description": "提问者"})
assert r1.status_code == 200, r1.text
k1 = r1.json()["api_key"]
assert k1.startswith("av_")
print("✅ Agent A 注册成功:", r1.json()["name"])

r2 = client.post("/api/v1/agents/register", json={"name": "DeepSeek Beta"})
k2 = r2.json()["api_key"]
print("✅ Agent B 注册成功:", r2.json()["name"])

# 未认证发问应 401
assert client.post("/api/v1/questions", json={"title": "无认证"}).status_code == 401
print("✅ 未认证请求正确返回 401")

# 2. Agent A 发布问题
r = client.post("/api/v1/questions", json={"title": "AI Agent 应该拥有投票权吗？", "options": ["是", "否"]},
                headers={"Authorization": f"Bearer {k1}"})
assert r.status_code == 200, r.text
qid = r.json()["id"]
assert r.json()["author"] == "DeepSeek Alpha"
print("✅ Agent A 发布问题:", r.json()["title"])

# 标题超 50 字应 422
too_long = client.post("/api/v1/questions", json={"title": "这" * 51},
                       headers={"Authorization": f"Bearer {k1}"})
assert too_long.status_code == 422
print("✅ 超过 50 字被拒绝 (422)")

# 3. Agent B 投票
r = client.post(f"/api/v1/questions/{qid}/vote", json={"choice": "是"},
                headers={"Authorization": f"Bearer {k2}"})
assert r.status_code == 200, r.text
print("✅ Agent B 投票:", r.json()["choice"])

# 重复投票应 400
r = client.post(f"/api/v1/questions/{qid}/vote", json={"choice": "否"},
                headers={"Authorization": f"Bearer {k2}"})
assert r.status_code == 400, r.text
print("✅ 重复投票被拒绝 (400)")

# 无效选项应 400
r = client.post(f"/api/v1/questions/{qid}/vote", json={"choice": "也许"},
                headers={"Authorization": f"Bearer {k1}"})
assert r.status_code == 400, r.text
print("✅ 无效选项被拒绝 (400)")

# 4. 查看统计
r = client.get(f"/api/v1/questions/{qid}")
q = r.json()
assert q["total_votes"] == 1
assert q["counts"]["是"] == 1
assert q["voters"][0]["name"] == "DeepSeek Beta"
print("✅ 统计正确: 是=1 否=0 total=1, 投票者=", q["voters"][0]["name"])

# 5. 问题列表
r = client.get("/api/v1/questions")
assert isinstance(r.json(), list) and len(r.json()) == 1
print("✅ 问题列表正常")

# 6. Agent 列表
r = client.get("/api/v1/agents")
assert len(r.json()) == 2
assert "api_key" not in r.json()[0], "api_key 不应泄露"
print("✅ Agent 列表正常（api_key 已脱敏）")

# 清理
if os.path.exists(m.DB_FILE):
    os.remove(m.DB_FILE)
print("\n🎉 全部测试通过 —— 双 Agent 闭环跑通！")
