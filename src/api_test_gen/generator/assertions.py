from typing import Any, Dict, List, Optional
from ..ir.models import SchemaRef

def generate_response_assertions(schema: SchemaRef, components: Dict[str, SchemaRef], var_name: str = "data") -> List[str]:
    """
    Generates deterministic assertions based on the response schema.
    """
    lines = []
    if schema.ref_name:
        resolved = components.get(schema.ref_name)
        if resolved:
            return generate_response_assertions(resolved, components, var_name)
        return []

    # Handle allOf - must match all schemas
    if schema.all_of:
        for sub in schema.all_of:
            lines.extend(generate_response_assertions(sub, components, var_name))
        # Proceed to check local properties as well
        if not schema.properties:
            return lines

    # Handle oneOf/anyOf - for responses, we just assert it matches AT LEAST ONE if we wanted to be strict,
    # but for simple positive tests, we will pick the first one's type assertion for now.
    # In a more advanced implementation, we would generate a try-except block or a helper function.
    if schema.one_of:
        return generate_response_assertions(schema.one_of[0], components, var_name)
    if schema.any_of:
        return generate_response_assertions(schema.any_of[0], components, var_name)

    if schema.type == "object":
        lines.append(f"assert isinstance({var_name}, dict)")
        if schema.properties:
            for name, prop in schema.properties.items():
                if prop.write_only:
                    continue # Skip writeOnly fields in responses
                
                # We assert existence for required fields, or all for completeness
                # If optional, we might skip, but let's stick to current "all" for now
                lines.append(f"assert \"{name}\" in {var_name}")
                lines.extend(_generate_type_assertion(prop, components, f"{var_name}[\"{name}\"]"))
    
    elif schema.type == "array":
        lines.append(f"assert isinstance({var_name}, list)")
        if schema.items:
            lines.append(f"if len({var_name}) > 0:")
            item_assertions = generate_response_assertions(schema.items, components, f"{var_name}[0]")
            for ia in item_assertions:
                lines.append(f"    {ia}")
    
    elif schema.type == "string":
        lines.append(f"assert isinstance({var_name}, str)")
        if schema.enum:
            lines.append(f"assert {var_name} in {list(schema.enum)}")
        if schema.min_length is not None:
            lines.append(f"assert len({var_name}) >= {schema.min_length}")
        if schema.max_length is not None:
            lines.append(f"assert len({var_name}) <= {schema.max_length}")
        if schema.pattern:
            # We'd need re module, let's keep it simple for now or skip pattern assert
            pass

    elif schema.type == "integer":
        lines.append(f"assert isinstance({var_name}, int)")
        if schema.minimum is not None:
            lines.append(f"assert {var_name} >= {schema.minimum}")
        if schema.maximum is not None:
            lines.append(f"assert {var_name} <= {schema.maximum}")

    elif schema.type == "number":
        lines.append(f"assert isinstance({var_name}, (int, float))")
        if schema.minimum is not None:
            lines.append(f"assert {var_name} >= {schema.minimum}")
        if schema.maximum is not None:
            lines.append(f"assert {var_name} <= {schema.maximum}")

    elif schema.type == "boolean":
        lines.append(f"assert isinstance({var_name}, bool)")

    return lines

def _generate_type_assertion(schema: SchemaRef, components: Dict[str, SchemaRef], val_path: str) -> List[str]:
    # This is a helper for nested properties to avoid infinite recursion or complex lines
    # It mostly just checks the type.
    lines = []
    if schema.ref_name:
        resolved = components.get(schema.ref_name)
        if resolved:
            return _generate_type_assertion(resolved, components, val_path)
        return []

    if schema.all_of:
        for sub in schema.all_of:
            lines.extend(_generate_type_assertion(sub, components, val_path))
        return lines

    if schema.one_of:
        return _generate_type_assertion(schema.one_of[0], components, val_path)
    if schema.any_of:
        return _generate_type_assertion(schema.any_of[0], components, val_path)

    if schema.type == "string":
        lines.append(f"assert isinstance({val_path}, str)")
    elif schema.type == "integer":
        lines.append(f"assert isinstance({val_path}, int)")
    elif schema.type == "number":
        lines.append(f"assert isinstance({val_path}, (int, float))")
    elif schema.type == "boolean":
        lines.append(f"assert isinstance({val_path}, bool)")
    elif schema.type == "object":
        lines.append(f"assert isinstance({val_path}, dict)")
    elif schema.type == "array":
        lines.append(f"assert isinstance({val_path}, list)")
    
    return lines
