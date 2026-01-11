import os
import re
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from ..ir.models import Endpoint, APISpec
from ..diff.engine import DiffResult
from ..state.repo_manager import TestFileMetadata
from .payloads import generate_payload
from .assertions import generate_response_assertions
from ..negative.engine import generate_negative_tests

logger = logging.getLogger(__name__)

class GenerationEngine:
    def __init__(self, repo_path: str, test_dir_name: str = "tests/endpoints"):
        self.repo_path = repo_path
        self.test_dir = os.path.join(repo_path, test_dir_name)
        
    def apply_diff(self, diff: DiffResult) -> None:
        """
        Applies changes based on the diff result.
        """
        # Ensure target directory exists for creations
        if diff.create and not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir, exist_ok=True)

        # 1. Handle Creates
        for endpoint in diff.create:
            self._create_test_file(endpoint)

        # 2. Handle Updates
        # update list contains string IDs. We likely need the Endpoint object.
        # But DiffResult only has IDs for update/skip.
        # Wait, DiffResult definition in previous step: update: List[str]
        # I need the actual Endpoint object to generate new metadata/code.
        # The DiffEngine caller usually has existing_tests and new_spec. 
        # But here I only have DiffResult.
        # I should assume DiffResult might need to carry the Endpoint object or I need access to the Spec.
        # The prompt says: "Inputs: diff_map... repo_path".
        # It doesn't explicitly pass the APISpec.
        # However, to generate code for "create", I definitely need the Endpoint object which is in diff.create.
        # For "update", diff.update is List[str]. I can't generate code without the Endpoint object.
        # I will assume the caller passes the APISpec or a map of ID->Endpoint, 
        # OR I must modify DiffResult in memory? 
        # Let's assume for this implementation that I have access to the objects or the DiffResult matches my needs.
        # The previous DiffResult `update` was `List[str]`. 
        # I will change the signature of `apply_diff` to accept `spec_map` (ID->Endpoint) to simplify looking up the new endpoint data.
        pass

    def apply_diff_with_spec(self, diff: DiffResult, endpoint_map: Dict[str, Endpoint], components: Dict[str, Any] = None) -> None:
        """
        Applies changes based on the diff result, using the endpoint map for details.
        """
        self.components = components or {}
        if diff.create and not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir, exist_ok=True)

        for endpoint in diff.create:
            update_or_create_test_file(endpoint, self.components, self.repo_path)

        for endpoint_id in diff.update:
            if endpoint_id in endpoint_map:
                update_or_create_test_file(endpoint_map[endpoint_id], self.components, self.repo_path)
            else:
                logger.warning(f"Endpoint {endpoint_id} marked for update but not found in spec.")

        for endpoint_id in diff.skip:
            logger.info(f"Skipping {endpoint_id} (unchanged)")

        for metadata in diff.delete:
            self._delete_test_file(metadata)

    def _get_file_path(self, endpoint: Endpoint) -> str:
        # Deterministic filename: {method}_{path_slug}.py
        # Remove parameters {id} -> id
        safe_path = re.sub(r'[^a-zA-Z0-9]', '_', endpoint.path).strip('_')
        filename = f"{endpoint.method.lower()}_{safe_path}.py"
        return os.path.join(self.test_dir, filename)

    def _create_test_file(self, endpoint: Endpoint) -> None:
        file_path = self._get_file_path(endpoint)
        logger.info(f"Creating test file for {endpoint.id} at {file_path}")
        
        content = self._generate_file_content(endpoint)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")

    def _update_test_file(self, endpoint: Endpoint) -> None:
        # We need to find the existing file. 
        # Ideally we'd use the path from metadata, but here we calculate it deterministically.
        # If the file was moved, this might fail unless we use the metadata from the diff (Deleted/Existing).
        # For simplicity, we assume standard paths.
        file_path = self._get_file_path(endpoint)
        
        if not os.path.exists(file_path):
            logger.warning(f"File for update not found at {file_path}. Re-creating.")
            self._create_test_file(endpoint)
            return

        logger.info(f"Updating test file for {endpoint.id} at {file_path}")
        
        # Read existing content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return

        # Update metadata in-place
        new_lines = self._patch_metadata(lines, endpoint)
        
        # Write back
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
        except Exception as e:
            logger.error(f"Failed to write updated file {file_path}: {e}")

    def _delete_test_file(self, metadata: TestFileMetadata) -> None:
        # metadata.relative_path is relative to repo root
        file_path = os.path.join(self.repo_path, metadata.relative_path)
        
        if os.path.exists(file_path):
            logger.info(f"Deleting test file for {metadata.endpoint_id} at {file_path}")
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Failed to delete file {file_path}: {e}")
        else:
            logger.warning(f"File to delete not found: {file_path}")

