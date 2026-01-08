import unittest
from api_test_gen.parser.openapi import OpenAPIParser
from api_test_gen.ir.models import APISpec, Endpoint, SchemaRef

MINIMAL_OPENAPI = """
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
components:
  schemas:
    User:
      type: object
      properties:
        id:
          type: integer
        name:
          type: string
      required:
        - id
        - name
paths:
  /users:
    get:
      summary: List users
      responses:
        '200':
          description: A list of users
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/User'
    post:
      summary: Create user
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/User'
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/User'
"""

class TestOpenAPIParser(unittest.TestCase):
    def test_basic_structure(self):
        parser = OpenAPIParser(MINIMAL_OPENAPI, is_yaml=True)
        spec = parser.parse()
        
        self.assertIsInstance(spec, APISpec)
        self.assertEqual(spec.title, "Test API")
        self.assertEqual(spec.version, "1.0.0")
        self.assertIn("User", spec.components)
        
    def test_endpoints(self):
        parser = OpenAPIParser(MINIMAL_OPENAPI, is_yaml=True)
        spec = parser.parse()
        
        endpoint_map = spec.endpoint_map
        self.assertIn("GET /users", endpoint_map)
        self.assertIn("POST /users", endpoint_map)

    def test_schema_conversion_ref(self):
        parser = OpenAPIParser(MINIMAL_OPENAPI, is_yaml=True)
        spec = parser.parse()
        
        # Test reference resolution in a response
        get_user = spec.endpoint_map["GET /users"]
        response_schema = get_user.responses["200"]
        
        self.assertEqual(response_schema.type, "array")
        self.assertIsNotNone(response_schema.items)
        self.assertEqual(response_schema.items.ref_name, "User")
        
    def test_request_body(self):
        parser = OpenAPIParser(MINIMAL_OPENAPI, is_yaml=True)
        spec = parser.parse()
        
        post_user = spec.endpoint_map["POST /users"]
        self.assertIsNotNone(post_user.request_body)
        self.assertEqual(post_user.request_body.ref_name, "User")

    def test_unsupported_version(self):
        bad_spec = MINIMAL_OPENAPI.replace("openapi: 3.0.0", "openapi: 2.0.0")
        with self.assertRaises(ValueError):
            OpenAPIParser(bad_spec, is_yaml=True)
            
    def test_unsupported_media_type(self):
        # Inject xml content type
        bad_spec = MINIMAL_OPENAPI.replace("application/json", "application/xml")
        parser = OpenAPIParser(bad_spec, is_yaml=True)
        with self.assertRaises(ValueError):
            parser.parse()

if __name__ == '__main__':
    unittest.main()
