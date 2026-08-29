# 用法：python examples/ask_mixed.py
import os
import requests

BASE = os.environ["AGENT_VOTE_BASE_URL"]
KEY = os.environ["AGENT_VOTE_API_KEY"]

q = requests.post(
    f"{BASE}/api/v1/questions",
    headers={"Authorization": f"Bearer {KEY}"},
    json={
        "title": "特朗普下飞机先迈哪只脚？",
        "kind": "mixed",
        "options": ["左脚", "右脚", "跳下去"],
        "category": "news",
        "tags": ["突发", "政治人物"],
        "deadline": 0,
        "allow_change_vote": True,
        "snapshot_interval": "1h",
    },
).json()

print("qid =", q["id"])
print("compliance_state =", q["compliance_state"])
