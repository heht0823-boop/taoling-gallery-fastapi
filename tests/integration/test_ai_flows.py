"""桃灵助手会话、SSE、归属和软删除集成测试。"""

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import AppError
from app.models.ai import AiConversation, AiMemory, AiMessage
from app.models.user import User


@pytest.fixture(autouse=True)
def local_ai_provider(monkeypatch):
    """隔离 DashScope 网络调用，同时保留业务编排和图库数据库查询。"""

    async def no_planned_tools(**_kwargs):
        """让服务使用可预测的本地意图规则规划工具。"""

        return []

    async def fixed_title(**_kwargs):
        """为首轮对话提供稳定标题，便于验证会话更新。"""

        return "最新图库推荐"

    async def fixed_metadata(**_kwargs):
        """提供流式回复完成后的结构化标签和搜索词。"""

        return {
            "reply": "本地测试回复",
            "recommended_tags": [],
            "search_keywords": ["最新"],
            "title": "最新图库推荐",
        }

    async def fixed_memory(**_kwargs):
        """返回可持久化的短期记忆，验证增强能力不会依赖外网。"""

        return {"short_memory": "用户希望查看最新图片", "long_memory": ""}

    monkeypatch.setattr("app.services.ai_provider.plan_tools", no_planned_tools)
    monkeypatch.setattr("app.services.ai_provider.generate_title", fixed_title)
    monkeypatch.setattr("app.services.ai_provider.structured_reply", fixed_metadata)
    monkeypatch.setattr("app.services.ai_provider.summarize_memories", fixed_memory)


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """把 HTTP 测试响应中的 SSE 文本解析为事件名称和 JSON 数据。"""

    events: list[tuple[str, dict]] = []
    for block in text.strip().split("\n\n"):
        event = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            events.append((event, json.loads("\n".join(data_lines))))
    return events


