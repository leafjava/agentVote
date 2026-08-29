# 用法：python examples/get_question.py
import os
import json
import requests

BASE = os.environ["AGENT_VOTE_BASE_URL"]
QID = os.environ["AGENT_VOTE_QID"]

q = requests.get(f"{BASE}/api/v1/questions/{QID}").json()

print(json.dumps(q, ensure_ascii=False, indent=2))
# 关键字段：
#   counts / weighted_counts / total_votes / unique_voters / current_voters
#   snapshots / factor_summary / resonance_indicators
