"""真实应用入口的路由与跨域契约测试。"""

from app.main import app

# 来自 taoling-project/main 的 Express 路由；AI 模块在独立功能提交中加入。
NODE_ROUTE_SUBSET = {
    ("post", "/api/auth/register"),
    ("post", "/api/auth/login"),
    ("post", "/api/auth/logout"),
    ("get", "/api/auth/me"),
    ("get", "/api/images"),
    ("get", "/api/images/{image_id}/thumbnail"),
    ("get", "/api/images/{image_id}"),
    ("post", "/api/images/{image_id}/view"),
    ("get", "/api/images/{image_id}/related"),
    ("post", "/api/images/{image_id}/favorite"),
    ("delete", "/api/images/{image_id}/favorite"),
    ("post", "/api/images/{image_id}/download"),
    ("get", "/api/categories"),
    ("get", "/api/tags"),
    ("get", "/api/messages"),
    ("get", "/api/user/profile"),
    ("get", "/api/user/profile/summary"),
    ("put", "/api/user/profile"),
    ("patch", "/api/user/profile"),
    ("post", "/api/user/profile/avatar"),
    ("patch", "/api/user/profile/avatar"),
    ("patch", "/api/user/password"),
    ("post", "/api/user/favorites"),
    ("delete", "/api/user/favorites/{image_id}"),
    ("get", "/api/user/favorites"),
    ("post", "/api/user/downloads"),
    ("get", "/api/user/downloads"),
    ("delete", "/api/user/downloads/{record_id}"),
    ("delete", "/api/user/downloads"),
    ("get", "/api/user/messages"),
    ("post", "/api/user/messages"),
    ("get", "/api/weather/live"),
    ("get", "/api/weather/live/batch"),
    ("get", "/api/weather/forecast"),
    ("get", "/api/weather/24h"),
    ("get", "/api/weather/warnings"),
    ("get", "/api/weather/tips"),
    ("get", "/api/admin/dashboard/stats"),
    ("get", "/api/admin/logs"),
    ("post", "/api/admin/files/images"),
    ("post", "/api/admin/images"),
    ("get", "/api/admin/images"),
    ("get", "/api/admin/images/{image_id}"),
    ("put", "/api/admin/images/{image_id}"),
    ("patch", "/api/admin/images/{image_id}"),
    ("patch", "/api/admin/images/{image_id}/status"),
    ("delete", "/api/admin/images/{image_id}"),
    ("patch", "/api/admin/images/{image_id}/restore"),
    ("get", "/api/admin/categories"),
    ("post", "/api/admin/categories"),
    ("put", "/api/admin/categories/{category_id}"),
    ("patch", "/api/admin/categories/{category_id}"),
    ("delete", "/api/admin/categories/{category_id}"),
    ("get", "/api/admin/tags"),
    ("post", "/api/admin/tags"),
    ("put", "/api/admin/tags/{tag_id}"),
    ("patch", "/api/admin/tags/{tag_id}"),
    ("delete", "/api/admin/tags/{tag_id}"),
    ("get", "/api/admin/users"),
    ("get", "/api/admin/users/{user_id}"),
    ("patch", "/api/admin/users/{user_id}/status"),
    ("delete", "/api/admin/users/{user_id}"),
    ("get", "/api/admin/messages"),
    ("get", "/api/admin/messages/{message_id}"),
    ("post", "/api/admin/messages/{message_id}/replies"),
    ("delete", "/api/admin/messages/{message_id}"),
}


def test_openapi_contains_all_completed_node_routes():
    """真实应用 OpenAPI 必须包含已完成的全部 Node 对照路由。"""

    schema = app.openapi()
    actual = {
        (method, path)
        for path, operations in schema["paths"].items()
        for method in operations
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert NODE_ROUTE_SUBSET <= actual


def test_application_has_no_duplicate_method_path_pairs():
    """集中注册清单不能重复挂载同一请求方法和路径。"""

    route_keys = [
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    ]
    assert len(route_keys) == len(set(route_keys))


async def test_vue_dev_origin_can_call_port_8000(client):
    """Vue 5173 开发源可携带 Cookie 跨域访问 Python 服务。"""

    response = await client.options(
        "/api/images",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"