async def test_non_stream_chat_persists_messages_stats_images_and_memory(
    authenticated_client,
    behavior_records,
):
    """非流式聊天应完整保存两条消息、统计、推荐图片和短期记忆。"""

    db, user, stats, public_image, *_ = behavior_records
    before_conversations = stats.ai_conversation_count
    before_messages = stats.ai_message_count

    response = await authenticated_client.post(
        "/api/ai/chat",
        params={"stream": "false"},
        json={"message": "给我看看最新图片"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "AI 回复成功"
    result = body["data"]
    assert result["conversation_id"] > 0
    assert result["title"] == "最新图库推荐"
    assert result["reply"].startswith("我按发布时间")
    assert public_image.id in {item["id"] for item in result["recommended_images"]}
    assert result["recommended_images"][0]["detail_url"].startswith("/images/")

    await db.refresh(stats)
    assert stats.ai_conversation_count == before_conversations + 1
    assert stats.ai_message_count == before_messages + 2
    messages = await authenticated_client.get(
        f"/api/user/ai/conversations/{result['conversation_id']}/messages"
    )
    assert messages.status_code == 200
    assert [item["role"] for item in messages.json()["data"]] == ["user", "assistant"]
    assert messages.json()["data"][1]["recommended_images"]

    memory = await db.scalar(
        select(AiMemory).where(
            AiMemory.user_id == user.id,
            AiMemory.conversation_id == result["conversation_id"],
            AiMemory.memory_type == "short",
        )
    )
    assert memory and memory.content == "用户希望查看最新图片"


async def test_default_chat_stream_matches_frontend_event_contract(
    authenticated_client,
):
    """默认聊天必须按前端解析器要求输出完整且有序的 SSE 事件。"""

    response = await authenticated_client.post(
        "/api/ai/chat",
        json={"message": "给我看看热门图片"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "start"
    assert "tools" in names
    assert "delta" in names
    assert names[-1] == "done"
    assert "error" not in names
    done = events[-1][1]
    assert done["title"] == "最新图库推荐"
    assert done["reply"].startswith("我按图库真实浏览热度")
    assert done["recommended_images"]


async def test_ai_provider_failure_and_generation_request_use_safe_local_replies(
    authenticated_client,
    monkeypatch,
):
    """云模型故障应本地降级，生图请求必须明确说明当前能力边界。"""

    async def unavailable(**_kwargs):
        """模拟 DashScope 未配置或暂时不可用。"""

        raise AppError(503, "AI 服务未配置")

    monkeypatch.setattr("app.services.ai_provider.plan_tools", unavailable)
    monkeypatch.setattr("app.services.ai_provider.structured_reply", unavailable)
    fallback = await authenticated_client.post(
        "/api/ai/chat",
        params={"stream": "false"},
        json={"message": "你好，今天心情怎么样"},
    )
    generation = await authenticated_client.post(
        "/api/ai/chat",
        params={"stream": "false"},
        json={"message": "帮我生成一张梦幻风景图片"},
    )

    assert fallback.status_code == 201
    assert fallback.json()["data"]["reply"].startswith("我先按你的描述")
    assert generation.status_code == 201
    assert "不提供图片生成" in generation.json()["data"]["reply"]


async def test_ai_aliases_ownership_validation_and_soft_delete(
    authenticated_client,
    behavior_records,
):
    """双前缀保持等价，并阻止读取他人会话或空白消息。"""

    db, user, *_ = behavior_records
    created = await authenticated_client.post(
        "/api/user/ai/conversations",
        json={"title": "兼容路径会话"},
    )
    conversation_id = created.json()["data"]["id"]
    listed = await authenticated_client.get("/api/ai/conversations")
    assert created.status_code == 201
    assert any(item["id"] == conversation_id for item in listed.json()["data"])

    suffix = uuid4().hex[:10]
    other_user = User(
        username=f"ai-other-{suffix}",
        email=f"ai-other-{suffix}@example.test",
        password_hash="test-only",
        role="user",
        status="normal",
    )
    db.add(other_user)
    await db.flush()
    foreign_conversation = AiConversation(user_id=other_user.id, title="他人会话")
    db.add(foreign_conversation)
    await db.flush()

    forbidden_history = await authenticated_client.get(
        f"/api/ai/conversations/{foreign_conversation.id}/messages"
    )
    blank_message = await authenticated_client.post(
        "/api/ai/chat",
        params={"stream": "false"},
        json={"conversation_id": conversation_id, "message": "   "},
    )
    removed = await authenticated_client.delete(
        f"/api/user/ai/conversations/{conversation_id}"
    )
    removed_again = await authenticated_client.get(
        f"/api/ai/conversations/{conversation_id}/messages"
    )

    assert forbidden_history.status_code == 404
    assert blank_message.status_code == 400
    assert blank_message.json()["message"] == "消息内容不能为空"
    assert removed.status_code == 200
    assert removed.json()["data"] == {}
    assert removed_again.status_code == 404


async def test_clear_conversations_soft_deletes_all_messages(
    authenticated_client,
    behavior_records,
):
    """清空接口应同时软删除当前用户全部会话及其消息。"""

    db, user, *_ = behavior_records
    chat_result = await authenticated_client.post(
        "/api/ai/chat",
        params={"stream": "false"},
        json={"message": "给我看看最新图片"},
    )
    conversation_id = chat_result.json()["data"]["conversation_id"]
    await authenticated_client.post(
        "/api/ai/conversations",
        json={"title": "待清空空会话"},
    )

    cleared = await authenticated_client.delete("/api/user/ai/conversations")
    listed = await authenticated_client.get("/api/ai/conversations")
    conversation = await db.get(AiConversation, conversation_id)
    messages = list(
        (
            await db.scalars(
                select(AiMessage).where(
                    AiMessage.user_id == user.id,
                    AiMessage.conversation_id == conversation_id,
                )
            )
        ).all()
    )

    assert cleared.status_code == 200
    assert cleared.json()["message"] == "AI 会话已清空"
    assert listed.json()["data"] == []
    assert conversation and conversation.deleted_at is not None
    assert messages and all(item.deleted_at is not None for item in messages)
