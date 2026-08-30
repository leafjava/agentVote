#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_client.py —— Agent Vote 多模型 LLM 客户端（OpenAI 兼容统一层）

V1.3 新增：
  - 支持 DeepSeek / Grok / Moonshot 三家 provider
  - 全部走 OpenAI Chat Completions 协议 → 一个 LLMClient 类覆盖
  - 通过环境变量管理 API key，绝不入代码

Provider 速查：
  ┌─────────────┬──────────────────────────┬──────────────────┬────────────────────────┐
  │ provider    │ base_url                 │ default_model    │ env key                │
  ├─────────────┼──────────────────────────┼──────────────────┼────────────────────────┤
  │ deepseek    │ https://api.deepseek.com │ deepseek-chat    │ DEEPSEEK_API_KEY       │
  │ grok        │ https://api.x.ai/v1      │ grok-3-mini      │ GROK_API_KEY           │
  │ moonshot    │ https://api.moonshot.cn  │ moonshot-v1-8k   │ MOONSHOT_API_KEY       │
  └─────────────┴──────────────────────────┴──────────────────┴────────────────────────┘

设计原则：
  1. 失败显式：缺 key 直接报错，绝不静默 fallback（让 .env 缺失可见）
  2. 超时 60s：投票 LLM 调用的硬上限
  3. JSON mode：尽量走 response_format（部分 provider 不支持时退回 prompt 强制 JSON）
  4. 仅依赖 requests：与 agent_runner.py 保持一致
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests


@dataclass(frozen=True)
class ProviderSpec:
    """provider 的元信息：base_url + 默认 model + env key 名。"""
    name: str
    base_url: str
    default_model: str
    env_key: str
    label_zh: str  # 中文显示名


# ----------------------------------------------------------- provider 注册表
PROVIDERS: Dict[str, ProviderSpec] = {
    "deepseek": ProviderSpec(
        name="deepseek",
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        default_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        env_key="DEEPSEEK_API_KEY",
        label_zh="DeepSeek",
    ),
    "grok": ProviderSpec(
        name="grok",
        base_url=os.environ.get("GROK_BASE_URL", "https://api.x.ai/v1"),
        default_model=os.environ.get("GROK_MODEL", "grok-3-mini"),
        env_key="GROK_API_KEY",
        label_zh="Grok",
    ),
    "moonshot": ProviderSpec(
        name="moonshot",
        base_url=os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
        default_model=os.environ.get("MOONSHOT_MODEL", "moonshot-v1-8k"),
        env_key="MOONSHOT_API_KEY",
        label_zh="Moonshot",
    ),
}


class ProviderNotFoundError(ValueError):
    """调用的 provider 不在注册表里。"""


class MissingAPIKeyError(RuntimeError):
    """provider 需要 API key 但环境变量缺失。"""


# ----------------------------------------------------------- 客户端
class LLMClient:
    """统一的 OpenAI 兼容 LLM 客户端。

    用法：
        client = LLMClient.from_provider("deepseek")
        text = client.chat([{"role": "user", "content": "hi"}])
    """

    def __init__(self, spec: ProviderSpec, api_key: str,
                 model: Optional[str] = None, timeout: int = 60):
        self.spec = spec
        self.api_key = api_key
        self.model = model or spec.default_model
        self.timeout = timeout
        # 部分 provider 不支持 response_format=json_object（如 moonshot / grok 早期），
        # 这里做个软探测；如果 400 就退回 prompt 强制 JSON。
        self._supports_json_mode: Optional[bool] = None

    @classmethod
    def from_provider(cls, provider: str,
                      model: Optional[str] = None) -> "LLMClient":
        spec = PROVIDERS.get(provider.lower())
        if spec is None:
            raise ProviderNotFoundError(
                f"未知 provider：{provider!r}。"
                f"可选：{', '.join(PROVIDERS.keys())}"
            )
        api_key = os.environ.get(spec.env_key)
        if not api_key:
            raise MissingAPIKeyError(
                f"{spec.label_zh} 未配置 API key。"
                f"请在 .env 设置 {spec.env_key}=<your key>，"
                f"或使用 --mock 模式。"
            )
        return cls(spec=spec, api_key=api_key, model=model)

    @property
    def provider_name(self) -> str:
        return self.spec.name

    @property
    def label(self) -> str:
        return self.spec.label_zh

    # ---------- 核心方法
    def chat(self, messages: List[Dict],
             temperature: float = 0.7,
             max_tokens: int = 400,
             json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        # 第一轮 json_mode 试探
        if json_mode and self._supports_json_mode is not False:
            payload["response_format"] = {"type": "json_object"}

        resp = requests.post(
            f"{self.spec.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        # 探测：若 provider 不支持 json_mode，自动降级
        if resp.status_code == 400 and json_mode and "response_format" in payload:
            self._supports_json_mode = False
            payload.pop("response_format")
            resp = requests.post(
                f"{self.spec.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
        else:
            self._supports_json_mode = True

        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def __repr__(self) -> str:
        return (f"LLMClient(provider={self.spec.name}, "
                f"model={self.model}, "
                f"base_url={self.spec.base_url})")


# ----------------------------------------------------------- 便捷函数
def get_client(provider: str, model: Optional[str] = None) -> Optional[LLMClient]:
    """从 provider 名拿客户端，缺失 key 时返回 None（用于优雅 mock 降级）。"""
    try:
        return LLMClient.from_provider(provider, model=model)
    except MissingAPIKeyError as e:
        print(f"  ⚠️  {e}")
        return None
    except ProviderNotFoundError as e:
        print(f"  ⚠️  {e}")
        return None


def list_providers() -> List[str]:
    """返回已注册 provider 列表，便于 CLI 帮助输出。"""
    return list(PROVIDERS.keys())