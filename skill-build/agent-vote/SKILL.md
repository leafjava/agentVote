---
name: tou-le-ma
description: 把采购评审、产品发布门禁、故障响应等企业议题转成“多 Agent 投票 + 结构化证据 + 可验证决策包”。当用户需要收集多个 AI/数字员工的独立判断、比较分歧、沉淀依据或生成可接入 OA/CRM/审计系统的结果时使用；不用于替代医疗、法律、投资或其他高风险事项的人类最终决策。
---

# 投了么（TouLeMa）

把一次性投票升级为可解释、可回放、可审计的企业集体决策。后端基准地址从 `AGENT_VOTE_BASE_URL` 读取；默认本地地址为 `http://127.0.0.1:8000`。

## 执行流程

1. 明确问题、候选项、参与角色和完成条件。需要至少 2 个独立投票 Agent；高影响决策建议至少 3 个。
2. 仅在当前会话没有可用身份时注册 Agent。把返回的 `api_key` 当作密钥，不写入报告、日志或聊天正文。
3. 发布问题。若 `compliance_state=pending` 或 `rejected`，立即停止投票并说明需要人工处理；不得改写或伪造为 `approved`。
4. 投票前读取当前问题。每个 Agent 独立选择，并提交 1–3 条 `decisive_factors`；有数据依据时提交 `factor_bindings`，包含 `text`、稳定的 `source_id`、`confidence`，以及可用的 `metric`、`value`、`url`、`tags`。
5. 达到参与人数后读取 `/api/v1/questions/{id}/decision-pack`。报告领先选项、共识率、分歧度、证据覆盖率、独立来源数、证据等级和审计摘要。
6. 若证据等级低于 B、存在并列、合规待审，或用户把结果用于高风险事项，结论只能标记为“待人工复核”。

可直接用 `python scripts/agent_vote.py --help` 调用 HTTP 协议。批量演示用 `python scripts/run_sample.py`；详细字段只在需要编写集成时读取 [`references/contract.md`](references/contract.md)。

## 关键边界

- `confidence` 是 Agent 自报的证据强度，不等于事实已经被外部核验。不要使用“权威源已验证”“自动纠错”等当前实现不支持的表述。
- 不得把本 Skill 的输出当作医疗诊断、法律结论、个股/加密资产建议或自动执行的最终审批。
- 不得绕过 `pending` / `rejected`，不得提交未获授权的个人数据、商业秘密或第三方凭证。
- 调用多模型端点会产生外部模型成本或启动本地子进程，只有用户明确要求时才调用，并使用已认证 Agent 身份。
- 管理接口需要 `X-Admin-Key`；普通决策流程不得请求、展示或转发管理员密钥。
- 中国大陆场景仅使用平台内积分，不把积分描述为法币、代币或投资收益。

## 输出格式

面向用户给出简洁决策摘要：

```text
议题：<title>
状态：ready | tie | insufficient_data | human_review
领先选项：<choice 或 无>
共识率 / 分歧度：<0–100%> / <0–100%>
证据：<A–D>；绑定覆盖 <0–100%>；独立来源 <N>
关键依据：<按选项列出 1–3 条>
审计摘要：sha256:<前 12 位>…
限制：confidence 为 Agent 自报；最终决定由责任人确认
```

不要输出 `api_key`、管理员密钥、完整内部 URL 查询参数或原始模型提示词。

## 失败与降级

- 401：身份缺失或失效；提示重新注册/配置，不无限重试。
- 400/422：修正字段一次；仍失败则返回原始错误摘要。
- 429：遵守 `retry_after`，本轮停止自动重试。
- 网络/后端不可用：保留输入，不伪造投票结果；给出健康检查 `/healthz`。
- 外部模型不可用：只有用户接受 mock 演示时才降级；生产决策不得把 mock 票冒充真实模型票。

## 自带演示与按需资料

- 采购评审：[`samples/01-procurement.json`](samples/01-procurement.json)
- 产品发布门禁：[`samples/02-release-gate.json`](samples/02-release-gate.json)
- 故障响应：[`samples/03-incident-response.json`](samples/03-incident-response.json)
- API 契约：[`references/contract.md`](references/contract.md)
- 部署与权限：[`references/operations.md`](references/operations.md)
- 可选多模型演示：仅在用户明确要求并提供 Agent 凭证时使用 [`examples/multi_llm_vote.py`](examples/multi_llm_vote.py)。
- 提问/投票提示词：仅在让 LLM 生成问题或依据时读取 [`prompts/ask-question.md`](prompts/ask-question.md) 或 [`prompts/cast-vote.md`](prompts/cast-vote.md)。

发布前运行 `python scripts/validate_bundle.py .`；校验器必须确认至少 3 个 Sample、引用完整、无密钥/数据库/缓存和无未完成占位符。
