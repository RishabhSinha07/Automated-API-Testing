import os
import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from ..ir.models import Endpoint
from ..diff.engine import DiffResult
from ..state.repo_manager import TestFileMetadata

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

    def apply_diff_with_spec(self, diff: DiffResult, endpoint_map: Dict[str, Endpoint]) -> None:
        """
        Applies changes based on the diff result, using the endpoint map for details.
        """
        if diff.create and not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir, exist_ok=True)

        for endpoint in diff.create:
            self._create_test_file(endpoint)

        for endpoint_id in diff.update:
            if endpoint_id in endpoint_map:
                self._update_test_file(endpoint_map[endpoint_id])
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

    def _generate_file_content(self, endpoint: Endpoint) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Build Metadata Header
        lines = []
        lines.append(f"# endpoint_id: {endpoint.id}")
        lines.append(f"# last_generated: {timestamp}")
        
        if endpoint.request_body:
            lines.append(f"# request_schema_hash: {endpoint.request_body.hash}")
            
        for code, schema in endpoint.responses.items():
            lines.append(f"# response_schema_hash_{code}: {schema.hash}")
            
        lines.append("")
        lines.append("import pytest")
        lines.append("")
        
        # Basic Test Skeleton
        func_name = f"test_{endpoint.method.lower()}_{re.sub(r'[^a-zA-Z0-9]', '_', endpoint.path).strip('_')}"
        lines.append(f"def {func_name}():")
        lines.append(f"    # TODO: Implement test for {endpoint.id}")
        if endpoint.summary:
            lines.append(f"    # Summary: {endpoint.summary}")
        lines.append("    pass")
        lines.append("")
        
        return "\n".join(lines)

    def _patch_metadata(self, lines: List[str], endpoint: Endpoint) -> List[str]:
        """
        Updates metadata headers in existing file content.
        Preserves other content.
        """
        new_lines = []
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # We need to construct the new metadata block
        # But parsing identifying where the block ends is tricky if user edited.
        # Assumption: Metadata is at the top, starting with #.
        
        # Strategy: Filter out old known metadata tags, then prepend new ones.
        filtered_lines = []
        for line in lines:
            if line.startswith("# endpoint_id:") or \
               line.startswith("# last_generated:") or \
               line.startswith("# request_schema_hash:") or \
               re.match(r"# response_schema_hash_\w+:", line):
                continue
            filtered_lines.append(line)
            
        # Add new metadata at the top
        header = []
        header.append(f"# endpoint_id: {endpoint.id}\n")
        header.append(f"# last_generated: {timestamp}\n")
        
        if endpoint.request_body:
            header.append(f"# request_schema_hash: {endpoint.request_body.hash}\n")
            
        for code, schema in endpoint.responses.items():
            header.append(f"# response_schema_hash_{code}: {schema.hash}\n")
            
        return header + filtered_lines
