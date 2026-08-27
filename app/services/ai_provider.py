"""DashScope OpenAI 兼容接口适配器。

第三方调用只集中在本模块：业务层可以捕获 ``AppError`` 后给出本地可用回复，
测试也能替换公开函数而不触网。普通回复使用 JSON 模式，流式回复逐段解析
DashScope 的 ``data:`` 行并产出纯文本增量。
"""

import json
import re
from collections.abc import AsyncIterator

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

FALLBACK_REPLY = (
    "我先按你的描述在图库里找找相关灵感。如果你有更明确的风格、主题、"
    "颜色或用途，也可以继续补充。"
)

# DashScope 的 OpenAI 兼容接口使用标准 function calling 定义。工具只暴露
# 图库读操作和幂等收藏操作，不允许模型直接拼 SQL 或访问任意内部服务。
AI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_images",
            "description": "按关键词、分类或标签搜索图库中的公开图片。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "category": {"type": "string"},
                    "sort": {
                        "type": "string",
                        "enum": ["weight", "latest", "hot", "favorites", "downloads"],
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hot_images",
            "description": "获取按真实浏览量排序的热门图片。",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 12}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_images",
            "description": "获取最近发布的公开图片。",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 12}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_favorites",
            "description": "用户确认后，把本轮推荐图片加入当前账号收藏。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_ids": {"type": "array", "items": {"type": "integer"}},
                },
            },
        },
    },
]


def _safe_json(value: str) -> dict | None:
    """解析纯 JSON 或从模型附带说明的文本中提取第一个 JSON 对象。"""

    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        matched = re.search(r"\{[\s\S]*\}", str(value or ""))
        if not matched:
            return None
        try:
            parsed = json.loads(matched.group(0))
            return parsed if isinstance(parsed, dict) else None
        except ValueError:
            return None


def normalize_strings(value: object, limit: int = 8) -> list[str]:
    """把模型返回值标准化为有序、去重、非空的短字符串数组。"""

    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _system_prompt(*, available_tags: list[str], memory: str, json_mode: bool) -> str:
    """根据图库标签、用户记忆和输出模式生成系统提示词。"""

    tags = "、".join(available_tags) if available_tags else "暂无标签"
    rules = [
        "你是“桃灵助手”，服务于图片图库网站“桃灵图库”。",
        "只能推荐图库中真实存在的内容，不能生成、绘制或修改图片。",
        "回复使用自然、简洁、可执行的中文。",
        f"当前图库可用标签：{tags}",
    ]
    if memory:
        rules.append(f"用户记忆参考：\n{memory}")
    if json_mode:
        rules.extend(
            [
                "只返回 JSON，不要返回 Markdown。",
                "字段必须包含 reply、recommended_tags、search_keywords、title。",
                "title 不超过 18 个中文，标签优先使用图库已有标签。",
            ]
        )
    return "\n".join(rules)


async def _request_json(
    messages: list[dict],
    *,
    temperature: float = 0.6,
    response_format: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """调用非流式 completions 接口并转换供应商错误。"""

    if not settings.dashscope_api_key:
        raise AppError(503, "AI 服务未配置 API Key，请检查 DASHSCOPE_API_KEY 环境变量")
    url = f"{settings.dashscope_base_url.rstrip('/')}/chat/completions"
    timeout = max(settings.ai_timeout_ms / 1000, 1)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.dashscope_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.dashscope_model,
                    "messages": messages,
                    "temperature": temperature,
                    **({"response_format": response_format} if response_format else {}),
                    **(extra or {}),
                },
            )
    except httpx.TimeoutException as exc:
        raise AppError(504, "AI 服务响应超时，请稍后重试") from exc
    except httpx.HTTPError as exc:
        raise AppError(502, f"AI 服务调用失败：{exc}") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise AppError(502, "AI 服务返回了无效 JSON") from exc
    if not isinstance(body, dict):
        raise AppError(502, "AI 服务返回了无效响应结构")
    if not response.is_success:
        message = (
            (body.get("error") or {}).get("message")
            or body.get("message")
            or "AI 服务调用失败"
        )
        raise AppError(502 if response.status_code >= 500 else 400, f"AI 服务返回错误：{message}")
    return body


async def structured_reply(
    *,
    messages: list[dict],
    available_tags: list[str],
    memory: str,
) -> dict:
    """请求结构化回复，并固定输出业务层需要的四个字段。"""

    body = await _request_json(
        [
            {
                "role": "system",
                "content": _system_prompt(
                    available_tags=available_tags,
                    memory=memory,
                    json_mode=True,
                ),
            },
            *messages,
        ],
        response_format={"type": "json_object"},
    )
    content = (
        ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
        or ""
    )
    parsed = _safe_json(content)
    if not parsed:
        return {
            "reply": str(content).strip() or FALLBACK_REPLY,
            "recommended_tags": [],
            "search_keywords": [],
            "title": "",
        }
    return {
        "reply": str(parsed.get("reply") or "").strip() or FALLBACK_REPLY,
        "recommended_tags": normalize_strings(parsed.get("recommended_tags")),
        "search_keywords": normalize_strings(parsed.get("search_keywords")),
        "title": str(parsed.get("title") or "").strip()[:30],
    }


