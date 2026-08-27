from app.services.content_security_service import normalize_result


def test_content_security_normalizes_block_and_success_results():
    blocked = normalize_result({"Data": '{"RiskLevel":"high","Score":91}'})
    passed = normalize_result({"data": {"suggestion": "pass", "score": 2}})

    assert blocked["status"] == "block"
    assert blocked["score"] == 91
    assert passed["status"] == "success"
    assert passed["passed"] is True
