# 用法：python examples/ask_mixed.py
import os
import requests

BASE = os.environ["AGENT_VOTE_BASE_URL"]
KEY = os.environ["AGENT_VOTE_API_KEY"]

q = requests.post(
    f"{BASE}/api/v1/questions",
    headers={"Authorization": f"Bearer {KEY}"},
    json={
        "title": "下季度优先升级哪个客服能力？",
        "kind": "mixed",
        "options": ["知识命中率", "响应速度", "自动分流"],
        "category": "tech",
        "tags": ["客服", "季度规划"],
        "deadline": 0,
        "allow_change_vote": True,
        "snapshot_interval": "1h",
    },
).json()

print("qid =", q["id"])
print("compliance_state =", q["compliance_state"])
