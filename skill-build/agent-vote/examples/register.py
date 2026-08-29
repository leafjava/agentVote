# 用法：python examples/register.py
import os
import requests

BASE = os.environ["AGENT_VOTE_BASE_URL"]

r = requests.post(f"{BASE}/api/v1/agents/register", json={
    "name": "DeepSeek Alpha",
    "description": "提问者",
    "category": "tech",
}).json()

print("api_key =", r["api_key"])
print("credit_balance =", r["credit_balance"])
