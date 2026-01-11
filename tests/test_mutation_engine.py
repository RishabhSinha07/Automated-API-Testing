from api_test_gen.negative.mutation_engine import MutationEngine
from api_test_gen.ir.models import SchemaRef

def test_mutation_engine_required_fields():
    schema = SchemaRef(
        type="object",
        properties={
            "name": SchemaRef(type="string"),
            "age": SchemaRef(type="integer")
        },
        required=("name", "age")
    )
    engine = MutationEngine(components={})
    base_payload = {"name": "test", "age": 25}
    
    mutations = engine.generate_mutations(schema, base_payload)
    
    # Expect: missing_required_field_name, missing_required_field_age, plus property mutations, plus extra fields
    descriptions = [m[0] for m in mutations]
    assert "missing_required_field_name" in descriptions
    assert "missing_required_field_age" in descriptions
    
    # Check that the mutation actually removed the field
    for desc, payload in mutations:
        if desc == "missing_required_field_name":
            assert "name" not in payload
            assert "age" in payload

def test_mutation_engine_invalid_types():
    schema = SchemaRef(
        type="object",
        properties={
            "age": SchemaRef(type="integer")
        }
    )
    engine = MutationEngine(components={})
    base_payload = {"age": 25}
    
    mutations = engine.generate_mutations(schema, base_payload)
    descriptions = [m[0] for m in mutations]
    assert "invalid_type_age" in descriptions
    
    for desc, payload in mutations:
        if desc == "invalid_type_age":
            assert payload["age"] == "not-a-number"

def test_mutation_engine_enum_violation():
    schema = SchemaRef(
        type="object",
        properties={
            "status": SchemaRef(type="string", enum=("active", "inactive"))
        }
    )
    engine = MutationEngine(components={})
    base_payload = {"status": "active"}
    
    mutations = engine.generate_mutations(schema, base_payload)
    descriptions = [m[0] for m in mutations]
    assert "invalid_enum_status" in descriptions

def test_mutation_engine_boundary_violations():
    schema = SchemaRef(
        type="object",
        properties={
            "score": SchemaRef(type="integer", minimum=0, maximum=100)
        }
    )
    engine = MutationEngine(components={})
    base_payload = {"score": 50}
    
    mutations = engine.generate_mutations(schema, base_payload)
    descriptions = [m[0] for m in mutations]
    assert "boundary_min_violation_score" in descriptions
    assert "boundary_max_violation_score" in descriptions
    
    for desc, payload in mutations:
        if desc == "boundary_min_violation_score":
            assert payload["score"] == -1
        if desc == "boundary_max_violation_score":
            assert payload["score"] == 101
