from typing import Any, Dict, List, Tuple, Optional
from ..ir.models import Endpoint

class SecurityNegativeTests:
    """
    Generates security-related negative tests based on security schemes.
    """
    def __init__(self):
        pass

    def generate_security_tests(self, endpoint: Endpoint) -> List[Dict[str, Any]]:
        """
        Generates security test scenarios for an endpoint.
        Returns a list of dicts: { "name": ..., "auth_override": ..., "expected_status": [401, 403] }
        """
        if not endpoint.security:
            return []

        scenarios = []

        # 1. No token
        scenarios.append({
            "name": "security_no_token",
            "auth_override": None, # Indicates no auth should be sent
            "expected_status": [401, 403]
        })

        # 2. Invalid token
        scenarios.append({
            "name": "security_invalid_token",
            "auth_override": "INVALID_TOKEN_123",
            "expected_status": [401, 403]
        })

        # 3. Expired token (mock)
        # We can't easily mock expiration without knowing the format (JWT etc.),
        # but we can send a "likely expired" lookalike or just a specific string.
        scenarios.append({
            "name": "security_expired_token",
            "auth_override": "EXPIRED_TOKEN_MOCK",
            "expected_status": [401, 403]
        })

        return scenarios
