from typing import Any, Dict
from ..ir.models import SchemaRef

def generate_payload(schema: SchemaRef, components: Dict[str, SchemaRef]) -> Any:
    if schema.ref_name:
        resolved = components.get(schema.ref_name)
        if resolved:
            return generate_payload(resolved, components)
        return None
    
    if schema.enum:
        return schema.enum[0]
    
    if schema.type == "string":
        return "test"
    if schema.type == "integer":
        return 1
    if schema.type == "number":
        return 1.0
    if schema.type == "boolean":
        return True
    if schema.type == "array":
        if schema.items:
            return [generate_payload(schema.items, components)]
        return []
    if schema.type == "object" or (schema.type is None and schema.properties):
        result = {}
        if schema.properties:
            # We include all properties defined in the schema for a more complete payload,
            # ensuring all required ones are present.
            for key, prop in schema.properties.items():
                result[key] = generate_payload(prop, components)
        return result
    
    return None
