# TouLeMa 决赛 Demo 视频脚本（4:40）

目标：在 5 分钟限制内证明“真实可运行、企业有价值、Skill 可复用、安全边界清楚”。全程只展示已实现能力。

## 录制前准备

1. 后端运行在 `http://127.0.0.1:8000`，`/healthz` 为 200。
2. 前端运行在 `http://localhost:3000`，预先打开 `/demo`。
3. 终端位于仓库根目录，已设置 `AGENT_VOTE_BASE_URL`。
4. 浏览器准备两个标签：Demo 页、Swagger 的 `/api/v1/questions/{id}/decision-pack`。
5. 录制分辨率 1920×1080；浏览器缩放 90%；终端字号至少 20。

## 0:00–0:25｜问题：企业已经有 Agent，却没有集体决策资产

画面：标题页或项目首页。

口播：

> 企业里，采购 Agent、风控 Agent、运维 Agent 都能给建议，但最后常常只剩一段聊天记录。普通投票只告诉你二比一，无法回答为什么、反对者看到了什么、证据是否完整。TouLeMa 把多 Agent 判断沉淀成可审计的企业决策包。

## 0:25–0:55｜产品：一张票同时携带选择与证据

画面：问题详情页，快速扫过投票者因素卡片。

口播：

> 每个 Agent 独立选择，并提交决定性因素和结构化证据：来源 ID、指标、值、自报置信度与链接。系统保留改投、撤回和快照，再计算共识、分歧、证据覆盖与审计摘要。模型可以替换，协议与企业资产不会丢。

## 0:55–1:25｜Skill 完整度：不是一个 Prompt

画面：展开 `skill-build/agent-vote/` 目录；依次高亮 `SKILL.md`、`scripts/`、`samples/`、`references/`。

终端：

```powershell
python skill-build/agent-vote/scripts/validate_bundle.py skill-build/agent-vote
```

口播：

> 这是可上传 ClawHive 的完整 Skill。入口定义触发条件、授权边界、失败降级和输出格式；复杂字段按需加载；执行脚本只用 Python 标准库。发布前校验 frontmatter、引用、敏感信息、运行产物和至少三个 Sample。

停留到终端出现“Bundle 校验通过”。

## 1:25–2:25｜核心证据：一条命令跑通三个企业 Sample

终端：

```powershell
python skill-build/agent-vote/scripts/run_sample.py --output-dir .sample-output
```

口播随输出：

> 第一组是 SaaS 采购评审：采购和安全选供应商乙，运维保留对供应商甲 SLA 的支持证据。
>
> 第二组是客服机器人发布门禁：质量与业务支持发布，风控把 1.8% 越权回答作为反对证据保留下来。
>
> 第三组是线上故障响应：SRE 与研发主张回滚，容量 Agent 主张扩容。三组都得到 A 级证据、三个独立来源和新的 SHA-256 摘要。

画面要求：完整出现 3/3 与“全部可复现”。

## 2:25–3:25｜创新：Decision Pack 把票数变成可流转资产

画面：打开任一问题详情页的深色 Decision Pack 区域；再切 Swagger JSON。

口播：

> TouLeMa 的核心输出不是页面，而是 `decision-pack/v1`。它给出领先选项、共识率、分歧度、证据绑定覆盖、独立来源和 A 到 D 的完整度等级。当前票与证据经过规范 JSON 序列化后生成稳定 SHA-256：状态不变，摘要不变；任何改投或证据变化，摘要都会改变。这个 JSON 可以直接接入 OA 审批、CRM、事故复盘或审计系统。

必须补充：

> 这里的 confidence 是 Agent 自报强度，A 级表示证据完整，不宣称外部事实已经核验。

## 3:25–4:05｜企业级控制：可管、可控、可降级

画面：Swagger 的锁/接口，或说明书权限表。

口播：

> 普通写操作使用 Agent Bearer Key，合规重审和风险管理使用独立 Admin Key；多模型端点必须认证，避免匿名消耗模型额度。CORS 默认只允许本机前端，数据库路径外置，SQLite、WAL、密钥、缓存都不会进入 Skill ZIP。合规 pending 或 rejected 必须停止，429 也不会无限重试。

## 4:05–4:40｜商业价值与收尾

画面：路演 PPT 的三场景页或首页评审矩阵。

口播：

> 我们先从采购评审、发布门禁、故障响应三个高频流程切入，再通过私有部署接入企业知识库和 OA。商业价值不是多做一个投票页面，而是缩短人工汇总、保留少数意见、提高复盘可追溯率。
>
> 普通投票记录结论；TouLeMa 把多 Agent 的结论、分歧、证据与审计摘要一起沉淀成企业可复用的决策资产。

最后一帧：产品名、`3 Samples · A 级证据 · 可验证 Decision Pack`。

## 失败兜底

- 后端临时失败：切换到预录的 3 Sample 终端片段，不伪造现场成功。
- 前端加载失败：用 `.sample-output/*.decision-pack.json` 展示同一数据。
- 多模型 Key 不可用：本视频不触发真实模型；三个 Sample 本身无模型依赖。
- 时间超出：优先删减目录展示 10 秒，不删三个 Sample、Decision Pack 限制声明与安全边界。

## 录制验收

- 总时长目标 4:40，硬上限 4:55。
- 画面中不出现 API Key、Admin Key、`.env` 或个人路径。
- 三个 Sample、Bundle 校验、Decision Pack JSON 至少各完整出现一次。
- 不说“权威源已验证”“自动改投已上线”“链上存证已完成”。
