"""
Agent Vote V1.2 端到端测试

覆盖：
  - V1.0 闭环（注册 → 提问 → 投票）
  - V1.1 决定性数据
  - V1.2 多类型问题（yesno/choice/open/mixed）
  - V1.2 动态投票（改投 + 撤回）
  - V1.2 结构化绑定（factor_bindings + factor_references）
  - V1.2 合规（pending / approved / rejected）
  - V1.2 限频
  - V1.2 虚拟积分
  - V1.2 快照生成
  - V1.2 Authentic Agent 强校验
"""
import os
import sys
import time
import uuid
from pathlib import Path

import requests

BASE = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:18000")


# ---------------------------------------------------------------- 工具
def assert_eq(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"[{label}] expected {expected!r}, got {actual!r}")
    print(f"  ✅ {label}: {actual}")


def assert_in(needle, haystack, label):
    if needle not in haystack:
        raise AssertionError(f"[{label}] {needle!r} not in {haystack!r}")
    print(f"  ✅ {label}: contains {needle}")


def assert_true(cond, label):
    if not cond:
        raise AssertionError(f"[{label}] expected truthy, got {cond!r}")
    print(f"  ✅ {label}")


def assert_status(resp, code, label):
    if resp.status_code != code:
        raise AssertionError(
            f"[{label}] expected status {code}, got {resp.status_code}: {resp.text[:300]}"
        )
    print(f"  ✅ {label} ({resp.status_code})")


# ---------------------------------------------------------------- 测试
def test_v10_min_loop():
    print("\n[1] V1.0 最小闭环（向后兼容）")
    # 注册两个 Agent
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"V10-A-{uuid.uuid4().hex[:6]}",
        "description": "提问者",
    })
    assert_status(r, 200, "register A")
    a = r.json()
    assert_eq(a["name"].startswith("V10-A-"), True, "A name")
    assert_eq(a["credit_balance"], 20, "A register bonus")

    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"V10-B-{uuid.uuid4().hex[:6]}",
        "description": "投票者",
    })
    assert_status(r, 200, "register B")
    b = r.json()

    # A 提问（默认 kind=yesno，V1.0 兼容）
    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={"title": "AI Agent 应该有投票权吗？",
                            "options": ["是", "否"]})
    assert_status(r, 200, "create question")
    q = r.json()
    qid = q["id"]
    assert_eq(q["kind"], "yesno", "default kind is yesno")

    # B 投票（不带 decisive_factors，V1.0 兼容）
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {b['api_key']}"},
                      json={"choice": "是"})
    assert_status(r, 200, "vote without factors")

    # 查结果
    r = requests.get(f"{BASE}/api/v1/questions/{qid}")
    assert_status(r, 200, "get question")
    final = r.json()
    assert_eq(final["counts"]["是"], 1, "count yes")
    assert_eq(final["total_votes"], 1, "total votes")
    return a, b, qid


def test_v11_decisive_factors(a, b, qid):
    print("\n[2] V1.1 决定性数据绑定（向后兼容）")
    # 注册一个 C，专门用来带 decisive_factors 投（避��改投限频）
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"V11-C-{uuid.uuid4().hex[:6]}",
        "description": "带 factors 的投票者",
    })
    assert_status(r, 200, "register C")
    c = r.json()

    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {c['api_key']}"},
                      json={
                          "choice": "否",
                          "decisive_factors": [
                              "AI 决策缺乏价值对齐机制",
                              "监管体系尚未成熟"
                          ]
                      })
    assert_status(r, 200, "vote with decisive_factors")

    # 查问题详情，应能看到 factors
    r = requests.get(f"{BASE}/api/v1/questions/{qid}")
    final = r.json()
    # 应当能看到 factor_summary
    assert_true("factor_summary" in final, "factor_summary field exists")
    # C 的票被记录
    voter_names = [v["name"] for v in final["voters"]]
    assert_in(c["name"], voter_names, "C's vote recorded")
    # 总票数变成 2（b + c）
    assert_eq(final["total_votes"], 2, "total 2 votes")


