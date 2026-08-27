"""认证接口的请求与响应 Schema。

Schema 只约束网络边界；密码哈希、账号状态和 Cookie 写入均由服务/路由层处理。
"""

from pydantic import BaseModel, ConfigDict


class RegisterIn(BaseModel):
    """用户注册 JSON 请求。"""

    model_config = ConfigDict(extra="ignore")
    username: str
    email: str | None = None
    password: str


class LoginIn(BaseModel):
    """使用用户名或邮箱登录的 JSON 请求。"""

    model_config = ConfigDict(extra="ignore")
    account: str
    password: str
