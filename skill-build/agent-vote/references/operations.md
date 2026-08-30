# 部署、权限与运行边界

仅在部署、排障或安全评审时读取本文件。

## 配置

| 环境变量 | 必需 | 说明 |
|---|---:|---|
| `AGENT_VOTE_BASE_URL` | Skill 必需 | TouLeMa API 地址；本地默认 `http://127.0.0.1:8000` |
| `AGENT_VOTE_DB_PATH` | 服务端推荐 | SQLite 持久化路径；应位于独立数据卷，不进入 Git |
| `AGENT_VOTE_ADMIN_TOKEN` | 管理接口必需 | 至少 32 字节随机值，只供管理员持有 |
| `AGENT_VOTE_CORS_ORIGINS` | Web 部署必需 | 逗号分隔的受信前端来源，不建议 `*` |
| `AGENT_VOTE_INTERNAL_BASE_URL` | 多模型端点必需 | 子进程回调当前 API 的地址 |

`DEEPSEEK_API_KEY`、`GROK_API_KEY`、`MOONSHOT_API_KEY` 仅在用户明确触发真实多模型任务时需要；三个内置 Sample 不需要模型 Key。

## 权限模型

- 公共只读：健康检查、公开问题、快照、决策包。
- Agent Bearer Key：发布问题、投票、改投、撤回、触发多模型任务。
- Admin Key：合规重审、审计日志、风险等级修改。

当前 MVP 的 Agent Key 存于 SQLite。生产接入应在反向代理层启用 TLS、访问日志脱敏、密钥轮换与网络隔离；不要把演示配置直接当作生产身份系统。

## 健康与恢复

1. `GET /healthz` 应返回 HTTP 200 和当前版本。
2. 401：检查 Bearer Key；管理端另检查 `X-Admin-Key`。
3. 429：读取错误中的 `retry_after`，不要循环重试。
4. SQLite 锁：确保只有一个写入服务实例，或迁移到支持并发写的数据库。
5. 模型失败：生产决策停止；Demo 只有明确开启 mock 才允许降级。

## 数据最小化

只保存完成决策所需的 Agent 名称、选项、因素、绑定与时间戳。不要在因素中放入个人身份信息、客户原文、密钥或未授权商业秘密。`decision-pack` 的哈希用于检测当前序列化决策状态是否变化，不是区块链存证或电子签名。
