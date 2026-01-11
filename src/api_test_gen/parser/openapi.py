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
        
        security_schemes = self.spec.get("components", {}).get("securitySchemes", {})
        servers = self.spec.get("servers", [])

        return APISpec(
            title=title,
            version=version,
            endpoints=tuple(endpoints),
            components=components,
            security_schemes=security_schemes,
            servers=tuple(servers)
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

    def _resolve_ref(self, ref_path: str) -> Dict[str, Any]:
        """
        Resolves a JSON reference within the specification.
        """
        if not ref_path.startswith("#/"):
            raise NotImplementedError(f"External references not supported: {ref_path}")
        
        parts = ref_path.lstrip("#/").split("/")
        current = self.spec
        for part in parts:
            if part not in current:
                raise ValueError(f"Could not resolve reference: {ref_path}")
            current = current[part]
        return current

    def _parse_paths(self) -> List[Endpoint]:
        """
        Parses all paths and operations into Endpoints.
        """
        paths = self.spec.get("paths", {})
        endpoints = []

        for path_str, path_item in paths.items():
            # Path-level parameters
            path_params = path_item.get("parameters", [])
            
            for method, operation in path_item.items():
                if method in ["parameters", "summary", "description"]:
                    continue # specific fields in Path Item Object, not operations
                
                # Merge path-level params with operation-level params
                op_params = operation.get("parameters", [])
                merged_params = path_params + op_params
                
                endpoints.append(self._parse_endpoint(path_str, method, operation, merged_params))
        
        return endpoints

    def _parse_endpoint(self, path: str, method: str, operation: Dict[str, Any], raw_params: List[Dict[str, Any]]) -> Endpoint:
        """
        Parses a single operation into an Endpoint.
        """
        logger.debug(f"Parsing {method.upper()} {path}")
        summary = operation.get("summary")
        description = operation.get("description")
        
        # Parse Parameters (Resolve $ref)
        parameters: List[Dict[str, Any]] = []
        for p in raw_params:
            if "$ref" in p:
                p = self._resolve_ref(p["$ref"])
            parameters.append(p)

        # Parse Request Body
        request_body_schema: Optional[SchemaRef] = None
        request_content_type: Optional[str] = None
        if "requestBody" in operation:
            rb_obj = operation["requestBody"]
            if "$ref" in rb_obj:
                rb_obj = self._resolve_ref(rb_obj["$ref"])
            
            content = rb_obj.get("content", {})
            if "application/json" in content:
                request_body_schema = self._convert_schema(content["application/json"]["schema"])
                request_content_type = "application/json"
            elif "application/x-www-form-urlencoded" in content:
                request_body_schema = self._convert_schema(content["application/x-www-form-urlencoded"]["schema"])
                request_content_type = "application/x-www-form-urlencoded"
            elif "multipart/form-data" in content:
                request_body_schema = self._convert_schema(content["multipart/form-data"]["schema"])
                request_content_type = "multipart/form-data"
            elif content:
                # Pick the first one if not JSON/Form
                first_ct = list(content.keys())[0]
                request_body_schema = self._convert_schema(content[first_ct]["schema"])
                request_content_type = first_ct

        # Parse Responses
        responses: Dict[str, SchemaRef] = {}
        for code, resp_obj in operation.get("responses", {}).items():
            if "$ref" in resp_obj:
                 resp_obj = self._resolve_ref(resp_obj["$ref"])
            
            content = resp_obj.get("content", {})
            if not content:
                # No content (e.g. 204 No Content)
                responses[code] = SchemaRef(extra={"empty_response": True}) 
            elif "application/json" in content:
                responses[code] = self._convert_schema(content["application/json"]["schema"])
            else:
                # Just take the first available content type's schema
                first_ct = list(content.keys())[0]
                responses[code] = self._convert_schema(content[first_ct]["schema"])

        # Parse Security
        security = operation.get("security", self.spec.get("security"))
        parsed_security = None
        if security:
            # security is a list of requirement objects
            # [{ "auth": ["scope"] }]
            temp_sec = []
            for req in security:
                item = {k: tuple(v) for k, v in req.items()}
                temp_sec.append(item)
            parsed_security = tuple(temp_sec)

        return Endpoint(
            method=method.upper(),
            path=path,
            summary=summary,
            description=description,
            parameters=tuple(parameters),
            request_body=request_body_schema,
            request_content_type=request_content_type,
            responses=responses,
            security=parsed_security
        )

    def _convert_schema(self, schema: Dict[str, Any]) -> SchemaRef:
        """
        Recursively converts an OpenAPI schema dict into a SchemaRef.
        """
        if not schema:
            return SchemaRef(extra={})

        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/components/schemas/"):
                ref_name = ref_path.split("/")[-1]
                return SchemaRef(ref_name=ref_name)
            else:
                # Resolve other refs immediately for IR simplification
                resolved = self._resolve_ref(ref_path)
                return self._convert_schema(resolved)

        if "allOf" in schema:
            merged_properties = {}
            merged_required = set()
            base_type = schema.get("type")
            
            for sub_schema_dict in schema["allOf"]:
                sub_ref = self._convert_schema(sub_schema_dict)
                # To flatten, we need the actual properties. If it's a ref, resolve it.
                if sub_ref.ref_name:
                    resolved = self._resolve_ref(f"#/components/schemas/{sub_ref.ref_name}")
                    # Recursively convert to handle nested allOf etc.
                    sub_ref = self._convert_schema(resolved)
                
                if sub_ref.properties:
                    merged_properties.update(sub_ref.properties)
                if sub_ref.required:
                    merged_required.update(sub_ref.required)
                if sub_ref.type:
                    base_type = sub_ref.type

            # Merge current level's properties and required
            if "properties" in schema:
                for k, v in schema["properties"].items():
                    merged_properties[k] = self._convert_schema(v)
            if "required" in schema:
                merged_required.update(schema["required"])

            return SchemaRef(
                type=base_type or "object",
                properties=merged_properties or None,
                required=tuple(sorted(list(merged_required))) if merged_required else None,
                all_of=tuple(self._convert_schema(s) for s in schema["allOf"])
            )

        # Composition for oneOf/anyOf (Not flattened, just stored)
        one_of = tuple(self._convert_schema(s) for s in schema["oneOf"]) if "oneOf" in schema else None
        any_of = tuple(self._convert_schema(s) for s in schema["anyOf"]) if "anyOf" in schema else None

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

        # Constraints
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        pattern = schema.get("pattern")
        read_only = schema.get("readOnly", False)
        write_only = schema.get("writeOnly", False)

        return SchemaRef(
            type=schema_type,
            properties=properties or None,
            items=items,
            required=required,
            nullable=nullable,
            enum=enum_vals,
            one_of=one_of,
            any_of=any_of,
            min_length=min_length,
            max_length=max_length,
            minimum=minimum,
            maximum=maximum,
            pattern=pattern,
            read_only=read_only,
            write_only=write_only
        )

def load_from_file(path: str) -> APISpec:
    with open(path, 'r') as f:
        content = f.read()
    
    is_yaml = path.endswith('.yaml') or path.endswith('.yml')
    return OpenAPIParser(content, is_yaml=is_yaml).parse()
