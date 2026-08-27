from app.utils.pagination import normalize_pagination, pagination_payload


def test_normalize_pagination_applies_defaults_and_limits():
    assert normalize_pagination(None, None) == (1, 12, 0)
    assert normalize_pagination(0, 101) == (1, 100, 0)
    assert normalize_pagination(3, 20) == (3, 20, 40)


def test_pagination_payload_includes_total_pages():
    assert pagination_payload(page=2, page_size=12, total=25) == {
        "page": 2,
        "pageSize": 12,
        "total": 25,
        "totalPages": 3,
    }
    assert pagination_payload(page=1, page_size=12, total=0)["totalPages"] == 0
