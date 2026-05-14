"""基础占位测试."""
from custom_components.workchat_integration.const import DOMAIN

def test_setup():
    """测试域名是否正确."""
    assert DOMAIN == "qweather"
