"""阿里云文本内容安全适配器。

签名、请求和不同版本响应在本模块内归一化，留言服务只依赖 ``passed`` 等稳定
业务字段；未开启审核时明确返回开发环境放行结果。
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import uuid4

import httpx

from app.core.config import settings
from app.core.exceptions import bad_request


def _percent_encode(value: object) -> str:
    """按阿里云 RPC 签名规范编码单个参数。"""

    return quote(str(value), safe="~")


def normalize_result(raw: dict) -> dict:
    """兼容阿里云不同审核服务的响应结构，输出统一审核结论。"""
    data = raw.get("Data", raw.get("data", {}))
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    results = data.get("Result") or data.get("result") or data.get("Results") or data.get("results") or []
    first_result = results[0] if isinstance(results, list) and results else {}
    if not isinstance(first_result, dict):
        first_result = {}
    labels = [
        data.get("Label"),
        data.get("label"),
        data.get("RiskLevel"),
        data.get("riskLevel"),
        data.get("suggestion"),
        data.get("Suggestion"),
        first_result.get("label"),
        first_result.get("riskLevel"),
        first_result.get("suggestion"),
    ]
    normalized_labels = {str(label).lower() for label in labels if label}
    score_value = (
        data.get("Score")
        or data.get("score")
        or data.get("RiskScore")
        or data.get("riskScore")
        or first_result.get("score")
        or 0
    )
    try:
        score = float(score_value)
    except (TypeError, ValueError):
        score = 0.0
    blocked = bool(normalized_labels.intersection({"block", "high", "deny", "review"})) or score >= 80
    return {
        "passed": not blocked,
        "status": "block" if blocked else "success",
        "score": score,
        "raw": raw,
    }


async def _request_aliyun(service_parameters: dict) -> dict:
    """签名并发送阿里云文本审核请求。"""

    if not settings.ali_access_key_id or not settings.ali_access_key_secret:
        raise bad_request("阿里云内容安全 AccessKey 未配置")
    params = {
        "Action": settings.ali_text_action,
        "Version": settings.ali_api_version,
        "Format": "JSON",
        "AccessKeyId": settings.ali_access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid4()),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "RegionId": settings.ali_region_id,
        "Service": settings.ali_service_name,
        "ServiceParameters": json.dumps(
            service_parameters,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    canonicalized = "&".join(
        f"{_percent_encode(key)}={_percent_encode(params[key])}" for key in sorted(params)
    )
    string_to_sign = f"POST&{_percent_encode('/')}&{_percent_encode(canonicalized)}"
    signature = base64.b64encode(
        hmac.new(
            f"{settings.ali_access_key_secret}&".encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        ).digest()
    ).decode()
    body = f"{canonicalized}&Signature={_percent_encode(signature)}"
    timeout = settings.ali_timeout_ms / 1000
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"https://{settings.ali_endpoint.strip('/')}/",
                content=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise bad_request("阿里云内容安全审核失败") from exc
    if not isinstance(payload, dict):
        raise bad_request("阿里云内容安全审核响应格式错误")
    if response.is_error or (payload.get("Code") and str(payload.get("Code")) != "200"):
        raise bad_request(
            payload.get("Message")
            or payload.get("Msg")
            or payload.get("message")
            or payload.get("msg")
            or "阿里云内容安全审核失败",
            payload,
        )
    return payload


async def check_text(*, content: str, data_id: str, user_id: int) -> dict:
    """审核留言文本；开发环境关闭审核时显式返回通过结果。"""
    if not settings.content_security_enabled:
        return {
            "passed": True,
            "status": "success",
            "score": 0.0,
            "raw": {"provider": "disabled"},
        }
    raw = await _request_aliyun(
        {
            "content": content,
            "dataId": data_id,
            "accountId": str(user_id),
        }
    )
    return normalize_result(raw)
