from app.core.exceptions import AppError,conflict
from app.core.response import api_response
def test_conflict_error():
    exc=conflict('用户名已存在')
    assert isinstance(exc,AppError)
    assert exc.status_code==409
    assert exc.message=='用户名已存在'

def test_api_response_status():
    response=api_response({'id':1},"success",200)
    assert response.status_code==200