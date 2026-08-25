async def test_health_http(client):
    """
    通过HTTP接口测试健康检查端点 /health
    依赖前面定义的client fixture，使用内存ASGI客户端发起GET请求
    """
    # 向/health接口发送GET异步请求
    response = await client.get("/health")
    # 断言HTTP状态码为200，接口访问成功
    assert response.status_code == 200
    # 解析json响应，校验data中status字段为ok
    assert response.json()["data"]["status"] == "ok"
