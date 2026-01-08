# Project Implementation Summary

This document outlines the components implemented for the **Automated API Testing** service.

## 1. Project Skeleton
- Established a standard Python project structure using `src/` layout.
- Configured `pyproject.toml` with minimal dependencies (`pyyaml` for parsing).
- Set up directories for `parser`, `ir`, `diff`, `generator`, `updater`, `state`, and `api`.

## 2. Canonical API Internal Representation (IR)
**Location:** `src/api_test_gen/ir/models.py`

Defines the core data structures used to represent the API in a consistent, immutable format.
- **Components**:
  - `APISpec`: Top-level container.
  - `Endpoint`: Represents a unique operation (`METHOD PATH`), containing request/response definitions.
  - `SchemaRef`: detailed schema definition with support for `properties`, `items`, `enum`, etc.
- **Features**:
  - **Deterministic Hashing**: Custom hashing algorithm ensures schemas are compared by value/structure, ignoring ordering differences in JSON.
  - **Immutability**: Uses frozen dataclasses to prevent accidental mutation during processing.

## 3. OpenAPI Parser
**Location:** `src/api_test_gen/parser/openapi.py`

Converts OpenAPI v3 JSON/YAML specifications into the Canonical IR.
- **Features**:
  - Validates OpenAPI version (3.x only).
  - extracting `paths` into `Endpoint` objects.
  - Resolves internal `$ref` to `components/schemas`.
  - Normalizes HTTP methods to uppercase.
  - Enforces `application/json` constraints (fails loudly on XML).
  - Handles empty responses (e.g., 204) via explicit metadata tags.

## 4. Repository State Manager
**Location:** `src/api_test_gen/state/repo_manager.py`

Scans the local filesystem to understand the current state of generated tests.
- **Features**:
  - **Metadata Extraction**: Reads header comments in test files (e.g., `# endpoint_id: GET /users`, `# request_schema_hash: ...`).
  - **State Loading**: Returns a structured list of `TestFileMetadata`.
  - **Robustness**: Handles missing directories and validates file paths.

## 5. Diff Engine
**Location:** `src/api_test_gen/diff/engine.py`

Compares the new IR (from Parser) against the existing Repository State.
- **Logic**:
  - **Create**: Endpoint exists in IR but not in Repo.
  - **Update**: Endpoint in both, but Schema Hashes (request or response) differ.
  - **Skip**: Hashes match exactly.
  - **Delete**: Endpoint in Repo but not in IR.
- **Output**: A `DiffResult` object categorized by action type.

## 6. Generation Engine
**Location:** `src/api_test_gen/generator/engine.py`

Executes the changes determined by the Diff Engine.
- **Features**:
  - **Creation**: Generates new Python test files with deterministic filenames (`get_users.py`) and a standard template.
  - **Update**: Patches only the metadata headers in existing files to reflect new schema hashes/timestamps, **preserving** user-written test logic.
  - **Deletion**: Removes obsolete test files.
  - **Metadata**: Embeds `last_generated` timestamp and Schema Hashes directly into file comments for state tracking.

## 7. Testing
Comprehensive unit tests provided for all modules in `tests/`:
- `test_parser.py`: Validates parsing logic and error handling.
- `test_repo_manager.py`: Verifies file scanning and metadata parsing.
- `test_diff.py`: Checks all diff scenarios (create/update/skip/delete).
- `test_generation.py`: Ensures files are created and updated correctly without dataloss.

## 8. E2E Verification
**Location:** `run_e2e.py`
A full end-to-end simulation was performed using a dummy OpenAPI spec and a local git repo:
- **Scenario**:
  - Input: `dummy_api.json` with 2 endpoints (`GET /users`, `POST /users`).
  - Repo: `dummyGitRepo` (initially empty).
- **Process**:
  - Parser loaded spec correctly.
  - Repo Manager identified 0 existing tests.
  - Diff Engine correctly flagged 2 endpoints for creation.
  - Generation Engine created `tests/endpoints/get_users.py` and `post_users.py`.
- **Result**: Validated that the full pipeline from JSON spec to Python test files works as expected.
