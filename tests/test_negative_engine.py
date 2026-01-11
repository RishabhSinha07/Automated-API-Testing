import pytest
from api_test_gen.ir.models import SchemaRef
from api_test_gen.negative.engine import generate_negative_tests

def test_missing_required_fields():
    schema = SchemaRef(
        type="object",
        properties={
            "name": SchemaRef(type="string"),
            "age": SchemaRef(type="integer")
        },
        required=("name",)
    )
    components = {}
    neg_tests = generate_negative_tests(schema, components)
    
    # Should have missing_required_field_name
    descriptions = [d for d, p in neg_tests]
    assert "missing_required_field_name" in descriptions
    
    # Check payload for that test
    payload = next(p for d, p in neg_tests if d == "missing_required_field_name")
    assert "name" not in payload
    assert "age" in payload

def test_invalid_types():
    schema = SchemaRef(
        type="object",
        properties={
            "age": SchemaRef(type="integer")
        }
    )
    components = {}
    neg_tests = generate_negative_tests(schema, components)
    
    descriptions = [d for d, p in neg_tests]
    assert "invalid_type_age" in descriptions
    
    payload = next(p for d, p in neg_tests if d == "invalid_type_age")
    assert payload["age"] == "not-a-number"

def test_boundary_violations():
    schema = SchemaRef(
        type="object",
        properties={
            "score": SchemaRef(type="integer", minimum=0, maximum=100)
        }
    )
    components = {}
    neg_tests = generate_negative_tests(schema, components)
    
    descriptions = [d for d, p in neg_tests]
    assert "boundary_min_violation_score" in descriptions
    assert "boundary_max_violation_score" in descriptions
    
    min_payload = next(p for d, p in neg_tests if d == "boundary_min_violation_score")
    assert min_payload["score"] == -1
    
    max_payload = next(p for d, p in neg_tests if d == "boundary_max_violation_score")
    assert max_payload["score"] == 101

def test_invalid_enum():
    schema = SchemaRef(
        type="object",
        properties={
            "status": SchemaRef(type="string", enum=("active", "inactive"))
        }
    )
    components = {}
    neg_tests = generate_negative_tests(schema, components)
    
    descriptions = [d for d, p in neg_tests]
    assert "invalid_enum_status" in descriptions
    
    payload = next(p for d, p in neg_tests if d == "invalid_enum_status")
    assert payload["status"] == "invalid_enum_value_999"

def test_invalid_format():
    schema = SchemaRef(
        type="object",
        properties={
            "email": SchemaRef(type="string", extra={"format": "email"}),
            "user_id": SchemaRef(type="string", extra={"format": "uuid"})
        }
    )
    components = {}
    neg_tests = generate_negative_tests(schema, components)
    
    descriptions = [d for d, p in neg_tests]
    assert "invalid_format_email_email" in descriptions
    assert "invalid_format_uuid_user_id" in descriptions
    
    email_payload = next(p for d, p in neg_tests if d == "invalid_format_email_email")
    assert email_payload["email"] == "not-an-email"
    
    uuid_payload = next(p for d, p in neg_tests if d == "invalid_format_uuid_user_id")
    assert uuid_payload["user_id"] == "not-a-uuid"
