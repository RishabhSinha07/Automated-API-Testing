# API Test Generator

A service that generates and updates API tests from API documentation.

## Requirements
- Python 3.11

## Project Structure
- `src/api_test_gen/`: Main package
  - `parser/`: Parses API documentation (e.g., OpenAPI, GraphQL).
  - `ir/`: Intermediate Representation of the API.
  - `diff/`: Identifies changes between different versions of API documentation.
  - `generator/`: Generates test cases from the IR.
  - `updater/`: Updates existing tests based on diffs.
  - `state/`: Manages the state of generated tests and documentation versions.
  - `api/`: Public API/CLI for the service.

## Installation
```bash
pip install -e .
```