from api_test_gen.ir.models import SchemaRef
from api_test_gen.generator.payloads import generate_payload

def test_primitives():
    assert generate_payload(SchemaRef(type="string"), {}) == "test"
    assert generate_payload(SchemaRef(type="integer"), {}) == 1
    assert generate_payload(SchemaRef(type="number"), {}) == 1.0
    assert generate_payload(SchemaRef(type="boolean"), {}) == True

def test_enum():
    schema = SchemaRef(type="string", enum=("active", "inactive"))
    assert generate_payload(schema, {}) == "active"

def test_array():
    items = SchemaRef(type="string")
    schema = SchemaRef(type="array", items=items)
    assert generate_payload(schema, {}) == ["test"]

def test_object():
    props = {
        "name": SchemaRef(type="string"),
        "age": SchemaRef(type="integer")
    }
    schema = SchemaRef(type="object", properties=props)
    payload = generate_payload(schema, {})
    assert payload == {"name": "test", "age": 1}

def test_nested_object():
    inner_props = {"id": SchemaRef(type="integer")}
    inner = SchemaRef(type="object", properties=inner_props)
    outer_props = {"user": inner}
    outer = SchemaRef(type="object", properties=outer_props)
    payload = generate_payload(outer, {})
    assert payload == {"user": {"id": 1}}

def test_ref_resolution():
    components = {
        "User": SchemaRef(
            type="object", 
            properties={"username": SchemaRef(type="string")}
        )
    }
    schema = SchemaRef(ref_name="User")
    payload = generate_payload(schema, components)
    assert payload == {"username": "test"}

def test_recursive_array_of_objects():
    user_schema = SchemaRef(
        type="object", 
        properties={"id": SchemaRef(type="integer")}
    )
    schema = SchemaRef(type="array", items=user_schema)
    payload = generate_payload(schema, {})
    assert payload == [{"id": 1}]

def test_nullable_always_non_null():
    schema = SchemaRef(type="string", nullable=True)
    assert generate_payload(schema, {}) == "test"
