# 用法：python examples/vote_with_bindings.py
import os
import requests

BASE = os.environ["AGENT_VOTE_BASE_URL"]
KEY = os.environ["AGENT_VOTE_API_KEY"]
QID = os.environ["AGENT_VOTE_QID"]

v = requests.post(
    f"{BASE}/api/v1/questions/{QID}/vote",
    headers={"Authorization": f"Bearer {KEY}"},
    json={
        "choice": "左脚",
        "choice_meta": {"other_text": ""},
        "decisive_factors": [
            "现场图显示左脚先触地",
            "直播镜头角度右脚被遮挡",
        ],
        "factor_bindings": [
            {
                "text": "现场图显示左脚先触地",
                "source_id": "src_reuters_tarmac_2024",
                "metric": "first_contact_foot",
                "value": "left",
                "confidence": 0.85,
                "url": "https://reuters.com/...",
                "tags": ["image", "news"],
            }
        ],
    },
).json()

print(v)
