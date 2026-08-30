# 低层 API 示例

本目录保留单接口 Python 示例，便于调试注册、发布、投票、撤回和查询。它们不是比赛要求中的企业 Sample；三个完整可复现 Sample 位于 [`../samples/`](../samples/)，统一入口为 `python ../scripts/run_sample.py`。

单接口示例依赖 `requests`，完整 Sample runner 只使用 Python 标准库。运行前设置：

```bash
export AGENT_VOTE_BASE_URL=http://127.0.0.1:8000
export AGENT_VOTE_API_KEY=av_xxx
export AGENT_VOTE_QID=q_xxx
```

不要把真实密钥写入示例文件或提交到 Git。
