# 投了么（TouLeMa）ClawHive 参赛说明书

版本：1.3.0 · 赛道：业务自动化 · 交付形态：企业多 Agent 决策 Skill

## 1. 产品目的

企业已经开始让多个数字员工分别做采购分析、质量评估、安全审查和运维判断，但最后的“集体决策”往往仍停留在聊天记录与人工复制。TouLeMa 把这些独立判断收束成统一协议：每张票都携带决定性因素与结构化证据，系统再生成可被 OA、CRM、审计或复盘流程消费的决策包。

目标用户：采购委员会、产品发布委员会、SRE 事故指挥、运营评审、企业 AI 平台管理员。

不适用：替代医疗、法律、投资或其他高风险事项的人类最终决策；未经授权处理个人数据或商业秘密；把自报置信度宣称为事实核验。

## 2. 核心能力

1. 多 Agent 独立投票：`yesno / choice / open / mixed` 四类问题。
2. 证据结构化：因素文本与 `source_id / metric / value / confidence / url / tags`。
3. 动态决策：改投、撤回、当前票与历史记录分离、时间桶快照。
4. 决策包：领先选项、共识率、分歧度、证据覆盖、独立来源、A–D 等级、SHA-256 摘要。
5. 企业控制：Bearer Key、Admin Key、CORS 白名单、合规状态、限频、风险等级、虚拟积分流水。
6. 可选多模型：DeepSeek、Grok、Moonshot 可作为独立投票 Agent；三个比赛 Sample 不依赖模型 Key。

## 3. 安装与启动

### 3.1 环境

- Python 3.10+
- Node.js 18+（只看 API/Swagger 可不安装）
- 本地 Demo 最低 256 MB 可用内存；不需要 GPU

### 3.2 后端

```powershell
cd backend
python -m pip install -r requirements.txt
$env:AGENT_VOTE_DB_PATH = "../.data/agent_vote.sqlite"
$env:AGENT_VOTE_ADMIN_TOKEN = "replace-with-a-random-admin-token"
$env:AGENT_VOTE_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

成功条件：`GET /healthz` 返回 `{"status":"ok","version":"1.3.0"}`；Swagger 位于 `/docs`。

### 3.3 前端

```powershell
cd frontend
npm ci
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
npm run dev
```

访问 `http://localhost:3000/demo`。

### 3.4 Skill

ClawHive 市场上传文件是 `skill-build/agent-vote.zip`。源码根目录内含 `SKILL.md`、`README.md`、`_meta.json`、脚本、3 个 Sample、提示词与按需引用。安装后自然语言触发示例：

- “让采购、安全、运维三个 Agent 评审两家客服平台，给我决策包。”
- “把这次版本发布做成多 Agent 门禁，保留反对意见和证据。”
- “让 SRE、研发、容量 Agent 对事故处置投票并生成审计摘要。”

## 4. 三个 Sample 验收

运行：

```powershell
$env:AGENT_VOTE_BASE_URL = "http://127.0.0.1:8000"
python skill-build/agent-vote/scripts/run_sample.py --output-dir ./.sample-output
```

### Sample 1：SaaS 供应商评审

- 角色：采购、安全、运维。
- 选项：供应商甲、供应商乙、延后采购。
- 预期：供应商乙 2 : 1；A 级证据；3 个来源。
- 商业意义：多数意见不会吞掉运维对 SLA 的反对证据。

### Sample 2：客服机器人发布门禁

- 角色：质量、业务、风控。
- 选项：是、否。
- 预期：发布 2 : 1；A 级证据；3 个来源。
- 商业意义：发布收益与 1.8% 安全越权风险同时进入决策包，责任人可以附条件放行。

### Sample 3：线上故障响应

- 角色：SRE、研发、容量。
- 选项：回滚版本、扩容集群、切换只读。
- 预期：回滚版本 2 : 1；A 级证据；3 个来源。
- 商业意义：发布时序、代码差异与容量压力被共同保留，便于事后复盘判断是否正确。

每次运行使用新的 Agent 与问题 ID，审计摘要随当前状态生成；输出目录保存完整 `decision-pack.json`。

## 5. Decision Pack 解释

`decision.state`：

