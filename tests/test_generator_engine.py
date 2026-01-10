import os
import shutil
import pytest
from api_test_gen.ir.models import Endpoint, SchemaRef
from api_test_gen.generator.engine import update_or_create_test_file

@pytest.fixture
def repo_path(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    return str(path)

def test_create_new_file(repo_path):
    endpoint = Endpoint(
        method="GET",
        path="/users",
        responses={"200": SchemaRef(type="object", properties={"id": SchemaRef(type="integer")}, required=("id",))}
    )
    update_or_create_test_file(endpoint, {}, repo_path)
    
    file_path = os.path.join(repo_path, "tests/endpoints/get_users.py")
    assert os.path.exists(file_path)
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    assert "def test_get_users():" in content
    assert "# --- AUTO-GENERATED START ---" in content
    assert "# --- AUTO-GENERATED END ---" in content
    assert "response = client.get(f\"/users\")" in content
    assert "assert response.status_code == 200" in content
    assert "assert isinstance(data, dict)" in content
    assert "assert \"id\" in data" in content

def test_update_preserves_user_code(repo_path):
    endpoint = Endpoint(
        method="POST",
        path="/users",
        request_body=SchemaRef(type="object", properties={"name": SchemaRef(type="string")}),
        responses={"201": SchemaRef(type="object")}
    )
    
    # 1. Create initial file
    update_or_create_test_file(endpoint, {}, repo_path)
    file_path = os.path.join(repo_path, "tests/endpoints/post_users.py")
    
    # 2. Add user code outside block
    with open(file_path, 'a') as f:
        f.write("\n# USER CODE\ndef custom_helper():\n    pass\n")
    
    # 3. Update with new schema
    new_endpoint = Endpoint(
        method="POST",
        path="/users",
        request_body=SchemaRef(type="object", properties={"email": SchemaRef(type="string")}),
        responses={"201": SchemaRef(type="object")}
    )
    update_or_create_test_file(new_endpoint, {}, repo_path)
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Block should be updated
    assert "\"email\": \"test\"" in content
    assert "\"name\": \"test\"" not in content
    
    # User code should be preserved
    assert "# USER CODE" in content
    assert "def custom_helper():" in content

def test_idempotent_replaces_block_correctly(repo_path):
    endpoint = Endpoint(method="GET", path="/test", responses={"200": SchemaRef(type="object")})
    update_or_create_test_file(endpoint, {}, repo_path)
    file_path = os.path.join(repo_path, "tests/endpoints/get_test.py")
    
    with open(file_path, 'r') as f:
        first_content = f.read()
    
    # Second run should result in same auto-block (except timestamp in header)
    update_or_create_test_file(endpoint, {}, repo_path)
    
    with open(file_path, 'r') as f:
        second_content = f.read()
    
    # Check that we didn't double up markers
    assert second_content.count("# --- AUTO-GENERATED START ---") == 1
    assert second_content.count("# --- AUTO-GENERATED END ---") == 1
