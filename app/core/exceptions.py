"""业务异常类型及统一 HTTP 异常响应处理。"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# FastAPI底层HTTP异常，继承自starlette
from starlette.exceptions import HTTPException as StarletteHTTPException

# 获取当前模块日志对象，用于打印异常堆栈
logger = logging.getLogger(__name__)


class AppError(Exception):
    """
    业务自定义异常类，业务逻辑主动抛出的异常
    """
    def __init__(self, status_code: int, message: str, data: dict | None = None):
        # HTTP状态码
        self.status_code = status_code
        # 异常提示信息
        self.message = message
        # 附加返回数据，默认为空字典
        self.data = data or {}


def bad_request(message: str, data: dict | None = None) -> AppError:
    """构造400 请求参数错误异常"""
    return AppError(400, message, data)


def unauthorized(message: str = "请先登录后再进行操作") -> AppError:
    """构造401 未登录/身份认证失败异常"""
    return AppError(401, message)


def forbidden(message: str = "当前账号没有权限执行该操作") -> AppError:
    """构造403 权限不足禁止访问异常"""
    return AppError(403, message)


def not_found(message: str = "资源不存在") -> AppError:
    """构造404 资源未找到异常"""
    return AppError(404, message)


def conflict(message: str = "数据已存在，请勿重复提交") -> AppError:
    """构造409 数据冲突，重复提交异常"""
    return AppError(409, message)


def register_exception_handlers(app: FastAPI) -> None:
    """
    注册全局异常处理器，统一格式化所有异常返回JSON响应
    :param app: FastAPI实例
    """

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        """捕获业务自定义AppError异常，返回统一JSON结构"""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": exc.message,
                "data": exc.data,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """捕获框架原生HTTP异常：404接口不存在、405方法不允许等"""
        # 404、405统一对外提示为接口不存在
        status_code = 404 if exc.status_code in {404, 405} else exc.status_code
        message = (
            "接口不存在，请检查请求路径和方法"
            if status_code == 404
            else str(exc.detail)
        )
        return JSONResponse(
            status_code=status_code,
            content={"code": status_code, "message": message, "data": {}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """捕获请求参数校验异常（query、body、path参数格式错误）"""
        # 解析校验错误，提取字段路径和错误提示
        errors = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content={
                "code": 400,
                "message": "参数校验失败",
                "data": {"errors": errors},
            },
        )

    @app.exception_handler(Exception)
    async def unknown_error_handler(request: Request, exc: Exception):
        """兜底捕获所有未处理的系统未知异常，返回500，打印完整异常堆栈日志"""
        logger.exception("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "服务器内部错误，请稍后再试",
                "data": {},
            },
        )
