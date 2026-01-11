import os
import re
import logging
import json
import shutil
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from ..ir.models import Endpoint, APISpec, SchemaRef
from ..diff.engine import DiffResult
from ..state.repo_manager import TestFileMetadata
from .payloads import generate_payload
from .assertions import generate_response_assertions
from .payloads import generate_payload
from .assertions import generate_response_assertions

logger = logging.getLogger(__name__)

class GenerationEngine:
    def __init__(self, repo_path: str, dry_run: bool = False):
        from .report_generator import ReportGenerator
        from ..negative.security_negative_tests import SecurityNegativeTests
        self.repo_path = repo_path
        self.dry_run = dry_run
        self.report_gen = ReportGenerator(repo_path)
        self.mutation_engine = None
        self.error_gen = None
        self.security_gen = SecurityNegativeTests()

    def run(self, spec: APISpec, diff: DiffResult, base_url: str = None, security_tokens: Dict[str, str] = None, generate_negative: bool = True) -> Dict[str, Any]:
        """
        Coordinates the entire generation process.
        """
        from ..negative.mutation_engine import MutationEngine
        from ..negative.error_assertion_generator import ErrorAssertionGenerator
        
        self.mutation_engine = MutationEngine(spec.components)
        self.error_gen = ErrorAssertionGenerator(spec.components)
        
        # 0. Migrate legacy tests if any
        if not self.dry_run:
            self._migrate_legacy_tests()

        # Ensure client exists
        if not self.dry_run:
            _ensure_client_exists(self.repo_path, base_url, security_tokens)

        # 1. Handle Deletions (and moves)
        for metadata in diff.delete:
            self._delete_test_file(metadata)

        # 2. Handle Creations and Updates
        all_endpoints = list(spec.endpoints)
        
        for endpoint in spec.endpoints:
            # We process all endpoints to get full report, 
            # but only write if they are in create or update.
            # Actually, standard behavior is only touch what changed.
            # But for the report, we might want to know about skipped ones too.
            # DiffResult doesn't have the Endpoint objects for updated/skipped, 
            # so we use the spec.
            
            is_new = endpoint in diff.create
            is_updated = endpoint.id in diff.update
            is_skipped = endpoint.id in diff.skip
            
            # For report generation
            pos_count = 0
            neg_count = 0
            sec_count = 0

            if is_new or is_updated:
                pos_count, neg_count, sec_count = self._process_endpoint(
                    endpoint, spec.components, base_url, security_tokens, generate_negative
                )
            elif is_skipped:
                # We should still count them for the report if we can.
                # Since we don't regenerate, we can't be 100% sure of the count without reading the file,
                # but for simplicity, let's assume 1 positive and some estimate or just count 1.
                pos_count = 1 
                # Ideally we'd scan the existing file to count tests.
            
            self.report_gen.add_endpoint_stats(endpoint.id, pos_count, neg_count, sec_count)

        if not self.dry_run:
            return self.report_gen.generate_report()
        else:
            logger.info("Dry run: Skipping report file generation.")
            return self.report_gen.stats

    def _process_endpoint(
        self, 
        endpoint: Endpoint, 
        components: Dict[str, SchemaRef], 
        base_url: str, 
        security_tokens: Dict[str, str],
        generate_negative: bool
    ) -> Tuple[int, int, int]:
        """
        Generates positive, negative, and security tests for an endpoint.
        Returns (positive_count, negative_count, security_count)
        """
        pos_count = 0
        neg_count = 0
        sec_count = 0

        # Positive Test
        if self._generate_positive_test_file(endpoint, components, base_url, security_tokens):
            pos_count = 1

        # Negative Tests
        if generate_negative:
            neg_count = self._generate_negative_test_file(endpoint, components, base_url, security_tokens)
            sec_count = self._generate_security_test_file(endpoint, components, base_url, security_tokens)

        return pos_count, neg_count, sec_count

    def _migrate_legacy_tests(self):
        legacy_dir = os.path.join(self.repo_path, "tests", "endpoints")
        positive_dir = os.path.join(self.repo_path, "tests", "positive")
        
        if os.path.exists(legacy_dir) and os.path.isdir(legacy_dir):
            logger.info(f"Migrating legacy tests from {legacy_dir} to {positive_dir}")
            os.makedirs(positive_dir, exist_ok=True)
            for filename in os.listdir(legacy_dir):
                old_path = os.path.join(legacy_dir, filename)
                new_path = os.path.join(positive_dir, filename)
                if os.path.isfile(old_path) and not os.path.exists(new_path):
                    shutil.move(old_path, new_path)
                elif os.path.isfile(old_path):
                    # Destination exists, just delete old one to be clean
                    os.remove(old_path)
            
            # Clean up empty legacy dir
            try:
                if not os.listdir(legacy_dir):
                    os.rmdir(legacy_dir)
            except Exception as e:
                logger.warning(f"Could not remove legacy directory {legacy_dir}: {e}")

    def _get_safe_filename(self, endpoint: Endpoint) -> str:
        safe_path = re.sub(r'[^a-zA-Z0-9]', '_', endpoint.path).strip('_')
        return f"{endpoint.method.lower()}_{safe_path}.py"

    def _write_file(self, folder: str, filename: str, content: str):
        if self.dry_run:
            logger.info(f"Dry run: Would write to tests/{folder}/{filename}")
            return True
        
        dir_path = os.path.join(self.repo_path, "tests", folder)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, filename)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return False

    def _generate_positive_test_file(self, endpoint: Endpoint, components: Dict[str, SchemaRef], base_url: str, security_tokens: Dict[str, str]) -> bool:
        filename = self._get_safe_filename(endpoint)
        
        # Check if file exists to preserve user code
        existing_content = self._read_existing_test("positive", filename)
        
        header = self._generate_headers(endpoint)
        body_lines = self._generate_positive_body(endpoint, components)
        
        content = self._assemble_test_file(
            endpoint, 
            "positive", 
            [("test_" + filename.replace(".py", ""), body_lines, [])], 
            header,
            existing_content
        )
        
        return self._write_file("positive", filename, content)

    def _generate_negative_test_file(self, endpoint: Endpoint, components: Dict[str, SchemaRef], base_url: str, security_tokens: Dict[str, str]) -> int:
        if not endpoint.request_body or endpoint.method.upper() not in ["POST", "PUT", "PATCH"]:
            return 0
        
        filename = self._get_safe_filename(endpoint)
        existing_content = self._read_existing_test("negative", filename)
        
        # Generate mutations
        base_payload = generate_payload(endpoint.request_body, components)
        mutations = self.mutation_engine.generate_mutations(endpoint.request_body, base_payload)
        
        if not mutations:
            return 0

        # Error schema
        error_schema = endpoint.responses.get("400") or endpoint.responses.get("422") or endpoint.responses.get("default")
        error_assertions = self.error_gen.generate_error_assertions(error_schema)

        test_definitions = []
        for desc, payload in mutations:
            func_name = f"test_{endpoint.method.lower()}_{self._get_safe_filename(endpoint).replace('.py', '')}_negative_{desc}"
            
            formatted_path = self._get_formatted_path(endpoint)
            
            body_lines = [
                f"response = client.{endpoint.method.lower()}(f\"{formatted_path}\", json={payload})",
                f"assert response.status_code in [400, 422]",
                "data = response.json()",
                *[f"{a}" for a in error_assertions]
            ]
            test_definitions.append((func_name, body_lines, ["@pytest.mark.negative"]))

        content = self._assemble_test_file(
            endpoint, 
            "negative", 
            test_definitions, 
            self._generate_headers(endpoint),
            existing_content
        )
        
        self._write_file("negative", filename, content)
        return len(mutations)

    def _generate_security_test_file(self, endpoint: Endpoint, components: Dict[str, SchemaRef], base_url: str, security_tokens: Dict[str, str]) -> int:
        if not endpoint.security:
            return 0
            
        filename = self._get_safe_filename(endpoint)
        existing_content = self._read_existing_test("security", filename)
        
        scenarios = self.security_gen.generate_security_tests(endpoint)
        if not scenarios:
            return 0

        test_definitions = []
        formatted_path = self._get_formatted_path(endpoint)
        
        # We need a basic payload if it's a POST/PUT
        payload = None
        if endpoint.request_body:
            payload = generate_payload(endpoint.request_body, components)

        for scenario in scenarios:
            func_name = f"test_{endpoint.method.lower()}_{self._get_safe_filename(endpoint).replace('.py', '')}_{scenario['name']}"
            
            # Auth override logic
            # In a real scenario, we might need to modify the client or headers.
            # Here we assume we can pass headers to the client call.
            headers_arg = ""
            if scenario['auth_override'] is None:
                # Need a way to tell the client to NOT use default auth
                headers_arg = ", headers={'Authorization': ''}" # Simplistic
            else:
                headers_arg = f", headers={{'Authorization': '{scenario['auth_override']}'}}"

            body_lines = []
            if payload:
                body_lines.append(f"response = client.{endpoint.method.lower()}(f\"{formatted_path}\", json={payload}{headers_arg})")
            else:
                body_lines.append(f"response = client.{endpoint.method.lower()}(f\"{formatted_path}\"{headers_arg})")
            
            body_lines.append(f"assert response.status_code in {scenario['expected_status']}")
            
            test_definitions.append((func_name, body_lines, ["@pytest.mark.security"]))

        content = self._assemble_test_file(
            endpoint, 
            "security", 
            test_definitions, 
            self._generate_headers(endpoint),
            existing_content
        )
        
        self._write_file("security", filename, content)
        return len(scenarios)

    def _get_formatted_path(self, endpoint: Endpoint) -> str:
        # Simplistic path parameter replacement for tests
        path = endpoint.path
        for p in endpoint.parameters:
            if p.get('in') == 'path':
                name = p.get('name')
                path = path.replace(f"{{{name}}}", "test_id")
        return path

    def _generate_headers(self, endpoint: Endpoint) -> List[str]:
        timestamp = datetime.now(timezone.utc).isoformat()
        headers = [
            f"# endpoint_id: {endpoint.id}",
            f"# last_generated: {timestamp}"
        ]
        if endpoint.request_body:
            headers.append(f"# request_schema_hash: {endpoint.request_body.hash}")
        for code, schema in endpoint.responses.items():
            headers.append(f"# response_schema_hash_{code}: {schema.hash}")
        return headers

    def _generate_positive_body(self, endpoint: Endpoint, components: Dict[str, SchemaRef]) -> List[str]:
        block_lines = []
        
        # Handle Parameters
        query_params = {}
        for p in endpoint.parameters:
            if p.get('in') == 'query':
                query_params[p.get('name')] = 'test_value'

        formatted_path = self._get_formatted_path(endpoint)
        request_args = []
        if query_params:
             request_args.append(f"params={query_params}")

        if endpoint.request_body:
            payload = generate_payload(endpoint.request_body, components)
            if endpoint.request_content_type == "application/json":
                request_args.append(f"json={payload}")
            else:
                request_args.append(f"json={payload}")

        args_str = ", ".join(request_args)
        if args_str:
            block_lines.append(f"response = client.{endpoint.method.lower()}(f\"{formatted_path}\", {args_str})")
        else:
            block_lines.append(f"response = client.{endpoint.method.lower()}(f\"{formatted_path}\")")
        
        success_codes = [c for c in endpoint.responses.keys() if c.startswith('2')]
        expected_status = success_codes[0] if success_codes else "200"
        block_lines.append(f"assert response.status_code == {expected_status}")

        if expected_status in endpoint.responses:
            try:
                 block_lines.append("data = response.json()")
                 assertions = generate_response_assertions(endpoint.responses[expected_status], components, "data")
                 block_lines.extend(assertions)
            except:
                 pass
        return block_lines

    def _read_existing_test(self, folder: str, filename: str) -> Optional[str]:
        path = os.path.join(self.repo_path, "tests", folder, filename)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return None

    def _assemble_test_file(
        self, 
        endpoint: Endpoint, 
        folder: str, 
        tests: List[Tuple[str, List[str], List[str]]], 
        headers: List[str], 
        existing_content: Optional[str]
    ) -> str:
        """
        Assembles a test file with multiple tests, preserving user code.
        tests: List of (func_name, body_lines, decorators)
        """
        start_marker = "# --- AUTO-GENERATED START ---"
        end_marker = "# --- AUTO-GENERATED END ---"
        
        if not existing_content:
            # Create new
            lines = [f"{h}\n" for h in headers]
            lines.append("\nimport pytest\n")
            lines.append("from ..client import client\n\n")
            
            for func_name, body, decorators in tests:
                for dec in decorators:
                    lines.append(f"{dec}\n")
                lines.append(f"def {func_name}():\n")
                lines.append(f"    {start_marker}\n")
                for bl in body:
                    lines.append(f"    {bl}\n")
                lines.append(f"    {end_marker}\n\n")
            return "".join(lines)
        else:
            # Update existing
            # 1. Update headers
            new_lines = [f"{h}\n" for h in headers]
            
            # 2. Keep existing imports and user code
            existing_lines = existing_content.splitlines(keepends=True)
            
            # Filter out old metadata
            filtered_existing = []
            for line in existing_lines:
                if line.startswith("# endpoint_id:") or \
                   line.startswith("# last_generated:") or \
                   line.startswith("# request_schema_hash:") or \
                   re.match(r"# response_schema_hash_\w+:", line):
                    continue
                filtered_existing.append(line)
            
            new_lines.extend(filtered_existing)
            content = "".join(new_lines)

            # 3. Update or Add tests
            for func_name, body, decorators in tests:
                auto_block = [f"    {start_marker}\n"] + [f"    {bl}\n" for bl in body] + [f"    {end_marker}\n"]
                
                # Check if function exists
                func_pattern = rf"(def {func_name}\(\):.*?\n)"
                if re.search(func_pattern, content):
                    # Replace the auto-block inside it
                    block_pattern = rf"(def {func_name}\(\):.*?\n\s+){re.escape(start_marker)}.*?{re.escape(end_marker)}"
                    if re.search(block_pattern, content, re.DOTALL):
                        content = re.sub(block_pattern, rf"\1{''.join(auto_block).strip()}", content, flags=re.DOTALL)
                    else:
                        # Function exists but no auto-block? Append it after def.
                        content = re.sub(func_pattern, rf"\1{''.join(auto_block)}", content)
                else:
                    # Append new function
                    new_func = "\n"
                    for dec in decorators:
                        new_func += f"{dec}\n"
                    new_func += f"def {func_name}():\n"
                    new_func += "".join(auto_block)
                    content += new_func
            
            return content

    def _delete_test_file(self, metadata: TestFileMetadata) -> None:
        file_path = os.path.join(self.repo_path, metadata.relative_path)
        if self.dry_run:
            logger.info(f"Dry run: Would delete {file_path}")
            return

        if os.path.exists(file_path):
            logger.info(f"Deleting test file for {metadata.endpoint_id} at {file_path}")
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Failed to delete file {file_path}: {e}")

def _ensure_client_exists(
    repo_path: str, 
    base_url: Optional[str] = None, 
    security_tokens: Optional[Dict[str, str]] = None
) -> None:
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
    def __init__(self, base_url=None):
        self.session = requests.Session()
        self.base_url = base_url or os.getenv("API_BASE_URL", "{default_base_url}")
        self.security_tokens = {{}}

    def set_security_token(self, scheme_name: str, token: str):
        self.security_tokens[scheme_name] = token
        
    def request(self, method, path, **kwargs):
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        if "headers" not in kwargs:
            kwargs["headers"] = {{}}
        for token in self.security_tokens.values():
            if token.startswith("Bearer "):
                kwargs["headers"]["Authorization"] = token
            else:
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
        os.makedirs(os.path.dirname(client_path), exist_ok=True)
        with open(client_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to bootstrap client.py: {e}")

# Maintain backward compatibility for the top-level function if needed,
# but it's better to use the engine class now.
def update_or_create_test_file(*args, **kwargs):
    # This is now handled by the engine.run method for better state management.
    # We could implement a shim if absolutely necessary.
    pass