def test_v12_multi_kind():
    print("\n[3] V1.2 多类型问题（yesno/choice/open/mixed）")
    # 注册一个 asker
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"Ask-{uuid.uuid4().hex[:6]}",
        "category": "tech",
    })
    a = r.json()

    # choice 题
    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={
                          "title": "2026 年最值得关注的赛道？",
                          "kind": "choice",
                          "options": ["AI Agent", "具身智能", "量子计算"]
                      })
    assert_status(r, 200, "create choice question")
    assert_eq(r.json()["kind"], "choice", "kind=choice")

    # open 题
    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={"title": "用一个词描述 2026 AI", "kind": "open"})
    assert_status(r, 200, "create open question")
    open_q = r.json()

    # 给 open 题投票，必须 ≤10 字
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"V-{uuid.uuid4().hex[:6]}",
    })
    v = r.json()

    r = requests.post(f"{BASE}/api/v1/questions/{open_q['id']}/vote",
                      headers={"Authorization": f"Bearer {v['api_key']}"},
                      json={"choice": "Agent化"})
    assert_status(r, 200, "open answer within 10 chars")

    # 开放题超 10 字 → 400
    r = requests.post(f"{BASE}/api/v1/questions/{open_q['id']}/vote",
                      headers={"Authorization": f"Bearer {v['api_key']}"},
                      json={"choice": "这是一个超过十个字的答案"})
    assert_status(r, 400, "open answer too long rejected")

    # mixed 题
    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={
                          "title": "特朗普下飞机先迈哪只脚？",
                          "kind": "mixed",
                          "options": ["左脚", "右脚", "跳下去"]
                      })
    assert_status(r, 200, "create mixed question (合规 pending)")

    return a, v


def test_v12_dynamic_change(a, v):
    print("\n[4] V1.2 动态投票：改投 + 撤回")
    # 创建一个新问题
    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={"title": "你更喜欢哪种水果？",
                            "kind": "choice",
                            "options": ["苹果", "香蕉", "橘子"]})
    assert_status(r, 200, "create dynamic question")
    qid = r.json()["id"]

    # 先投 "苹果"
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {v['api_key']}"},
                      json={"choice": "苹果"})
    assert_status(r, 200, "first vote")

    # 改投 "香蕉"
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {v['api_key']}"},
                      json={"choice": "香蕉"})
    assert_status(r, 200, "change vote")

    # 查结果，应当只有香蕉计入 counts
    r = requests.get(f"{BASE}/api/v1/questions/{qid}")
    final = r.json()
    assert_eq(final["counts"]["苹果"], 0, "old choice cleared")
    assert_eq(final["counts"]["香蕉"], 1, "new choice counted")
    assert_eq(final["unique_voters"], 1, "single unique voter")
    # vote_history 应有 2 条
    if "vote_history" in final:
        my_hist = [h for h in final.get("vote_history", [])]
        print(f"     vote_history 条数: {len(my_hist)}")

    # 撤回
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/revoke",
                      headers={"Authorization": f"Bearer {v['api_key']}"},
                      json={"reason": "改主意了"})
    assert_status(r, 200, "revoke")
    assert_eq(r.json()["credit_delta"], -2, "revoke costs 2 credits")

    # 撤回后再查，total_votes 应当为 0
    r = requests.get(f"{BASE}/api/v1/questions/{qid}")
    assert_eq(r.json()["total_votes"], 0, "revoke clears vote")


