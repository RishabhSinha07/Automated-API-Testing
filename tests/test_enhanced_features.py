import json
import unittest
from api_test_gen.parser.openapi import OpenAPIParser
from api_test_gen.generator.payloads import generate_payload
from api_test_gen.generator.assertions import generate_response_assertions

COMPOSITE_SPEC = """
openapi: 3.0.0
info:
  title: Enhanced API
  version: 1.0.0
components:
  schemas:
    Base:
      type: object
      properties:
        id: {type: integer}
    Extended:
      allOf:
        - $ref: '#/components/schemas/Base'
        - type: object
          properties:
            name: {type: string, minLength: 5}
            secret: {type: string, writeOnly: true}
    Combined:
      oneOf:
        - type: string
        - type: integer
  parameters:
    PageSize:
      name: pageSize
      in: query
      schema: {type: integer}
  responses:
    NotFound:
      description: Not Found
      content:
        application/json:
          schema:
            type: object
            properties:
              error: {type: string}
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
paths:
  /items/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema: {type: string}
    get:
      parameters:
        - $ref: '#/components/parameters/PageSize'
      responses:
        '200':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Extended'
        '404':
          $ref: '#/components/responses/NotFound'
    post:
      requestBody:
        content:
          application/x-www-form-urlencoded:
            schema:
              $ref: '#/components/schemas/Extended'
      responses:
        '201':
          description: Created
security:
  - bearerAuth: []
servers:
  - url: https://api.example.com/v1
"""

class TestEnhancedFeatures(unittest.TestCase):
    def test_all_of_flattening(self):
        parser = OpenAPIParser(COMPOSITE_SPEC, is_yaml=True)
        spec = parser.parse()
        
        extended = spec.components["Extended"]
        # flattened
        self.assertIn("id", extended.properties)
        self.assertIn("name", extended.properties)
        self.assertEqual(extended.properties["name"].min_length, 5)
        
    def test_parameter_ref_resolution(self):
        parser = OpenAPIParser(COMPOSITE_SPEC, is_yaml=True)
        spec = parser.parse()
        
        endpoint = spec.endpoint_map["GET /items/{id}"]
        # PageSize ref resolved
        param_names = [p["name"] for p in endpoint.parameters]
        self.assertIn("pageSize", param_names)
        self.assertIn("id", param_names)

    def test_response_ref_resolution(self):
        parser = OpenAPIParser(COMPOSITE_SPEC, is_yaml=True)
        spec = parser.parse()
        
        endpoint = spec.endpoint_map["GET /items/{id}"]
        not_found_resp = endpoint.responses["404"]
        self.assertIn("error", not_found_resp.properties)

    def test_security_parsing(self):
        parser = OpenAPIParser(COMPOSITE_SPEC, is_yaml=True)
        spec = parser.parse()
        
        self.assertIn("bearerAuth", spec.security_schemes)
        endpoint = spec.endpoint_map["GET /items/{id}"]
        self.assertIsNotNone(endpoint.security)
        self.assertEqual(endpoint.security[0]["bearerAuth"], ())

    def test_payload_generation_with_constraints(self):
        parser = OpenAPIParser(COMPOSITE_SPEC, is_yaml=True)
        spec = parser.parse()
        
        extended = spec.components["Extended"]
        payload = generate_payload(extended, spec.components)
        self.assertTrue(len(payload["name"]) >= 5)
        self.assertIn("secret", payload) # writeOnly is included in request payloads

    def test_assertion_generation_skips_write_only(self):
        parser = OpenAPIParser(COMPOSITE_SPEC, is_yaml=True)
        spec = parser.parse()
        
        extended = spec.components["Extended"]
        assertions = generate_response_assertions(extended, spec.components)
        assertions_str = "\n".join(assertions)
        self.assertIn('"id" in data', assertions_str)
        self.assertIn('"name" in data', assertions_str)
        self.assertNotIn('"secret" in data', assertions_str)

    def test_form_data_support(self):
        parser = OpenAPIParser(COMPOSITE_SPEC, is_yaml=True)
        spec = parser.parse()
        
        post_endpoint = spec.endpoint_map["POST /items/{id}"]
        self.assertEqual(post_endpoint.request_content_type, "application/x-www-form-urlencoded")

if __name__ == '__main__':
    unittest.main()
