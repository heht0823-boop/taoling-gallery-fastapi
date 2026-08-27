"""分页参数校验和统一分页响应构造。"""

def normalize_pagination(
    page: int | None,
    page_size: int | None,
) -> tuple[int, int, int]:
    """
    分页参数规范化处理
    对前端传入的page、page_size做边界兜底，计算数据库查询offset偏移量

    :param page: 前端传入页码，允许为None
    :param page_size: 前端传入每页条数，允许为None
    :return: (safe_page, safe_page_size, offset)
        safe_page: 安全页码，最小为1
        safe_page_size: 安全每页条数，范围 [1, 100]
        offset: SQL查询偏移量 (page‑1)*page_size
    """
    # 未传page默认1，页码最小不能小于1
    safe_page = max(page or 1, 1)
    # 未传page_size默认12；下限1，上限100，防止一次性拉取大量数据
    safe_page_size = min(max(page_size or 12, 1), 100)
    # 计算数据库offset偏移
    offset = (safe_page - 1) * safe_page_size
    return safe_page, safe_page_size, offset


def pagination_payload(*, page: int, page_size: int, total: int) -> dict:
    """
    构造分页返回payload，给前端分页组件使用
    关键字-only参数，强制调用时传命名参数

    :param page: 当前页码（经过normalize_pagination处理后的安全值）
    :param page_size: 每页条数（经过normalize_pagination处理后的安全值）
    :param total: 数据总条数
    :return: 分页信息字典
    """
    return {
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": (total + page_size - 1) // page_size,
    }
