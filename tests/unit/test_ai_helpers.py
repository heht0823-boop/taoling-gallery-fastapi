"""桃灵助手纯函数与 SSE 开关契约测试。"""

from app.api.routes.user.ai import _should_stream
from app.services.ai_provider import normalize_strings
from app.services.ai_tools import normalize_image_ids, search_tokens


def test_ai_stream_defaults_and_explicit_false_values():
    """未传 stream 时默认流式，query 参数优先覆盖 JSON body。"""

    assert _should_stream(None, None) is True
    assert _should_stream(None, True) is True
    assert _should_stream(None, False) is False
    assert _should_stream("false", True) is False
    assert _should_stream("0", True) is False
    assert _should_stream("true", False) is True


def test_ai_provider_normalizes_model_arrays():
    """模型数组必须保持顺序、去重、去空并遵守数量上限。"""

    assert normalize_strings([" 风景 ", "", "风景", "插画"], limit=2) == [
        "风景",
        "插画",
    ]
    assert normalize_strings("风景") == []


def test_ai_tool_helpers_sanitize_search_and_image_ids():
    """本地工具只接收有效搜索片段和有序正整数图片 ID。"""

    assert search_tokens("请帮我找一些梦幻 风景图片") == ["梦幻", "风景"]
    assert normalize_image_ids(["2", 2, -1, "bad", 3]) == [2, 3]
