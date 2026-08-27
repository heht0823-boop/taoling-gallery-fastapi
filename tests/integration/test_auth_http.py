async def test_login_wrong_password(client):
    """
    测试登录：账号或密码错误场景
    :param client: FastAPI测试异步客户端fixture
    """
    # 向登录接口发送POST请求，传入错误账号密码
    response = await client.post(
        "/api/auth/login",
        json={"account": "not-exists", "password": "wrong"},
    )
    # 断言HTTP状态码为401未授权
    assert response.status_code == 401
    # 断言自定义响应体里业务code等于401
    assert response.json()["code"] == 401

async def test_register_wrong_password(client):
    """
    测试注册：密码长度不足场景
    :param client: FastAPI测试异步客户端fixture
    """
    response = await client.post(
        "/api/auth/register",
        json={"account": "testUser", "password": "123"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 400