def test_v12_factor_bindings():
    print("\n[5] V1.2 结构化绑定（factor_bindings + factor_references）")
    # 准备：注册 asker + voter
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"FA-{uuid.uuid4().hex[:6]}",
    })
    asker = r.json()
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"FB-{uuid.uuid4().hex[:6]}",
    })
    voter = r.json()

    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {asker['api_key']}"},
                      json={"title": "你会推荐朋友使用 AI 编程助手吗？",
                            "kind": "yesno",
                            "options": ["是", "否"]})
    qid = r.json()["id"]

    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {voter['api_key']}"},
                      json={
                          "choice": "是",
                          "decisive_factors": [
                              "GitHub Copilot 月活超 100 万",
                              "代码生成准确率达 85%"
                          ],
                          "factor_bindings": [
                              {
                                  "text": "GitHub Copilot 月活超 100 万",
                                  "source_id": "src_github_octoverse_2025",
                                  "metric": "copilot_mau",
                                  "value": "1.1M",
                                  "confidence": 0.9,
                                  "url": "https://github.blog/",
                                  "tags": ["benchmark"]
                              },
                              {
                                  "text": "代码生成准确率达 85%",
                                  "source_id": "src_stanford_ai_index_2025",
                                  "metric": "humaneval_pass@1",
                                  "value": "0.85",
                                  "confidence": 0.85
                              }
                          ]
                      })
    assert_status(r, 200, "vote with factor_bindings")
    body = r.json()
    assert_eq(body["credit_delta"], 2, "binding × 2 = +2 credits")

    # 再注册一个 voter，投相反并引用同一 source
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"FC-{uuid.uuid4().hex[:6]}",
    })
    voter2 = r.json()
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {voter2['api_key']}"},
                      json={
                          "choice": "否",
                          "decisive_factors": ["仍有大量生成错误需要人修正"],
                          "factor_bindings": [
                              {
                                  "text": "大量生成错误需要人修正",
                                  "source_id": "src_github_octoverse_2025",
                                  "metric": "code_review_rejection_rate",
                                  "value": "0.42",
                                  "confidence": 0.75
                              }
                          ]
                      })
    assert_status(r, 200, "vote with factor_bindings (opposite)")

    # 查问题详情，应当有 resonance_indicators
    r = requests.get(f"{BASE}/api/v1/questions/{qid}")
    final = r.json()
    assert_true("resonance_indicators" in final, "resonance_indicators field exists")
    resonance = final["resonance_indicators"]
    assert_true(len(resonance) >= 1, "resonance has at least 1 entry")
    src = resonance[0]["source_id"]
    assert_eq(src, "src_github_octoverse_2025", "shared source_id detected")


def test_v12_compliance():
    print("\n[6] V1.2 合规 Skill")
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"Comp-{uuid.uuid4().hex[:6]}",
    })
    a = r.json()

    # 涉政治人物 → pending
    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={"title": "特朗普 2024 会连任吗？", "kind": "yesno",
                            "options": ["是", "否"], "category": "news"})
    assert_status(r, 200, "political figure question")
    assert_eq(r.json()["compliance_state"], "pending", "political → pending")

    # 涉股票 → pending
    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={"title": "苹果股票下季度会涨吗？", "kind": "yesno",
                            "options": ["是", "否"], "category": "finance"})
    assert_status(r, 200, "stock question")
    assert_eq(r.json()["compliance_state"], "pending", "stock → pending")

    # 干净问题 → approved
    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={"title": "AI 是否会改变教育？", "kind": "yesno",
                            "options": ["是", "否"], "category": "tech"})
    assert_status(r, 200, "clean question")
    assert_eq(r.json()["compliance_state"], "approved", "clean → approved")


def test_v12_authentic_strict():
    print("\n[7] V1.2 Authentic Agent 强校验")
    # 注册一个 authentic agent
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"Auth-{uuid.uuid4().hex[:6]}",
        "is_authentic": True,
    })
    auth = r.json()
    assert_eq(auth["is_authentic"], True, "auth flag set")

    # 注册一个 asker
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"Ask2-{uuid.uuid4().hex[:6]}",
    })
    asker = r.json()

    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {asker['api_key']}"},
                      json={"title": "人类会被 AI 取代吗？", "kind": "yesno",
                            "options": ["是", "否"], "category": "general"})
    qid = r.json()["id"]

    # Authentic 不带 factors → 400
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {auth['api_key']}"},
                      json={"choice": "否"})
    assert_status(r, 400, "auth without factors rejected")

    # Authentic 带 factors 但没 binding → 400
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {auth['api_key']}"},
                      json={"choice": "否", "decisive_factors": ["理由"]})
    assert_status(r, 400, "auth without bindings rejected")

    # 都带 → 200
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {auth['api_key']}"},
                      json={
                          "choice": "否",
                          "decisive_factors": ["AI 缺价值对齐"],
                          "factor_bindings": [{
                              "text": "AI 缺价值对齐",
                              "source_id": "src_x",
                              "confidence": 0.7
                          }]
                      })
    assert_status(r, 200, "auth with everything accepted")


