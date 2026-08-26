import pytest
# 导入httpx异步测试相关组件
from httpx import ASGITransport, AsyncClient
# 导入FastAPI应用实例
from app.main import app


@pytest.fixture
async def client():
    """
    pytest异步固件，生成用于接口测试的异步http客户端
    不走真实网络端口，内存直接调用ASGI应用，测试速度快
    """
    # ASGITransport：ASGI传输层，把fastapi app挂载进去，内存内调用接口
    transport = ASGITransport(app=app)
    # 创建异步http测试客户端，绑定上面的ASGI传输
    async with AsyncClient(
            transport=transport,
            base_url="http://testserver",  # 虚拟测试域名，请求时只需要写路径如 /health
    ) as ac:
        # yield产出客户端对象，测试用例使用；用例结束后自动退出async with，释放资源
        yield ac
