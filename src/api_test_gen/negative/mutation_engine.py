from typing import Any, Dict, List, Tuple, Optional
import random
from ..ir.models import SchemaRef

# Injection payloads
INJECTION_PAYLOADS = [
    "' OR 1=1 --",
    "\"; DROP TABLE users; --",
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "../../etc/passwd",
    "$(whoami)",
    "{{7*7}}"
]

class MutationEngine:
    """
    Generates negative payloads based on schema constraints and common attack vectors.
    """
    def __init__(self, components: Dict[str, SchemaRef]):
        self.components = components

    def generate_mutations(self, schema: SchemaRef, base_payload: Any) -> List[Tuple[str, Any]]:
        """
        Generates a list of (description, mutated_payload) for a given schema and valid base payload.
        """
        results = []
        
        # Resolve top-level ref
        resolved_schema = self._resolve_schema(schema)

        if resolved_schema.type == "object" and isinstance(base_payload, dict):
            # 1. Required fields removal
            if resolved_schema.required:
                for field in resolved_schema.required:
                    mutated = base_payload.copy()
                    if field in mutated:
                        del mutated[field]
                        results.append((f"missing_required_field_{field}", mutated))

            # 2. Extra unexpected fields
            mutated_extra = base_payload.copy()
            mutated_extra["hacker_extra_field"] = "unexpected_value"
            results.append(("extra_unexpected_field", mutated_extra))

            # 3. Property-level mutations
            if resolved_schema.properties:
                for prop_name, prop_schema in resolved_schema.properties.items():
                    prop_mutations = self._generate_property_mutations(prop_name, prop_schema, base_payload)
                    results.extend(prop_mutations)
                    
            # 4. Null injection for non-nullable fields at top level
            # (Already covered in property-level mutations if called from object)

        return results

    def _resolve_schema(self, schema: SchemaRef) -> SchemaRef:
        if schema.ref_name:
            return self.components.get(schema.ref_name, schema)
        return schema

    def _generate_property_mutations(
        self, 
        name: str, 
        schema: SchemaRef, 
        base_payload: Dict[str, Any]
    ) -> List[Tuple[str, Any]]:
        results = []
        resolved = self._resolve_schema(schema)
        
        if name not in base_payload:
            return results

        # 1. Type Mismatch
        wrong_type_val = self._get_wrong_type_value(resolved.type or "string")
        mutated = base_payload.copy()
        mutated[name] = wrong_type_val
        results.append((f"invalid_type_{name}", mutated))

        # 2. Null Injection (if not nullable)
        if not resolved.nullable:
            mutated = base_payload.copy()
            mutated[name] = None
            results.append((f"null_injection_{name}", mutated))

        # 3. Enum Violations
        if resolved.enum:
            mutated = base_payload.copy()
            # Pick a value definitely not in enum
            invalid_enum = f"invalid_enum_{random.randint(1000, 9999)}"
            while invalid_enum in resolved.enum:
                invalid_enum = f"invalid_enum_{random.randint(1000, 9999)}"
            mutated[name] = invalid_enum
            results.append((f"invalid_enum_{name}", mutated))

        # 4. Boundary Violations (Numbers)
        if resolved.type in ["integer", "number"]:
            if resolved.minimum is not None:
                mutated = base_payload.copy()
                mutated[name] = resolved.minimum - 1
                results.append((f"boundary_min_violation_{name}", mutated))
            if resolved.maximum is not None:
                mutated = base_payload.copy()
                mutated[name] = resolved.maximum + 1
                results.append((f"boundary_max_violation_{name}", mutated))

        # 5. Boundary Violations (Strings)
        if resolved.type == "string":
            if resolved.min_length is not None and resolved.min_length > 0:
                mutated = base_payload.copy()
                mutated[name] = "a" * (resolved.min_length - 1)
                results.append((f"boundary_min_length_violation_{name}", mutated))
            
            if resolved.max_length is not None:
                mutated = base_payload.copy()
                mutated[name] = "a" * (resolved.max_length + 1)
                results.append((f"boundary_max_length_violation_{name}", mutated))
            else:
                # Oversized string anyway for safety/stress testing if no max_length
                mutated = base_payload.copy()
                mutated[name] = "a" * 5000 
                results.append((f"oversized_string_{name}", mutated))

        # 6. Format Violations
        format_val = None
        if resolved.extra and 'format' in resolved.extra:
            format_val = resolved.extra['format']
        
        if format_val == "email":
            mutated = base_payload.copy()
            mutated[name] = "not-an-email"
            results.append((f"invalid_format_email_{name}", mutated))
        elif format_val == "uuid":
            mutated = base_payload.copy()
            mutated[name] = "not-a-uuid"
            results.append((f"invalid_format_uuid_{name}", mutated))

        # 7. Injection Payloads
        for i, payload in enumerate(INJECTION_PAYLOADS):
            mutated = base_payload.copy()
            mutated[name] = payload
            # Use a short index to avoid too long names
            results.append((f"injection_{name}_{i}", mutated))

        return results

    def _get_wrong_type_value(self, current_type: str) -> Any:
        if current_type == "string":
            return 123
        if current_type == "integer" or current_type == "number":
            return "not-a-number"
        if current_type == "boolean":
            return "not-a-boolean"
        if current_type == "array":
            return "not-an-array"
        if current_type == "object":
            return "not-an-object"
        return True # Fallback
