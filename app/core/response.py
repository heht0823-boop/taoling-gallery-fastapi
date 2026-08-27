"""与原 Node 服务一致的统一响应封装。"""

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def api_response(
        data: Any = None,
        message: str = 'success',
        status_code: int = 200,
        headers: dict[str, str] | None = None,
) -> JSONResponse:
    """
    统一接口返回封装函数，构造标准JSON格式响应
    :param data: 业务返回数据，任意类型，不传默认为空字典
    :param message: 响应提示信息，默认 success
    :param status_code: HTTP状态码，默认200
    :param headers: 可选响应头字典
    :return: FastAPI JSONResponse 对象，可直接作为路由返回值
    """
    # 组装统一返回体；data为None时返回空字典{}，避免返回null
    payload = {
        'code': status_code,
        'message': message,
        'data': {} if data is None else data
    }
    # jsonable_encoder：把ORM模型、datetime等不可直接序列化对象转为json可兼容类型
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload),
        headers=headers
    )


def created(data: Any = None, message: str = '创建成功') -> JSONResponse:
    """
    创建资源快捷响应，HTTP 201
    :param data: 创建成功后返回的业务数据
    :param message: 提示文案，默认“创建成功”
    :return: JSONResponse
    """
    return api_response(data=data, message=message, status_code=201)
