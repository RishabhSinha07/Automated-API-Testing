import unittest
from api_test_gen.diff.engine import DiffEngine, DiffResult
from api_test_gen.ir.models import APISpec, Endpoint, SchemaRef
from api_test_gen.state.repo_manager import TestFileMetadata

class TestDiffEngine(unittest.TestCase):
    def setUp(self):
        # Base schemas
        self.schema_a = SchemaRef(type="object", ref_name="A")
        self.hash_a = self.schema_a.hash
        
        self.schema_b = SchemaRef(type="object", ref_name="B")
        self.hash_b = self.schema_b.hash

    def test_create_new_endpoint(self):
        spec = APISpec(
            title="Test API",
            version="1.0",
            endpoints=(
                Endpoint(method="GET", path="/new", responses={"200": self.schema_a}),
            )
        )
        existing = []
        
        engine = DiffEngine(spec, existing)
        result = engine.compute_diff()
        
        self.assertEqual(len(result.create), 1)
        self.assertEqual(result.create[0].id, "GET /new")
        self.assertEqual(len(result.update), 0)
        self.assertEqual(len(result.skip), 0)

    def test_skip_unchanged_endpoint(self):
        spec = APISpec(
            title="Test API",
            version="1.0",
            endpoints=(
                Endpoint(method="GET", path="/existing", responses={"200": self.schema_a}),
            )
        )
        existing = [
            TestFileMetadata(
                relative_path="tests/test_existing.py",
                endpoint_id="GET /existing",
                request_schema_hash=None,
                response_schema_hashes={"200": self.hash_a}
            )
        ]
        
        engine = DiffEngine(spec, existing)
        result = engine.compute_diff()
        
        self.assertEqual(len(result.skip), 1)
        self.assertEqual(result.skip[0], "GET /existing")
        self.assertEqual(len(result.update), 0)

    def test_update_changed_schema_hash(self):
        # Spec has Schema A, existing file has Schema B hash
        spec = APISpec(
            title="Test API",
            version="1.0",
            endpoints=(
                Endpoint(method="GET", path="/changed", responses={"200": self.schema_a}),
            )
        )
        existing = [
             TestFileMetadata(
                relative_path="tests/test_changed.py",
                endpoint_id="GET /changed",
                request_schema_hash=None,
                response_schema_hashes={"200": self.hash_b} # Different!
            )
        ]
        
        engine = DiffEngine(spec, existing)
        result = engine.compute_diff()
        
        self.assertEqual(len(result.update), 1)
        self.assertEqual(result.update[0], "GET /changed")

    def test_update_added_response_code(self):
        spec = APISpec(
            title="Test API",
            version="1.0",
            endpoints=(
                Endpoint(method="POST", path="/add_code", responses={"200": self.schema_a, "201": self.schema_b}),
            )
        )
        existing = [
             TestFileMetadata(
                relative_path="tests/test_add_code.py",
                endpoint_id="POST /add_code",
                request_schema_hash=None,
                response_schema_hashes={"200": self.hash_a} # Missing 201
            )
        ]
        
        engine = DiffEngine(spec, existing)
        result = engine.compute_diff()
        
        self.assertEqual(len(result.update), 1)

    def test_delete_removed_endpoint(self):
        spec = APISpec(title="Test API", version="1.0", endpoints=())
        existing = [
             TestFileMetadata(
                relative_path="tests/test_removed.py",
                endpoint_id="DELETE /removed"
            )
        ]
        
        engine = DiffEngine(spec, existing)
        result = engine.compute_diff()
        
        self.assertEqual(len(result.delete), 1)
        self.assertEqual(result.delete[0].endpoint_id, "DELETE /removed")

if __name__ == "__main__":
    unittest.main()