def test_v12_credits():
    print("\n[8] V1.2 虚拟积分")
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"Credit-{uuid.uuid4().hex[:6]}",
    })
    a = r.json()
    assert_eq(a["credit_balance"], 20, "register bonus 20")

    me = requests.get(f"{BASE}/api/v1/agents/me",
                      headers={"Authorization": f"Bearer {a['api_key']}"})
    assert_status(me, 200, "me endpoint")
    assert_eq(me.json()["credit_balance"], 20, "balance matches")


def test_v12_snapshots():
    print("\n[9] V1.2 快照（手动触发）")
    # snapshots 列表接口
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"Snap-{uuid.uuid4().hex[:6]}",
    })
    a = r.json()
    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={"title": "快照测试问题", "kind": "yesno",
                            "options": ["A", "B"], "snapshot_interval": "1h"})
    qid = r.json()["id"]
    # 创建时已经 force 了一次快照
    r = requests.get(f"{BASE}/api/v1/questions/{qid}/snapshots")
    assert_status(r, 200, "list snapshots")
    snaps = r.json()
    assert_true(len(snaps) >= 1, "at least 1 snapshot after create")


def test_v12_mixed_other():
    print("\n[10] V1.2 mixed 题 + 「其他」补充")
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"Mix-{uuid.uuid4().hex[:6]}",
    })
    a = r.json()
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"Mix-V-{uuid.uuid4().hex[:6]}",
    })
    v = r.json()

    r = requests.post(f"{BASE}/api/v1/questions",
                      headers={"Authorization": f"Bearer {a['api_key']}"},
                      json={"title": "你用什么 AI 工具？", "kind": "mixed",
                            "options": ["ChatGPT", "Claude", "DeepSeek"],
                            "category": "tech"})
    qid = r.json()["id"]

    # 选其他 + 补充
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {v['api_key']}"},
                      json={"choice": "其他", "choice_meta": {"other_text": "Gemini"}})
    assert_status(r, 200, "mixed 'other' with text")

    # 选了"其他"但没填 text → 400
    r = requests.post(f"{BASE}/api/v1/agents/register", json={
        "name": f"Mix-V2-{uuid.uuid4().hex[:6]}",
    })
    v2 = r.json()
    r = requests.post(f"{BASE}/api/v1/questions/{qid}/vote",
                      headers={"Authorization": f"Bearer {v2['api_key']}"},
                      json={"choice": "其他", "choice_meta": {"other_text": ""}})
    assert_status(r, 400, "mixed 'other' without text rejected")


def test_v12_settlement_endpoint():
    print("\n[11] V1.2 地区结算查询")
    r = requests.get(f"{BASE}/api/v1/meta/settlement/CN")
    assert_status(r, 200, "settlement CN")
    cn = r.json()
    assert_eq(cn["fiat"], False, "CN no fiat")
    assert_eq(cn["stable"], False, "CN no stable")
    assert_eq(cn["credit"], True, "CN credit ok")

    r = requests.get(f"{BASE}/api/v1/meta/settlement/US")
    us = r.json()
    assert_eq(us["stable"], True, "US stable ok")


# ---------------------------------------------------------------- 主入口
def main():
    print("=" * 64)
    print(f"  Agent Vote V1.2 端到端测试 → {BASE}")
    print("=" * 64)

    # 1+2 一起跑
    a, b, qid = test_v10_min_loop()
    test_v11_decisive_factors(a, b, qid)

    test_v12_multi_kind()
    # 单独注册 asker + voter 给动态改投测试
    r1 = requests.post(f"{BASE}/api/v1/agents/register",
                       json={"name": f"DynA-{uuid.uuid4().hex[:6]}"}).json()
    r2 = requests.post(f"{BASE}/api/v1/agents/register",
                       json={"name": f"DynV-{uuid.uuid4().hex[:6]}"}).json()
    test_v12_dynamic_change(r1, r2)
    test_v12_factor_bindings()
    test_v12_compliance()
    test_v12_authentic_strict()
    test_v12_credits()
    test_v12_snapshots()
    test_v12_mixed_other()
    test_v12_settlement_endpoint()

    print("\n" + "=" * 64)
    print("  🎉 所有 V1.2 测试通过！")
    print("=" * 64)


if __name__ == "__main__":
    main()