# 桃灵图库 FastAPI 后端

这是桃灵图库的独立 Python 后端。它与原 Node.js + Express 服务保持相同的
`/api` 请求路径、Cookie/JWT 鉴权、统一响应结构和前端字段，可直接服务原 Vue
前端；聊天接口同时兼容 `/api/ai/*` 与 `/api/user/ai/*`。

## 技术栈

- Python 3.12+
- FastAPI + Uvicorn
- SQLAlchemy 2.0 Async + MySQL + asyncmy
- Pydantic Settings
- pytest + pytest-asyncio + HTTPX
- Ruff

## 本地启动

1. 准备原桃灵图库 MySQL 数据库与表结构。
2. 复制 `.env.example` 为 `.env`，至少配置数据库、JWT 和管理员密码。
3. 创建虚拟环境并安装锁定依赖。
4. 验证数据库后启动服务。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe scripts\db_smoke.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动阶段会先执行数据库连通检查，再检查管理员账号。数据库没有管理员时必须在
`.env` 设置非空 `ADMIN_PASSWORD`；已有管理员但缺少 `user_stats` 时会自动补齐。

服务入口：

- 健康检查：`http://127.0.0.1:8000/health`
- OpenAPI：`http://127.0.0.1:8000/openapi.json`
- Swagger UI：`http://127.0.0.1:8000/docs`

## 前端对接

开发环境可把 Vue 的变量设为绝对地址：

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api
VITE_UPLOAD_BASE_URL=http://localhost:8000/uploads
```

后端默认允许 `http://localhost:5173` 和 `http://127.0.0.1:5173` 携带认证
Cookie 跨域访问。本地联调时前后端应统一使用 `localhost`，或统一使用
`127.0.0.1`，避免浏览器因站点主机名不同而阻止 `SameSite=lax` Cookie。生产
环境使用同域反向代理时，前端可继续使用 `/api` 和 `/uploads` 相对路径，并在
后端 `CORS_ORIGINS` 中填写实际前端来源。

## 接口范围

当前 OpenAPI 精确覆盖原 Express 的 78 个业务方法/路径：

| 模块 | 能力 |
| --- | --- |
| 认证 | 注册、登录、退出、当前用户 |
| 公开图库 | 图片列表/详情/缩略图/相关推荐、分类、标签、留言、浏览 |
| 用户中心 | 资料、头像、密码、收藏、下载记录、留言 |
| 桃灵助手 | SSE/非流式聊天、会话创建/列表/消息、删除/清空、双前缀兼容 |
| 天气 | 实况、批量实况、预报、24 小时、预警、生活指数 |
| 管理后台 | 仪表盘、日志、图片/文件、分类、标签、用户、留言回复 |

普通 JSON 响应统一为：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m pytest -q
```

契约测试会把真实 OpenAPI 与 Express 路由清单做精确比较；集成测试使用数据库
回滚事务验证鉴权、计数、软删除、上传、天气缓存、管理端和 AI SSE 完整流程。
