import os
import re
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class TestFileMetadata:
    relative_path: str
    endpoint_id: str
    request_schema_hash: Optional[str] = None
    response_schema_hashes: Optional[Dict[str, str]] = None

def _extract_metadata_from_content(content: str) -> Dict[str, Any]:
    """
    Parses the header/docstring of a test file to extract metadata.
    Expected format in docstring or comments:
    # endpoint_id: GET /users
    # request_schema_hash: abc1234
    # response_schema_hash_200: def5678
    """
    metadata = {}
    
    # Simple regex extraction for now. Can be made more robust.
    endpoint_match = re.search(r'#\s*endpoint_id:\s*(.+)', content)
    if endpoint_match:
        metadata['endpoint_id'] = endpoint_match.group(1).strip()
        
    request_hash_match = re.search(r'#\s*request_schema_hash:\s*(.+)', content)
    if request_hash_match:
        metadata['request_schema_hash'] = request_hash_match.group(1).strip()
        
    responses = {}
    for match in re.finditer(r'#\s*response_schema_hash_(\w+):\s*(.+)', content):
        code = match.group(1)
        hash_val = match.group(2).strip()
        responses[code] = hash_val
    
    if responses:
        metadata['response_schema_hashes'] = responses
        
    return metadata

def read_existing_tests(repo_path: str, test_dir_name: str = "tests") -> List[TestFileMetadata]:
    """
    Scans the repository for test files and extracts metadata.
    
    Args:
        repo_path: Absolute path to the repository root.
        test_dir_name: Directory name to search for tests (default: 'tests').
        
    Returns:
        List of TestFileMetadata sorted by relative path.
    """
    if not os.path.exists(repo_path):
        raise FileNotFoundError(f"Repository path does not exist: {repo_path}")
    if not os.path.isdir(repo_path):
        raise NotADirectoryError(f"Path is not a directory: {repo_path}")
    
    # Normalize path
    repo_path = os.path.abspath(repo_path)
    search_root = os.path.join(repo_path, test_dir_name)
    
    if not os.path.exists(search_root):
        logger.warning(f"Test directory {search_root} not found. Returning empty list.")
        return []

    discovered_files = []
    
    for root, _, files in os.walk(search_root):
        for file in files:
            if not file.endswith(".py") or file == "__init__.py":
                continue
                
            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, repo_path)
            
            logger.info(f"Discovered test file: {relative_path}")
            
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                meta_dict = _extract_metadata_from_content(content)
                
                # We require at least an endpoint_id to consider it a managed test file
                if 'endpoint_id' in meta_dict:
                    metadata = TestFileMetadata(
                        relative_path=relative_path,
                        endpoint_id=meta_dict['endpoint_id'],
                        request_schema_hash=meta_dict.get('request_schema_hash'),
                        response_schema_hashes=meta_dict.get('response_schema_hashes')
                    )
                    discovered_files.append(metadata)
                else:
                    logger.debug(f"Skipping {relative_path}: No endpoint_id metadata found.")
                    
            except Exception as e:
                logger.error(f"Failed to read/parse {relative_path}: {e}")
                # We fail loudly if we can't read a file that looks like a test? 
                # Or just log error? Requirement says "Fail loudly if the path does not exist".
                # It accepts individual file read errors or should it crash? 
                # Let's log error but valid scan implies we should probably be able to read our own files.
                # However, for robustness, one bad file shouldn't necessarily crash the whole scan unless critical.
                # I'll re-raise for now to be safe/strict as per "Fail loudly" vibe.
                raise e

    # Deterministic ordering
    discovered_files.sort(key=lambda x: x.relative_path)
    return discovered_files
