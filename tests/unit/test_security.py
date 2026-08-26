from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_and_verify():
    """
    测试bcrypt密码哈希与校验流程
    1. 明文密码哈希之后不等于原明文
    2. 正确明文可以校验通过
    3. 错误明文校验返回False
    """
    raw = "123456abc"
    # 对明文密码做bcrypt哈希
    value = hash_password(raw)
    # 哈希结果绝对不能等于原始明文
    assert value != raw
    # 正确密码校验应当返回True
    assert verify_password(raw, value) is True
    # 错误密码校验应当返回False
    assert verify_password("wrong", value) is False


def test_jwt_round_trip():
    """
    JWT 往返测试：生成token → 解析token
    校验生成之后解析出来的payload数据和入参一致
    注意：不会测试过期逻辑，单元测试不修改系统时间
    """
    # 生成用户id=1，角色user的jwt令牌
    token = create_access_token(1, "user")
    # 解码token拿到载荷
    payload = decode_access_token(token)
    # 校验payload中用户id正确
    assert payload["id"] == 1
    # 校验payload中角色正确
    assert payload["role"] == "user"
