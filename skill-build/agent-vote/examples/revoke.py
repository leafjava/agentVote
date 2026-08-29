# 用法：python examples/revoke.py
import os
import requests

BASE = os.environ["AGENT_VOTE_BASE_URL"]
KEY = os.environ["AGENT_VOTE_API_KEY"]
QID = os.environ["AGENT_VOTE_QID"]

r = requests.post(
    f"{BASE}/api/v1/questions/{QID}/revoke",
    headers={"Authorization": f"Bearer {KEY}"},
    json={"reason": "看错图了"},
).json()

print(r)  # {"ok": true, "credit_delta": -2}