async def stream_reply(
    *,
    messages: list[dict],
    available_tags: list[str],
    memory: str,
) -> AsyncIterator[str]:
    """调用流式 completions 接口，并逐个产出非空文本 delta。"""

    if not settings.dashscope_api_key:
        raise AppError(503, "AI 服务未配置 API Key，请检查 DASHSCOPE_API_KEY 环境变量")
    url = f"{settings.dashscope_base_url.rstrip('/')}/chat/completions"
    timeout = max(settings.ai_timeout_ms / 1000, 1)
    payload = {
        "model": settings.dashscope_model,
        "messages": [
            {
                "role": "system",
                "content": _system_prompt(
                    available_tags=available_tags,
                    memory=memory,
                    json_mode=False,
                ),
            },
            *messages,
        ],
        "temperature": 0.7,
        "stream": True,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {settings.dashscope_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                if not response.is_success:
                    raw = await response.aread()
                    raise AppError(
                        502 if response.status_code >= 500 else 400,
                        f"AI 服务返回错误：{raw.decode('utf-8', errors='replace')}",
                    )
                async for line in response.aiter_lines():
                    value = line.strip()
                    if not value.startswith("data:"):
                        continue
                    data = value[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        event = json.loads(data)
                    except ValueError:
                        continue
                    delta = ((event.get("choices") or [{}])[0].get("delta") or {}).get(
                        "content"
                    )
                    if delta:
                        yield str(delta)
    except httpx.TimeoutException as exc:
        raise AppError(504, "AI 服务响应超时，请稍后重试") from exc
    except httpx.HTTPError as exc:
        raise AppError(502, f"AI 服务调用失败：{exc}") from exc


async def plan_tools(
    *,
    messages: list[dict],
    available_tags: list[str],
    memory: str,
) -> list[dict]:
    """让模型选择受控图库工具，并把 function arguments 安全解析为字典。"""

    body = await _request_json(
        [
            {
                "role": "system",
                "content": _system_prompt(
                    available_tags=available_tags,
                    memory=memory,
                    json_mode=False,
                ),
            },
            {
                "role": "system",
                "content": (
                    "仅在用户明确需要搜索图片、查看热门/最新图片或确认收藏时调用工具；"
                    "普通闲聊不要调用工具。"
                ),
            },
            *messages,
        ],
        temperature=0.2,
        extra={"tools": AI_TOOLS, "tool_choice": "auto"},
    )
    tool_calls = ((body.get("choices") or [{}])[0].get("message") or {}).get(
        "tool_calls"
    ) or []
    allowed_names = {item["function"]["name"] for item in AI_TOOLS}
    result: list[dict] = []
    for call in tool_calls:
        function = call.get("function") or {}
        name = function.get("name")
        if name not in allowed_names:
            continue
        raw_arguments = function.get("arguments") or "{}"
        arguments = raw_arguments if isinstance(raw_arguments, dict) else _safe_json(raw_arguments)
        result.append(
            {
                "id": call.get("id"),
                "name": name,
                "arguments": arguments or {},
            }
        )
    return result


async def generate_title(*, user_message: str, assistant_reply: str) -> str:
    """根据首轮问答生成短标题；供应商不可用时返回空串交给业务层兜底。"""

    try:
        body = await _request_json(
            [
                {
                    "role": "system",
                    "content": (
                        '只返回 JSON：{"title":"18个中文以内的会话标题"}。'
                        "标题基于用户首条输入和助手首条回复总结。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"用户第一条输入：{user_message}\n助手回复：{assistant_reply}",
                },
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except AppError:
        return ""
    content = (
        ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
        or ""
    )
    parsed = _safe_json(content) or {}
    return str(parsed.get("title") or "").strip()[:30]


async def summarize_memories(
    *,
    existing_short: str,
    existing_long: str,
    messages: list[dict],
) -> dict:
    """压缩近期上下文和长期偏好，并在云服务不可用时生成本地短期摘要。"""

    system_prompt = "\n".join(
        [
            "你是桃灵助手的记忆整理器，只返回 JSON。",
            "字段必须包含 short_memory、long_memory。",
            "short_memory 用 120 字以内总结当前上下文；long_memory 用 160 字以内总结稳定偏好。",
            "没有明显长期偏好时，long_memory 返回空字符串。",
        ]
    )
    try:
        body = await _request_json(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "\n".join(
                        [
                            f"已有短期记忆：{existing_short or '无'}",
                            f"已有长期记忆：{existing_long or '无'}",
                            "最近消息：",
                            *[
                                f"{item.get('role', 'unknown')}: {item.get('content', '')}"
                                for item in messages
                            ],
                        ]
                    ),
                },
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = (
            ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
            or ""
        )
        parsed = _safe_json(content) or {}
        return {
            "short_memory": str(parsed.get("short_memory") or "").strip()[:500],
            "long_memory": str(parsed.get("long_memory") or "").strip()[:800],
        }
    except AppError:
        fallback = "\n".join(
            f"{'用户' if item.get('role') == 'user' else '助手'}：{item.get('content', '')}"
            for item in messages[-4:]
        )
        return {
            "short_memory": fallback[:500],
            "long_memory": existing_long,
        }
