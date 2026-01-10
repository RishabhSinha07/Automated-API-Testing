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

    if schema.type == "object":
        lines.append(f"assert isinstance({var_name}, dict)")
        if schema.properties:
            for name, prop in schema.properties.items():
                # We assert existence and type for properties
                # To be deterministic and safe, we mostly focus on required ones or common ones
                # In this generator, we'll assert all properties present in the schema for completeness
                lines.append(f"assert \"{name}\" in {var_name}")
                lines.extend(_generate_type_assertion(prop, components, f"{var_name}[\"{name}\"]"))
    elif schema.type == "array":
        lines.append(f"assert isinstance({var_name}, list)")
        if schema.items:
            lines.append(f"if len({var_name}) > 0:")
            # Recurse for the first item
            item_assertions = generate_response_assertions(schema.items, components, f"{var_name}[0]")
            for ia in item_assertions:
                lines.append(f"    {ia}")
    elif schema.type == "string":
        lines.append(f"assert isinstance({var_name}, str)")
        if schema.enum:
            lines.append(f"assert {var_name} in {list(schema.enum)}")
    elif schema.type == "integer":
        lines.append(f"assert isinstance({var_name}, int)")
    elif schema.type == "number":
        lines.append(f"assert isinstance({var_name}, (int, float))")
    elif schema.type == "boolean":
        lines.append(f"assert isinstance({var_name}, bool)")

    return lines

def _generate_type_assertion(schema: SchemaRef, components: Dict[str, SchemaRef], val_path: str) -> List[str]:
    lines = []
    if schema.ref_name:
        resolved = components.get(schema.ref_name)
        if resolved:
            return _generate_type_assertion(resolved, components, val_path)
        return []

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
