# 用法：
#   1) 让 FastAPI 后端跑在 http://127.0.0.1:8000
#   2) 浏览器打开投票广场 http://localhost:3000/demo
#   3) 或脚本里硬编码：
#        python examples/multi_llm_vote.py <question_id>
#
# V1.3 多 LLM 集体智能：
#   一键让 DeepSeek Beta / Grok Gamma / Moonshot Delta 三家 LLM 自动注册
#   并投票同一问题。后端用 subprocess 调 agents/agent_runner.py --vote
#   --qid <id> --voters deepseek,grok,moonshot，每家独立决策 → 决策依据图谱
#   天然带跨模型对比。
#
# 关键参数：
#   wait=true (默认)：同步等 3 个 voter 全部跑完再返回（实测 15~25 秒）
#   wait=false：fire-and-forget，立即返回 status="started"
#   mock=true：所有 provider 走内置模板，不消耗真实 API
import os
import sys
import time

import requests

BASE = os.environ.get("AGENT_VOTE_BASE_URL", "http://127.0.0.1:8000")
QID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AGENT_VOTE_QID", "")

if not QID:
    # 列出第一个活跃问题
    qs = requests.get(f"{BASE}/api/v1/questions?status=active").json()
    if not qs:
        print("❌ 投票广场为空，先去 /demo 发布一个问题")
        sys.exit(1)
    QID = qs[0]["id"]
    print(f"ℹ️  未指定 qid，自动选取第一个问题：{qs[0]['title']}（{QID}）")

VOTERS = ["deepseek", "grok", "moonshot"]  # 默认三选三
WAIT = True                                    # 同步等结果
MOCK = False                                   # 真实 LLM 调用（需 .env 配 key）

print(f"🚀 触发 {len(VOTERS)} 家 LLM 集体投票：{VOTERS}")
print(f"   qid = {QID}")
print(f"   wait = {WAIT}, mock = {MOCK}")

t0 = time.time()
resp = requests.post(
    f"{BASE}/api/v1/questions/{QID}/multi-llm-vote",
    json={"voters": VOTERS, "wait": WAIT, "mock": MOCK},
    timeout=300,
).json()

print()
print(f"✅ 状态：{resp.get('status')}")
print(f"   voters: {resp.get('voters')}")
print(f"   returncode: {resp.get('returncode')}")
if resp.get("message"):
    print(f"   message: {resp['message']}")
print(f"   用时：{time.time() - t0:.1f}s")

# 拉一次问题详情看结果
print()
print("--- 投票后状态 ---")
q = requests.get(f"{BASE}/api/v1/questions/{QID}").json()
print(f"title: {q['title']}")
print(f"counts: {q.get('counts')}")
print(f"total_votes: {q.get('total_votes')}")
print("voters:")
for v in q.get("voters", []):
    print(
        f"  · {v['name']:<22} -> {v['choice']:<6}"
        f"  ({len(v.get('decisive_factors', []))} 理由 /"
        f" {len(v.get('factor_bindings', []))} 绑定)"
    )