from api_test_gen.negative.error_assertion_generator import ErrorAssertionGenerator
from api_test_gen.ir.models import SchemaRef

def test_error_assertion_with_schema():
    error_schema = SchemaRef(
        type="object",
        properties={
            "error_code": SchemaRef(type="integer"),
            "message": SchemaRef(type="string")
        },
        required=("error_code", "message")
    )
    generator = ErrorAssertionGenerator(components={})
    assertions = generator.generate_error_assertions(error_schema)
    
    assert "isinstance(data, dict)" in assertions[0]
    # Check if it generates property assertions
    assert 'assert "error_code" in data' in assertions
    assert 'assert "message" in data' in assertions

def test_error_assertion_fallback():
    # No schema provided
    generator = ErrorAssertionGenerator(components={})
    assertions = generator.generate_error_assertions(None)
    
    # Check for fallback fields
    assert "isinstance(data, dict)" in assertions[0]
    assert any("'code' in data" in a for a in assertions)
    assert any("'message' in data" in a for a in assertions)
    assert any("'details' in data" in a for a in assertions)
