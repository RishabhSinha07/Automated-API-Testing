from typing import Any, Dict, Optional, Tuple, List
import logging
import yaml
import json
from pathlib import Path

from ..ir.models import APISpec, Endpoint, SchemaRef

logger = logging.getLogger(__name__)

class OpenAPIParser:
    """
    Parses OpenAPI V3 specifications into Canonical API IR.
    """

    def __init__(self, spec_content: str, is_yaml: bool = False):
        if is_yaml:
            self.spec = yaml.safe_load(spec_content)
        else:
            self.spec = json.loads(spec_content)
        
        self._validate_version()

    def _validate_version(self):
        openapi_version = self.spec.get("openapi", "")
        if not openapi_version.startswith("3."):
            raise ValueError(f"Unsupported OpenAPI version: {openapi_version}. Only 3.x is supported.")

    def parse(self) -> APISpec:
        """
        Main entry point to parse the specification.
        """
        info = self.spec.get("info", {})
        title = info.get("title", "Untitled")
        version = info.get("version", "0.0.0")

        components = self._parse_components()
        endpoints = self._parse_paths()

        return APISpec(
            title=title,
            version=version,
            endpoints=tuple(endpoints),
            components=components
        )

    def _parse_components(self) -> Dict[str, SchemaRef]:
        """
        Parses generic schemas from components/schemas.
        """
        schemas = self.spec.get("components", {}).get("schemas", {})
        parsed_components = {}
        
        for name, schema_dict in schemas.items():
            parsed_components[name] = self._convert_schema(schema_dict)
            
        return parsed_components

    def _parse_paths(self) -> List[Endpoint]:
        """
        Parses all paths and operations into Endpoints.
        """
        paths = self.spec.get("paths", {})
        endpoints = []

        for path_str, path_item in paths.items():
            # TODO: Handle path-level parameters (common to all operations)
            
            for method, operation in path_item.items():
                if method in ["parameters", "summary", "description"]:
                    continue # specific fields in Path Item Object, not operations
                
                endpoints.append(self._parse_endpoint(path_str, method, operation))
        
        return endpoints

    def _parse_endpoint(self, path: str, method: str, operation: Dict[str, Any]) -> Endpoint:
        """
        Parses a single operation into an Endpoint.
        """
        logger.debug(f"Parsing {method.upper()} {path}")
        summary = operation.get("summary")
        description = operation.get("description")
        
        # Parse Parameters
        raw_params = operation.get("parameters", [])
        parameters: List[Dict[str, Any]] = []
        for p in raw_params:
            if "$ref" in p:
                raise NotImplementedError("Parameter $ref resolution not yet implemented")
            
            # Keep raw param dict, but ensure valid JSON types where possible
            parameters.append(p)

        # Parse Request Body
        request_body_schema: Optional[SchemaRef] = None
        if "requestBody" in operation:
            content = operation["requestBody"].get("content", {})
            if not content:
                pass # Empty body?
            elif "application/json" in content:
                request_body_schema = self._convert_schema(content["application/json"]["schema"])
            else:
                # Fail loudly as requested
                # TODO: Support application/x-www-form-urlencoded or multipart/form-data
                raise ValueError(f"Unsupported requestBody content types in {method.upper()} {path}: {list(content.keys())}")

        # Parse Responses
        responses: Dict[str, SchemaRef] = {}
        for code, resp_obj in operation.get("responses", {}).items():
            if "$ref" in resp_obj:
                 # TODO: Resolve response refs
                 raise NotImplementedError("Response $ref resolution not yet implemented")
            
            content = resp_obj.get("content", {})
            if not content:
                # No content (e.g. 204 No Content)
                responses[code] = SchemaRef(extra={"empty_response": True}) 
            elif "application/json" in content:
                responses[code] = self._convert_schema(content["application/json"]["schema"])
            else:
                # TODO: Decide if we fail on non-json responses or just ignore them.
                # Instruction says "Fail loudly for unsupported OpenAPI constructs".
                # But generic errors often have text/plain.
                # Strictly following:
                raise ValueError(f"Unsupported response content types for {code} in {method.upper()} {path}: {list(content.keys())}")

        return Endpoint(
            method=method.upper(),
            path=path,
            summary=summary,
            description=description,
            parameters=tuple(parameters),
            request_body=request_body_schema,
            responses=responses
        )

    def _convert_schema(self, schema: Dict[str, Any]) -> SchemaRef:
        """
        Recursively converts an OpenAPI schema dict into a SchemaRef.
        """
        if not schema:
            # Empty schema {} matches everything
            return SchemaRef(extra={})

        if "$ref" in schema:
            # Assume '#/components/schemas/Name' format
            ref_path = schema["$ref"]
            if not ref_path.startswith("#/components/schemas/"):
                 # TODO: Support remote refs or other internal paths
                 raise NotImplementedError(f"Only #/components/schemas/ refs supported. Found: {ref_path}")
            ref_name = ref_path.split("/")[-1]
            return SchemaRef(ref_name=ref_name)

        # Basic fields
        schema_type = schema.get("type")
        nullable = schema.get("nullable", False)
        
        # Properties
        properties = {}
        if "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                properties[prop_name] = self._convert_schema(prop_schema)
        
        # Items (for arrays)
        items = None
        if "items" in schema:
            items = self._convert_schema(schema["items"])

        # Create immutables
        required = tuple(sorted(schema.get("required", []))) if "required" in schema else None
        enum_vals = tuple(schema.get("enum")) if "enum" in schema else None

        # TODO: Handle 'allOf', 'oneOf', 'anyOf'
        if any(k in schema for k in ["allOf", "oneOf", "anyOf"]):
            raise NotImplementedError("allOf/oneOf/anyOf not yet supported")

        return SchemaRef(
            type=schema_type,
            properties=properties or None,
            items=items,
            required=required,
            nullable=nullable,
            enum=enum_vals
        )

def load_from_file(path: str) -> APISpec:
    with open(path, 'r') as f:
        content = f.read()
    
    is_yaml = path.endswith('.yaml') or path.endswith('.yml')
    return OpenAPIParser(content, is_yaml=is_yaml).parse()
