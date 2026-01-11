from api_test_gen.negative.security_negative_tests import SecurityNegativeTests
from api_test_gen.ir.models import Endpoint

def test_generate_security_tests():
    endpoint = Endpoint(
        method="GET",
        path="/secure",
        security=({"Bearer": ()},) # Security is required
    )
    generator = SecurityNegativeTests()
    scenarios = generator.generate_security_tests(endpoint)
    
    assert len(scenarios) == 3
    names = [s["name"] for s in scenarios]
    assert "security_no_token" in names
    assert "security_invalid_token" in names
    assert "security_expired_token" in names
    
    for s in scenarios:
        assert s["expected_status"] == [401, 403]

def test_no_security_tests_if_not_required():
    endpoint = Endpoint(
        method="GET",
        path="/public",
        security=None # No security
    )
    generator = SecurityNegativeTests()
    scenarios = generator.generate_security_tests(endpoint)
    
    assert len(scenarios) == 0
