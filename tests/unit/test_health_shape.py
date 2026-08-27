import pytest

# 导入health业务处理函数
from app.main import health


# pytest标记：标记这是一个异步测试用例
@pytest.mark.asyncio
async def test_health_shape():
    # 调用健康检查异步函数，获取返回结果
    result = await health()
    # 校验返回码为200
    assert result["code"] == 200
    # 校验响应消息
    assert result["message"] == "success"
    # 校验data内部status状态为ok
    assert result["data"]["status"] == "ok"
