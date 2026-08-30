# -*- coding: utf-8 -*-
"""企业级门禁：安全默认值、决策证据包、审计哈希与健康检查。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "backend"))

os.environ["AGENT_VOTE_ADMIN_TOKEN"] = "test-admin-token"

import db as dbm  # noqa: E402

_tmp = tempfile.TemporaryDirectory(
    prefix="agent-vote-enterprise-", ignore_cleanup_errors=True
)
dbm.DB_FILE = Path(_tmp.name) / "enterprise.sqlite"

import main as m  # noqa: E402

dbm.init_db()
client = TestClient(m.app)


def register(name: str) -> dict:
    response = client.post(
        "/api/v1/agents/register",
        json={"name": name, "category": "tech", "is_authentic": True},
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth(agent: dict) -> dict:
    return {"Authorization": f"Bearer {agent['api_key']}"}


asker = register("Enterprise-Asker")
voters = [register(f"Enterprise-Voter-{index}") for index in range(1, 4)]

question_response = client.post(
    "/api/v1/questions",
    headers=auth(asker),
    json={
        "title": "下一季度优先升级哪个客服能力？",
        "kind": "choice",
        "options": ["知识命中率", "首次响应速度", "工单自动分流"],
        "category": "tech",
        "tags": ["客服", "季度规划"],
        "snapshot_interval": "1d",
    },
)
assert question_response.status_code == 200, question_response.text
qid = question_response.json()["id"]

choices = ["知识命中率", "知识命中率", "工单自动分流"]
for index, (voter, choice) in enumerate(zip(voters, choices), start=1):
    vote_response = client.post(
        f"/api/v1/questions/{qid}/vote",
        headers=auth(voter),
        json={
            "choice": choice,
            "decisive_factors": [f"第 {index} 组客服质检显示该能力影响最大"],
            "factor_bindings": [
                {
                    "text": f"第 {index} 组客服质检样本",
                    "source_id": f"src_internal_qa_{index}",
                    "metric": "customer_effort_score",
                    "value": str(80 + index),
                    "confidence": 0.86,
                    "url": f"https://kb.example.com/qa/{index}",
                    "tags": ["internal", "qa"],
                }
            ],
        },
    )
    assert vote_response.status_code == 200, vote_response.text

pack_response = client.get(f"/api/v1/questions/{qid}/decision-pack")
assert pack_response.status_code == 200, pack_response.text
pack = pack_response.json()
assert pack["schema_version"] == "decision-pack/v1"
assert pack["decision"]["leading_choice"] == "知识命中率"
assert pack["decision"]["total_votes"] == 3
assert pack["evidence"]["grade"] == "A"
assert pack["evidence"]["binding_coverage"] == 1.0
assert pack["evidence"]["unique_sources"] == 3
assert len(pack["audit"]["digest"]) == 64
assert client.get(f"/api/v1/questions/{qid}/decision-pack").json()["audit"]["digest"] == pack["audit"]["digest"]
print("✅ 决策证据包：结论、覆盖率、分歧度与稳定 SHA-256 审计摘要通过")

assert client.get("/api/v1/admin/compliance/logs").status_code == 401
assert client.get(
    "/api/v1/admin/compliance/logs", headers={"X-Admin-Key": "wrong"}
).status_code == 401
assert client.get(
    "/api/v1/admin/compliance/logs",
    headers={"X-Admin-Key": "test-admin-token"},
).status_code == 200
print("✅ 管理接口默认受 X-Admin-Key 保护")

assert client.post(
    f"/api/v1/questions/{qid}/multi-llm-vote", json={"mock": True}
).status_code == 401
print("✅ 会触发模型/子进程的接口需要 Agent 身份")

health = client.get("/healthz")
assert health.status_code == 200 and health.json()["status"] == "ok"
print("✅ 健康检查通过")

cors_ok = client.options(
    "/healthz",
    headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    },
)
assert cors_ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
cors_blocked = client.options(
    "/healthz",
    headers={
        "Origin": "https://untrusted.example",
        "Access-Control-Request-Method": "GET",
    },
)
assert "access-control-allow-origin" not in cors_blocked.headers
print("✅ CORS 只允许显式配置的前端来源")

print("\n🎉 企业级门禁全部通过！")
