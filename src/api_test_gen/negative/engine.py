from typing import Any, Dict, List, Tuple, Optional
from ..ir.models import SchemaRef
def generate_negative_tests(schema: SchemaRef, components: Dict[str, SchemaRef]) -> List[Tuple[str, Any]]:
    """
    Generates negative payloads based on schema constraints.
    Returns a list of tuples: (description, payload)
    """
    from ..generator.payloads import generate_payload
    results = []
    
    # Resolve top-level ref
    resolved_schema = schema
    if schema.ref_name:
        resolved_schema = components.get(schema.ref_name, schema)

    # Generate a base valid payload to mutate from (using the original schema for generation)
    base_payload = generate_payload(schema, components)
    if not isinstance(base_payload, dict):
        # We only handle object mutations for now
        return results

    # 1. Required fields removal
    if resolved_schema.required:
        for field in resolved_schema.required:
            mutated = base_payload.copy()
            if field in mutated:
                del mutated[field]
                results.append((f"missing_required_field_{field}", mutated))

    # 2. Property-level mutations
    if resolved_schema.properties:
        for prop_name, prop_schema in resolved_schema.properties.items():
            prop_results = _generate_property_mutations(prop_name, prop_schema, components, base_payload)
            results.extend(prop_results)

    return results

def _generate_property_mutations(
    name: str, 
    schema: SchemaRef, 
    components: Dict[str, SchemaRef], 
    base_payload: Dict[str, Any]
) -> List[Tuple[str, Any]]:
    results = []
    
    # Resolve ref if any
    resolved_schema = schema
    if schema.ref_name:
        resolved_schema = components.get(schema.ref_name, schema)

    # Type Mismatch
    if resolved_schema.type:
        wrong_type_val = _get_wrong_type_value(resolved_schema.type)
        mutated = base_payload.copy()
        mutated[name] = wrong_type_val
        results.append((f"invalid_type_{name}", mutated))

    # Enum Violations
    if resolved_schema.enum:
        mutated = base_payload.copy()
        mutated[name] = "invalid_enum_value_999" # Simple invalid enum
        results.append((f"invalid_enum_{name}", mutated))

    # Boundary Violations (Numbers)
    if resolved_schema.type in ["integer", "number"]:
        if resolved_schema.minimum is not None:
            mutated = base_payload.copy()
            mutated[name] = resolved_schema.minimum - 1
            results.append((f"boundary_min_violation_{name}", mutated))
        if resolved_schema.maximum is not None:
            mutated = base_payload.copy()
            mutated[name] = resolved_schema.maximum + 1
            results.append((f"boundary_max_violation_{name}", mutated))

    # Boundary Violations (Strings)
    if resolved_schema.type == "string":
        if resolved_schema.min_length is not None and resolved_schema.min_length > 0:
            mutated = base_payload.copy()
            mutated[name] = "a" * (resolved_schema.min_length - 1)
            results.append((f"boundary_min_length_violation_{name}", mutated))
        if resolved_schema.max_length is not None:
            mutated = base_payload.copy()
            mutated[name] = "a" * (resolved_schema.max_length + 1)
            results.append((f"boundary_max_length_violation_{name}", mutated))

    # Format Violations
    # Note: Our IR models.py doesn't seem to have 'format' field explicitly, 
    # but it has 'extra' where it might be.
    # Let's check SchemaRef in models.py again.
    # It has 'extra'.
    format_val = None
    if resolved_schema.extra and 'format' in resolved_schema.extra:
        format_val = resolved_schema.extra['format']
    
    if format_val == "email":
        mutated = base_payload.copy()
        mutated[name] = "not-an-email"
        results.append((f"invalid_format_email_{name}", mutated))
    elif format_val == "uuid":
        mutated = base_payload.copy()
        mutated[name] = "not-a-uuid"
        results.append((f"invalid_format_uuid_{name}", mutated))

    return results

def _get_wrong_type_value(current_type: str) -> Any:
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
    return None
