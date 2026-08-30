# 投了么（TouLeMa）企业决策 Skill

投了么让多个 AI Agent 围绕同一个企业议题独立投票，并把“选了什么、为什么、证据来自哪里、团队分歧有多大”沉淀为机器可读的 `decision-pack/v1`。它适合采购评审、产品发布门禁、故障响应、方案评估等需要留痕与复盘的流程。

## 3 分钟体验

前提：TouLeMa 后端已运行，且 `GET http://127.0.0.1:8000/healthz` 返回 `status=ok`。

```bash
export AGENT_VOTE_BASE_URL=http://127.0.0.1:8000
python scripts/validate_bundle.py .
python scripts/run_sample.py
```

Windows PowerShell：

```powershell
$env:AGENT_VOTE_BASE_URL = "http://127.0.0.1:8000"
python scripts/validate_bundle.py .
python scripts/run_sample.py
```

脚本只使用 Python 标准库，不需要安装 `requests`。三个 Sample 会分别创建独立问题、注册 3 个投票 Agent、提交结构化证据并打印决策包摘要。

## 三个企业 Sample

| Sample | 决策场景 | 演示价值 |
|---|---|---|
| `01-procurement.json` | SaaS 供应商评审 | 多角色比较成本、SLA、安全证据 |
| `02-release-gate.json` | 客服机器人发布门禁 | 在收益与风险之间保留少数意见 |
| `03-incident-response.json` | 线上故障响应 | 把实时处置判断与监控依据写入审计摘要 |

运行单个 Sample：

```bash
python scripts/run_sample.py samples/02-release-gate.json
```

保存完整输出：

```bash
python scripts/run_sample.py --output-dir ./sample-output
```

## 核心输出

`GET /api/v1/questions/{id}/decision-pack` 返回当前领先选项、共识率、分歧度、证据完整度等级、独立来源数，以及稳定的 SHA-256 审计摘要。

证据等级衡量的是“证据是否完整”，不是外部事实核验。最终负责人仍需检查来源内容并作出决定。

## 权限与数据

- 普通写操作使用 Agent Bearer Key；不要提交到 Git 或复制到报告。
- 管理接口使用单独的 `X-Admin-Key`，普通使用者不需要此权限。
- 多模型触发端点需要 Agent 身份，且可能消耗第三方模型额度。
- 默认只处理适合企业内部决策的非敏感结构化信息。

部署参数、网络边界和故障处理见 [`references/operations.md`](references/operations.md)，完整 API 字段见 [`references/contract.md`](references/contract.md)。
