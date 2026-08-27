from app.models.message import UserMessage
from app.services.message_service import create_message, list_board, list_mine


async def test_public_and_personal_messages_hide_unapproved_content(
    behavior_records,
):
    db, user, *_ = behavior_records
    root = UserMessage(
        user_id=user.id,
        content="公开顶级留言",
        check_status="success",
        check_score=0,
    )
    blocked = UserMessage(
        user_id=user.id,
        content="已屏蔽留言",
        check_status="block",
        check_score=99,
    )
    pending = UserMessage(
        user_id=user.id,
        content="待审核留言",
        check_status="pending",
        check_score=0,
    )
    db.add_all([root, blocked, pending])
    await db.flush()
    reply = UserMessage(
        user_id=user.id,
        parent_id=root.id,
        content="公开回复",
        check_status="success",
        check_score=0,
    )
    blocked_reply = UserMessage(
        user_id=user.id,
        parent_id=root.id,
        content="屏蔽回复",
        check_status="block",
        check_score=99,
    )
    db.add_all([reply, blocked_reply])
    await db.commit()

    board = await list_board(db, page=1, page_size=100)
    mine = await list_mine(db, user_id=user.id, page=1, page_size=8)

    board_by_id = {item["id"]: item for item in board["list"]}
    assert root.id in board_by_id
    assert blocked.id not in board_by_id
    assert pending.id not in board_by_id
    assert [
        item["content"] for item in board_by_id[root.id]["replies"]
    ] == ["公开回复"]
    assert {item["content"] for item in mine["list"]} == {
        "公开顶级留言",
        "公开回复",
    }
    assert "check_status" not in board_by_id[root.id]


async def test_create_message_and_http_contract(
    authenticated_client,
    behavior_records,
):
    db, user, *_ = behavior_records
    board_before = await list_board(db, page=1, page_size=24)
    result = await create_message(
        db,
        user=user,
        content="  服务层审核留言  ",
        parent_id=None,
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
    )
    response = await authenticated_client.post(
        "/api/user/messages",
        json={"content": "HTTP 审核留言"},
    )
    mine = await authenticated_client.get(
        "/api/user/messages",
        params={"page": 1, "pageSize": 8},
    )
    board = await authenticated_client.get(
        "/api/messages",
        params={"page": 1, "pageSize": 24},
    )

    assert result == {"submitted": True}
    assert response.status_code == 201
    assert response.json()["data"] == {"submitted": True}
    assert mine.json()["data"]["pagination"]["total"] == 2
    assert board.status_code == 200
    assert board.json()["data"]["pagination"]["total"] == (
        board_before["pagination"]["total"] + 2
    )