def update_or_create_test_file(
    endpoint: Endpoint, 
    components: Dict[str, Any], 
    repo_path: str,
    base_url: Optional[str] = None,
    security_tokens: Optional[Dict[str, str]] = None,
    generate_negative: bool = True
) -> None:
    """
    Updates or creates an API test file with payloads and schema assertions.
    Preserves user code outside AUTO-GENERATED blocks.
    """
    # Deterministic Path
    test_dir = os.path.join(repo_path, "tests/endpoints")
    if not os.path.exists(test_dir):
        os.makedirs(test_dir, exist_ok=True)
    
    # Ensure client.py exists in tests root
    _ensure_client_exists(repo_path, base_url, security_tokens)
    
    safe_path = re.sub(r'[^a-zA-Z0-9]', '_', endpoint.path).strip('_')
    filename = f"{endpoint.method.lower()}_{safe_path}.py"
    file_path = os.path.join(test_dir, filename)

    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Headers
    headers = [
        f"# endpoint_id: {endpoint.id}",
        f"# last_generated: {timestamp}"
    ]
    if endpoint.request_body:
        headers.append(f"# request_schema_hash: {endpoint.request_body.hash}")
    for code, schema in endpoint.responses.items():
        headers.append(f"# response_schema_hash_{code}: {schema.hash}")
    
    # Block Content
    block_lines = []
    
    # Handle Parameters (Query/Path)
    query_params = {}
    path_replacements = {}
    for p in endpoint.parameters:
        p_name = p.get('name')
        p_in = p.get('in')
        if p_in == 'query':
            query_params[p_name] = 'test_value' # Simplistic
        elif p_in == 'path':
            path_replacements[p_name] = 'test_id'

    formatted_path = endpoint.path
    for k, v in path_replacements.items():
        formatted_path = formatted_path.replace(f"{{{k}}}", v)

    # Request Generation
    request_args = []
    if query_params:
         request_args.append(f"params={json.dumps(query_params)}")

    if endpoint.request_body:
        payload = generate_payload(endpoint.request_body, components)
        if endpoint.request_content_type == "application/json":
            request_args.append(f"json={json.dumps(payload)}")
        elif endpoint.request_content_type == "application/x-www-form-urlencoded":
            request_args.append(f"data={json.dumps(payload)}")
        elif endpoint.request_content_type == "multipart/form-data":
            request_args.append(f"files={json.dumps(payload)}") # Simplified
        else:
            request_args.append(f"json={json.dumps(payload)}")

    args_str = ", ".join(request_args)
    if args_str:
        block_lines.append(f"response = client.{endpoint.method.lower()}(f\"{formatted_path}\", {args_str})")
    else:
        block_lines.append(f"response = client.{endpoint.method.lower()}(f\"{formatted_path}\")")
    
    block_lines.append("")
    # Determine success code
    success_codes = [c for c in endpoint.responses.keys() if c.startswith('2')]
    expected_status = success_codes[0] if success_codes else "200"
    block_lines.append(f"assert response.status_code == {expected_status}")

    if expected_status in endpoint.responses:
        try:
             # Basic check if response has content
             block_lines.append("data = response.json()")
             assertions = generate_response_assertions(endpoint.responses[expected_status], components, "data")
             block_lines.extend(assertions)
        except:
             pass

    auto_block = [
        "    # --- AUTO-GENERATED START ---",
        *[f"    {l}" for l in block_lines],
        "    # --- AUTO-GENERATED END ---"
    ]

    func_name = f"test_{endpoint.method.lower()}_{safe_path}"

    # Negative Tests
    negative_blocks = []
    if generate_negative and endpoint.method.upper() in ["POST", "PUT", "PATCH"] and endpoint.request_body:
        neg_tests = generate_negative_tests(endpoint.request_body, components)
        
        # Try to find an error schema for assertions
        error_schema = endpoint.responses.get("400") or endpoint.responses.get("422") or endpoint.responses.get("default")

        for desc, neg_payload in neg_tests:
            neg_func_name = f"{func_name}_negative_{desc}"
            neg_lines = [
                f"@pytest.mark.negative",
                f"def {neg_func_name}():",
                f"    # --- AUTO-GENERATED START ---",
                f"    response = client.{endpoint.method.lower()}(f\"{formatted_path}\", json={json.dumps(neg_payload)})",
                f"    assert response.status_code in [400, 422]"
            ]
            
            if error_schema:
                try:
                    neg_lines.append("    data = response.json()")
                    neg_assertions = generate_response_assertions(error_schema, components, "data")
                    for a in neg_assertions:
                        neg_lines.append(f"    {a}")
                except:
                    pass
            
            neg_lines.append(f"    # --- AUTO-GENERATED END ---")
            neg_lines.append("")
            negative_blocks.append("\n".join(neg_lines))

    if not os.path.exists(file_path):
        # Create new file
        content = [
            *headers,
            "",
            "import pytest",
            "from ..client import client",
            "",
            f"def {func_name}():",
            *auto_block,
            "",
            *negative_blocks
        ]
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(content))
    else:
        # Update existing file
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Update Headers & ensure imports
        new_lines = []
        # Filter existing metadata
        existing_content = []
        for line in lines:
            if line.startswith("# endpoint_id:") or \
               line.startswith("# last_generated:") or \
               line.startswith("# request_schema_hash:") or \
               re.match(r"# response_schema_hash_\w+:", line):
                continue
            existing_content.append(line)
        
        # Prepend new headers
        new_lines.extend([f"{h}\n" for h in headers])
        
        # Ensure imports
        content_str = "".join(existing_content)
        if "import pytest" not in content_str:
            new_lines.append("import pytest\n")
        if "from ..client import client" not in content_str:
            new_lines.append("from ..client import client\n")
        
        # Handle the main function and its block
        start_marker = "# --- AUTO-GENERATED START ---"
        end_marker = "# --- AUTO-GENERATED END ---"
        
        final_lines = []
        final_lines.extend(new_lines)
        
        # Split existing content into functions or sections to preserve user code
        # This is tricky. For now, we update the main function's auto-block.
        # AND we manage the negative functions.
        
        in_main_block = False
        main_block_updated = False
        
        for line in existing_content:
            if f"def {func_name}():" in line:
                # We'll catch the block inside this function later
                final_lines.append(line)
            elif start_marker in line and not main_block_updated:
                # Assuming the first auto-block belongs to the main function
                final_lines.append(line)
                for bl in block_lines:
                    final_lines.append(f"    {bl}\n")
                in_main_block = True
            elif end_marker in line and in_main_block:
                final_lines.append(line)
                in_main_block = False
                main_block_updated = True
            elif not in_main_block:
                # Check if this line is part of a negative function we already have
                # If so, we'll replace its block or skip it to be recreated
                # Actually, simpler: search and replace all negative test blocks
                final_lines.append(line)

        # Append new negative tests if they don't exist
        # For simplicity in this iteration, we just append them if not present by name
        for neg_block in negative_blocks:
            neg_func_name_match = re.search(r"def (test_[^_]+_[^_]+_negative_[^\(]+)\(\):", neg_block)
            if neg_func_name_match:
                neg_func_name = neg_func_name_match.group(1)
                if neg_func_name not in "".join(final_lines):
                    final_lines.append("\n" + neg_block)
            else:
                final_lines.append("\n" + neg_block)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(final_lines)

    def _patch_metadata(self, lines: List[str], endpoint: Endpoint) -> List[str]:
        """
        Updates metadata headers in existing file content.
        Preserves other content.
        If the function body is just 'pass', it replaces it with real logic.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Pre-process lines to remove existing metadata and capture body
        filtered_lines = []
        for line in lines:
            if line.startswith("# endpoint_id:") or \
               line.startswith("# last_generated:") or \
               line.startswith("# request_schema_hash:") or \
               re.match(r"# response_schema_hash_\w+:", line):
                continue
            filtered_lines.append(line)
            
        # Ensure client import exists
        has_client_import = any("from ..client import client" in line for line in filtered_lines)
        if not has_client_import:
            # Find a good place for import (after pytest or at top)
            import_inserted = False
            for i, line in enumerate(filtered_lines):
                if line.startswith("import pytest"):
                    filtered_lines.insert(i + 1, "from ..client import client\n")
                    import_inserted = True
                    break
            if not import_inserted:
                filtered_lines.insert(0, "from ..client import client\n")

        # Construct new header
        header = []
        header.append(f"# endpoint_id: {endpoint.id}\n")
        header.append(f"# last_generated: {timestamp}\n")
        
        if endpoint.request_body:
            header.append(f"# request_schema_hash: {endpoint.request_body.hash}\n")
            
        for code, schema in endpoint.responses.items():
            header.append(f"# response_schema_hash_{code}: {schema.hash}\n")
        
        # Check if function body is just 'pass' and replace if so
        content = "".join(filtered_lines)
        func_name = self._get_function_name(endpoint)
        # Regex to find the function and its body
        # Matches: def test_foo(): followed by any comments and then 'pass' (with indentation)
        pass_pattern = rf"(def {func_name}\(\):\s+(?:#[^\n]*\s+)*)pass(\s*)$"
        
        if re.search(pass_pattern, content, re.MULTILINE):
            body_lines = self._generate_test_body(endpoint)
            replacement_body = "\n".join([f"    {l}" for l in body_lines])
            content = re.sub(pass_pattern, rf"\1{replacement_body}\2", content, flags=re.MULTILINE)
            return header + [content]

        return header + filtered_lines

def _ensure_client_exists(
    repo_path: str, 
    base_url: Optional[str] = None, 
    security_tokens: Optional[Dict[str, str]] = None
) -> None:
    """Creates a default client.py in the tests/ directory if it doesn't exist."""
    client_path = os.path.join(repo_path, "tests/client.py")
    if os.path.exists(client_path):
        return

    default_base_url = base_url or os.getenv("API_BASE_URL", "https://api.example.com")
    tokens_code = ""
    if security_tokens:
        for name, token in security_tokens.items():
            tokens_code += f"client.set_security_token(\"{name}\", \"{token}\")\n"

    content = f"""import requests
import os

class APIClient:
    \"\"\"
    A simple wrapper around requests.Session to provide a base URL 
    and common configuration for generated tests.
    Supports security schemes and different request formats.
    \"\"\"
    def __init__(self, base_url=None):
        self.session = requests.Session()
        self.base_url = base_url or os.getenv("API_BASE_URL", "{default_base_url}")
        self.security_tokens = {{}} # Map scheme name -> token

    def set_security_token(self, scheme_name: str, token: str):
        self.security_tokens[scheme_name] = token
        
    def request(self, method, path, **kwargs):
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        
        # Auto-inject security if headers aren't already set
        if "headers" not in kwargs:
            kwargs["headers"] = {{}}
        
        # Simple injection for Bearer or API Key
        for token in self.security_tokens.values():
            if token.startswith("Bearer "):
                kwargs["headers"]["Authorization"] = token
            else:
                # Assuming generic API Key if not Bearer
                kwargs["headers"]["X-API-Key"] = token

        return self.session.request(method, url, **kwargs)

    def get(self, path, **kwargs): return self.request("GET", path, **kwargs)
    def post(self, path, **kwargs): return self.request("POST", path, **kwargs)
    def put(self, path, **kwargs): return self.request("PUT", path, **kwargs)
    def delete(self, path, **kwargs): return self.request("DELETE", path, **kwargs)
    def patch(self, path, **kwargs): return self.request("PATCH", path, **kwargs)

client = APIClient()
{tokens_code}"""
    try:
        # Ensure tests dir exists
        os.makedirs(os.path.dirname(client_path), exist_ok=True)
        with open(client_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to bootstrap client.py: {e}")
