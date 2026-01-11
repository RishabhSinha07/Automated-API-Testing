# API Test Generator

A service that generates and updates API tests from API documentation.

## Requirements
- Python 3.11+

## Project Structure
- `src/api_test_gen/`: Main package
  - `parser/`: Parses OpenAPI specifications into IR.
  - `ir/`: Intermediate Representation (APISpec, Endpoint models).
  - `diff/`: Identifies changes between spec and local repo.
  - `generator/`: Generates test code and assertions.
  - `negative/`: Engine for mutating valid payloads into negative test cases.
  - `state/`: Scans and manages repo state (metadata).
  - `cli.py`: Command-line interface entry point.

## Features
- **Deterministic IR Parser**: Converts OpenAPI 3.x to a stable internal model.
- **Smart Diffing**: Detects Added, Updated, and Deleted endpoints with user-code preservation.
- **Automatic Negative Test Generation**: 
  - Generates mutations for missing required fields.
  - Injects wrong-type payloads and invalid enum values.
  - Tests boundary violations (min-1, max+1) and invalid formats (email, uuid).
  - Automatically asserts 400/422 status codes and validates error response structures.

## Installation
```bash
# Clone the repository
git clone <repo-url>
cd Automated-API-Testing

# Install in editable mode
pip install -e .
```

## CLI Usage

The project provides a CLI tool named `apitestgen`.

### Generate Tests
Generate or update test files from an OpenAPI spec into a local repository.

```bash
apitestgen generate --spec <path_to_spec> --repo <path_to_repo>
```

**Options:**
- `--spec`: Path to OpenAPI JSON/YAML file (Required).
- `--repo`: Path to local repository where test files are stored (Required).
- `--token`: Security tokens in `SCHEME:TOKEN` format (e.g. `Bearer:abc`).
- `--server-url`: Override the base URL for the API.
- `--negative / --no-negative`: Toggle automatic negative test generation (Default: enabled).
- `--verbose`: Enable detailed logging of the generation process.

**Example:**
```bash
apitestgen generate --spec spec.json --repo ./my-tests --verbose
```

### Inspect Diffs
Show endpoint changes that would be applied without modifying any files.

```bash
apitestgen diff --spec <path_to_spec> --repo <path_to_repo>
```

### Clean Obsolete Tests (Experimental)
Identify and remove test files that no longer correspond to endpoints in the spec.

```bash
apitestgen clean --repo <path_to_repo>
```

## Web UI

The UI for this project has been moved to its own repository: **Automated-API-Testing-UI**.

### 1. Start the Backend Server (In this repo)
The UI communicates with a FastAPI backend. Run it using:

```bash
# From the project root
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
python3 -m api_test_gen.server
```
*Port: 8000*

### 2. Start the Frontend (In the UI repo)
In the **Automated-API-Testing-UI** repository, start the dev server:

```bash
cd /Users/rishabhsinha/Documents/Projects/Automated-API-Testing-UI
npm install
npm run dev
```
*Port: 5173 (default)*

## Development
To run tests:
```bash
pytest
```