- `ready`：有票且只有一个领先选项。
- `tie`：最高票并列。
- `insufficient_data`：尚无有效票。

`consensus_ratio = 最高票数 / 当前有效票数`；`disagreement_index = 1 - consensus_ratio`。

证据门禁：

| 等级 | 条件 |
|---|---|
| A | ≥3 当前票；绑定覆盖 ≥80%；平均自报置信度 ≥0.8；≥2 独立来源 |
| B | ≥2 当前票；绑定覆盖 ≥60%；平均自报置信度 ≥0.65 |
| C | 有票且至少存在因素或绑定 |
| D | 无可用证据 |

`audit.digest` 是规范 JSON 的 SHA-256。规范内容包括问题 ID、票数、加权票数、当前投票者、选择、因素和绑定。相同决策状态得到相同摘要；任何当前票或证据变化都会改变摘要。

## 6. 权限、安全与合规

| 能力 | 所需权限 |
|---|---|
| 健康、问题、快照、决策包 | 公开只读 |
| 发布、投票、改投、撤回、多模型触发 | Agent Bearer Key |
| 合规重审、日志、风险等级 | `X-Admin-Key` |

部署要求：

- 生产必须启用 TLS、密钥轮换、访问日志脱敏与网络隔离。
- `AGENT_VOTE_DB_PATH` 指向持久卷；SQLite/WAL 不进入 Git 或 ZIP。
- CORS 明确列出可信来源；不要使用通配来源携带凭证。
- `pending` / `rejected` 必须进入人工流程。
- 429 不自动重放；网络失败不伪造结果。
- 自报 `confidence` 不是外部事实核验；对关键来源必须由责任人或授权连接器复核。

## 7. 自动化质量证据

| 门禁 | 覆盖 |
|---|---|
| `tests/test_e2e.py` | V1.0 注册、提问、投票、统计、脱敏兼容 |
| `tests/test_v12_e2e.py` | 11 组完整链路：多类型、改投、撤回、绑定、合规、Authentic、积分、快照、地区 |
| `tests/test_enterprise.py` | 决策包、稳定哈希、Admin 鉴权、多模型鉴权、健康检查、CORS |
| `scripts/validate_bundle.py` | frontmatter、3+ Sample、引用、Python 语法、敏感信息、运行产物 |
| `npm run build` | Next.js production compile、lint、类型检查与静态生成 |

## 8. 故障排查

| 现象 | 处理 |
|---|---|
| `python` 打开 Microsoft Store | 安装 Python 3.10+，或使用真实解释器绝对路径 |
| `/healthz` 不通 | 检查 uvicorn、端口、防火墙和 `AGENT_VOTE_DB_PATH` 父目录权限 |
| 401 | 检查 Bearer Key；管理接口另检查 `X-Admin-Key` |
| 429 | 等待错误中的 `retry_after`，不要循环重试 |
| Sample 合规状态非 approved | Sample 文件被改动或规则升级；停止并人工检查 |
| SQLite locked | 保持单写实例；高并发生产迁移到服务型数据库 |
| 多模型失败 | 检查模型 Key 与回调地址；生产不自动伪装成 mock |

## 9. 商业落地

初始客户：已部署企业 AI Agent、但缺少跨 Agent 决策治理的团队。交付方式可分为：

1. ClawHive 市场 Skill：开箱体验与标准场景。
2. 企业私有部署：接入内网 OA、CRM、知识库与审计系统。
3. 行业模板：采购、发布、事故、运营等决策 Schema 与合规规则包。

衡量指标：每次决策参与 Agent 数、证据绑定覆盖率、人工复核耗时、因证据不足被退回比例、复盘可追溯率。当前项目不虚构收入、客户或市场份额。

## 10. 提交清单

- [x] ≥3 个 Sample。
- [x] 5 分钟内 Demo 脚本。
- [x] 详细说明书。
- [x] 路演 PPTX。
- [x] Skill ZIP 与 Bundle 校验器。
- [x] 后端/前端/测试源码。
- [x] 商业价值、创新性、完整度、稳定性逐项证据。

最终上传前重新运行 Bundle、3 Sample、后端测试、前端构建和 PPT 视觉检查。
