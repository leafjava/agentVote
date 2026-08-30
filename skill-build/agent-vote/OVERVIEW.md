# 投了么（TouLeMa）企业概览

TouLeMa 把多个 AI Agent 对同一业务问题的独立判断，沉淀成可解释、可验收、可审计的 `decision-pack/v1`。本文是产品概览；执行边界以 [`SKILL.md`](SKILL.md) 为准，字段以 [`references/contract.md`](references/contract.md) 为准。

## 适用场景

- 采购评审：采购、安全、技术分别评估供应商。
- 发布门禁：质量、业务、风控对上线条件投票。
- 事故响应：SRE、研发、容量 Agent 在回滚、扩容等处置中保留少数意见。
- 其他非高风险企业评审：使用统一选项和证据字段即可复用。

## 核心流程

```text
创建议题 → Agent 独立投票 → 绑定因素与来源 → 生成 Decision Pack → 人类责任人确认
```

每张当前票可包含：

- `choice`：选择。
- `decisive_factors`：1–3 条决定性因素。
- `factor_bindings`：稳定的 `source_id`、指标、值、链接和 Agent 自报置信度。

决策包输出领先选项、共识率、分歧度、证据覆盖、独立来源、A–D 完整度等级与 SHA-256 快照摘要。

## 三个可执行 Sample

| 场景 | 预期领先 | 共识 | 证据 |
|---|---|---:|---|
| SaaS 供应商评审 | 供应商乙 | 2:1 | A 级、3 来源 |
| 客服机器人发布门禁 | 是 | 2:1 | A 级、3 来源 |
| 线上故障响应 | 回滚版本 | 2:1 | A 级、3 来源 |

运行：

```powershell
python scripts/run_sample.py --output-dir .sample-output
```

## 可选多模型模式

后端提供需 Agent 认证的 `multi-llm-vote` 端点，可将 DeepSeek、Grok、Moonshot 当作独立投票者。该路径可能消耗外部模型额度并启动本地子进程，因此不是默认 Sample 的一部分。仅在用户明确要求时使用 [`examples/multi_llm_vote.py`](examples/multi_llm_vote.py)；脚本默认 `mock`，真实调用需显式加 `--live`。

## 安全与完整度

- Agent 写操作需 Bearer Key；管理操作需独立 `X-Admin-Key`。
- CORS 默认只允许本地前端，生产环境通过明确白名单配置。
- SQLite/WAL、密钥、日志、缓存不进入 Skill ZIP。
- `confidence` 为 Agent 自报；A 级是完整度门禁，不是外部事实认证。
- 医疗、法律、投资等高风险决策不得把 Skill 输出当作人类最终结论。

## 验收

```powershell
python scripts/validate_bundle.py .
```

校验器检查 Skill frontmatter、引用、3+ Sample、Python 语法、敏感信息与运行产物。
