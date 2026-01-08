from typing import List, Dict, Any, Set
from dataclasses import dataclass, field

from ..ir.models import APISpec, Endpoint
from ..state.repo_manager import TestFileMetadata

@dataclass
class DiffResult:
    create: List[Endpoint] = field(default_factory=list)
    update: List[str] = field(default_factory=list) # Endpoint IDs
    skip: List[str] = field(default_factory=list) # Endpoint IDs
    delete: List[TestFileMetadata] = field(default_factory=list)

class DiffEngine:
    def __init__(self, spec: APISpec, existing_tests: List[TestFileMetadata]):
        self.spec = spec
        self.existing_tests = existing_tests
        
    def compute_diff(self) -> DiffResult:
        result = DiffResult()
        
        # Map existing tests by endpoint_id for quick lookup
        existing_map: Dict[str, TestFileMetadata] = {
            t.endpoint_id: t for t in self.existing_tests
        }
        
        # Track seen endpoints to identify deletes
        processed_endpoint_ids: Set[str] = set()
        
        for endpoint in self.spec.endpoints:
            eid = endpoint.id
            processed_endpoint_ids.add(eid)
            
            if eid not in existing_map:
                # New endpoint
                result.create.append(endpoint)
            else:
                # Existing endpoint, check for changes
                existing = existing_map[eid]
                if self._has_changed(endpoint, existing):
                    result.update.append(eid)
                else:
                    result.skip.append(eid)
                    
        # Check for deleted endpoints (in existing but not in new spec)
        for eid, meta in existing_map.items():
            if eid not in processed_endpoint_ids:
                result.delete.append(meta)
                
        return result

    def _has_changed(self, endpoint: Endpoint, existing: TestFileMetadata) -> bool:
        """
        Determines if the schema has changed for a given endpoint.
        """
        # 1. Compare Request Body Schema Hash
        current_req_hash = endpoint.request_body.hash if endpoint.request_body else None
        
        # In repo_manager, we store None as None.
        # But if the file has explicit "None" string or missing, we need to be careful.
        # Assuming existing.request_schema_hash is accurate.
        # Note: if existing is None and current is None, they match.
        # If one is None and other is not, they differ.
        if current_req_hash != existing.request_schema_hash:
            return True
            
        # 2. Compare Response Schema Hashes
        # Existing might store a dict of code -> hash
        existing_resps = existing.response_schema_hashes or {}
        
        # Current responses
        curr_resps = endpoint.responses
        
        # Check keys match (set of status codes)
        if set(existing_resps.keys()) != set(curr_resps.keys()):
            return True
            
        # Check hash values
        for code, schema_ref in curr_resps.items():
            if schema_ref.hash != existing_resps.get(code):
                return True
                
        return False
