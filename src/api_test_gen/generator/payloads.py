from typing import Any, Dict
from ..ir.models import SchemaRef

def generate_payload(schema: SchemaRef, components: Dict[str, SchemaRef]) -> Any:
    if schema.ref_name:
        resolved = components.get(schema.ref_name)
        if resolved:
            return generate_payload(resolved, components)
        return None
    
    # Handle allOf - merge multiple schema variants
    if schema.all_of:
        final_result = {}
        for sub in schema.all_of:
            sub_payload = generate_payload(sub, components)
            if isinstance(sub_payload, dict):
                final_result.update(sub_payload)
            elif sub_payload is not None:
                # If it's a primitive, it might be the only one or overriding
                final_result = sub_payload
        
        # Also include local properties if any
        if schema.properties:
            local_payload = {}
            for key, prop in schema.properties.items():
                if not prop.read_only:
                    local_payload[key] = generate_payload(prop, components)
            if isinstance(final_result, dict):
                final_result.update(local_payload)
        return final_result

    # Handle oneOf/anyOf - pick first variant for positive tests
    if schema.one_of:
        return generate_payload(schema.one_of[0], components)
    if schema.any_of:
        return generate_payload(schema.any_of[0], components)

    if schema.enum:
        return schema.enum[0]
    
    if schema.type == "string":
        val = "test"
        if schema.min_length and len(val) < schema.min_length:
            val = "a" * schema.min_length
        if schema.max_length and len(val) > schema.max_length:
            val = val[:schema.max_length]
        return val
        
    if schema.type == "integer":
        val = 1
        if schema.minimum is not None:
            val = int(schema.minimum)
        if schema.maximum is not None and val > schema.maximum:
            val = int(schema.maximum)
        return val
        
    if schema.type == "number":
        val = 1.0
        if schema.minimum is not None:
            val = float(schema.minimum)
        if schema.maximum is not None and val > schema.maximum:
            val = float(schema.maximum)
        return val
        
    if schema.type == "boolean":
        return True
        
    if schema.type == "array":
        if schema.items:
            return [generate_payload(schema.items, components)]
        return []
        
    if schema.type == "object" or (schema.type is None and schema.properties):
        result = {}
        if schema.properties:
            for key, prop in schema.properties.items():
                if prop.read_only:
                    continue # Skip readOnly fields in request payloads
                result[key] = generate_payload(prop, components)
        return result
    
    return None
