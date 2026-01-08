import unittest
import tempfile
import shutil
import os
from api_test_gen.state.repo_manager import read_existing_tests, TestFileMetadata

class TestRepoManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.repo_tests_dir = os.path.join(self.test_dir, "tests", "endpoints")
        os.makedirs(self.repo_tests_dir)
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)
        
    def test_read_valid_metadata(self):
        file_content = """
# endpoint_id: GET /users
# request_schema_hash: hash123
# response_schema_hash_200: hash200
# response_schema_hash_404: hash404

def test_get_users():
    pass
"""
        with open(os.path.join(self.repo_tests_dir, "test_get_users.py"), "w") as f:
            f.write(file_content)
            
        results = read_existing_tests(self.test_dir)
        
        self.assertEqual(len(results), 1)
        meta = results[0]
        self.assertEqual(meta.endpoint_id, "GET /users")
        self.assertEqual(meta.request_schema_hash, "hash123")
        self.assertEqual(meta.response_schema_hashes, {"200": "hash200", "404": "hash404"})
        self.assertIn("tests/endpoints/test_get_users.py", meta.relative_path)

    def test_ignore_files_without_metadata(self):
        file_content = """
def test_something_else():
    pass
"""
        with open(os.path.join(self.repo_tests_dir, "test_other.py"), "w") as f:
            f.write(file_content)
            
        results = read_existing_tests(self.test_dir)
        self.assertEqual(len(results), 0)

    def test_invalid_path(self):
        with self.assertRaises(FileNotFoundError):
            read_existing_tests("/invalid/path/does/not/exist")

if __name__ == "__main__":
    unittest.main()
