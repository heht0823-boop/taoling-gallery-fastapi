import pytest


def clamp(value: int, minimum: int, maximum: int) -> int:
    """将数值限制在 [minimum, maximum] 区间内
    小于下限返回下限，大于上限返回上限，中间返回原值
    """
    return max(minimum, min(value, maximum))


@pytest.mark.parametrize(
    ("value", "expected"),  # 参数名
    [(1, 1), (0, 1), (200, 100)],  # 多组测试数据：输入值，预期输出
)
def test_clamp(value, expected):
    """参数化测试 clamp 函数，固定下限1，上限100"""
    # 调用clamp，断言实际结果等于预期结果
    assert clamp(value, 1, 100) == expected
