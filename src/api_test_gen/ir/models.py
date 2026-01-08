import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Union

# Helper for deterministic hashing
def _deterministic_hash(data: Any) -> str:
    """
    Computes a deterministic SHA256 hash of a dictionary or list structure.
    Recursively sorts dictionary keys to ensure consistency.
    """
    def _sort_any(val: Any) -> Any:
        if isinstance(val, dict):
            return {k: _sort_any(v) for k, v in sorted(val.items())}
        if isinstance(val, list):
            # We can't strictly sort lists unless order doesn't matter, 
            # but for schema hashing (e.g. enums), order might matter.
            # If order matters, leave it. If it considers set-semantics, sort.
            # Assuming standard JSON-like structure where list order corresponds to definition order.
            return [_sort_any(v) for v in val]
        return val

    # We use json.dumps with sort_keys to ensure dictionary key order is deterministic
    json_bytes = json.dumps(_sort_any(data), sort_keys=True, ensure_ascii=True).encode('utf-8')
    return hashlib.sha256(json_bytes).hexdigest()


@dataclass(frozen=True)
class SchemaRef:
    """
    Represents a reference to a named schema, or an inline schema definition.
    This corresponds roughly to a JSON Schema object or a $ref.
    """
    # If ref_name is present, it's a reference to a schema in components
    ref_name: Optional[str] = None
    
    # Standard JSON Schema fields
    type: Optional[str] = None
    properties: Optional[Dict[str, 'SchemaRef']] = None
    items: Optional['SchemaRef'] = None
    required: Optional[Tuple[str, ...]] = None # Tuple for immutability
    nullable: bool = False
    enum: Optional[Tuple[str, ...]] = None # Tuple for immutability
    
    # Additional raw schema data for full fidelity if needed
    extra: Optional[Dict[str, Any]] = field(
        default=None,
        compare=False,
        hash=False,
        repr=False
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to directory for hashing."""
        d: Dict[str, Any] = {}
        if self.ref_name:
            d['$ref'] = self.ref_name
        if self.type:
            d['type'] = self.type
        if self.properties:
            d['properties'] = {k: v.to_dict() for k, v in self.properties.items()}
        if self.items:
            d['items'] = self.items.to_dict()
        if self.required:
            d['required'] = sorted(list(self.required))
        if self.nullable:
            d['nullable'] = True
        if self.enum:
            d['enum'] = self.enum
        # extra is excluded from hashing/identity to avoid ambiguity with compare=False
        return d

    @property
    def hash(self) -> str:
        """Deterministic hash of the schema definition."""
        return _deterministic_hash(self.to_dict())


@dataclass(frozen=True)
class Endpoint:
    """
    Represents a single API endpoint (Method + Path).
    """
    method: str
    path: str
    summary: Optional[str] = None
    description: Optional[str] = None
    
    # Request details
    parameters: Tuple[Dict[str, Any], ...] = field(default_factory=tuple) # Query/Path/Header params
    request_body: Optional[SchemaRef] = None
    
    # Responses: Status Code -> Schema
    responses: Dict[str, SchemaRef] = field(default_factory=dict)  # status_code as string ("200", "default")
    
    @property
    def id(self) -> str:
        """Deterministic Endpoint ID: METHOD PATH"""
        return f"{self.method.upper()} {self.path}"


@dataclass(frozen=True)
class APISpec:
    """
    Top-level container for the Canonical API IR.
    """
    title: str
    version: str
    endpoints: Tuple[Endpoint, ...]
    
    # Shared schemas (components/schemas)
    components: Dict[str, SchemaRef] = field(default_factory=dict)
    
    @property
    def endpoint_map(self) -> Dict[str, Endpoint]:
        """Map of Endpoint ID -> Endpoint"""
        return {ep.id: ep for ep in self.endpoints}
