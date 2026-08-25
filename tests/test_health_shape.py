import pytest
from main import health
@pytest.mark.asyncio
async def test_health_shape():
    result=await health()
    assert result['code']==200
    assert result['message']=='success'
    assert result['data']['status']=='ok'