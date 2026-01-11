from typing import Any, Dict, List, Optional
from ..ir.models import SchemaRef
from ..generator.assertions import generate_response_assertions

class ErrorAssertionGenerator:
    """
    Generates assertions for error responses (4xx, 5xx).
    Uses OpenAPI defined error schemas if available, otherwise falls back to generic validation.
    """
    def __init__(self, components: Dict[str, SchemaRef]):
        self.components = components

    def generate_error_assertions(
        self, 
        error_schema: Optional[SchemaRef], 
        var_name: str = "data"
    ) -> List[str]:
        """
        Generates code for asserting error structures.
        """
        if error_schema:
            try:
                # Use the existing assertion generator for the defined schema
                assertions = generate_response_assertions(error_schema, self.components, var_name)
                if assertions:
                    return assertions
            except Exception:
                # If something fails, fall back to generic
                pass

        # Fallback generic validation: code (int), message (string), details (optional list)
        return [
            f"assert isinstance({var_name}, dict)",
            f"if 'code' in {var_name}: assert isinstance({var_name}['code'], int)",
            f"if 'message' in {var_name}: assert isinstance({var_name}['message'], str)",
            f"if 'details' in {var_name}: assert isinstance({var_name}['details'], list)"
        ]
