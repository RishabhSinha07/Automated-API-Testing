import os
import tempfile
import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import re
from .parser.openapi import load_from_file
from .state.repo_manager import read_existing_tests, TestFileMetadata
from .diff.engine import DiffEngine
from .generator.engine import GenerationEngine

app = FastAPI(title="API TestGen Backend")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/open-picker")
async def open_native_picker():
    """Opens a native macOS folder picker and returns the absolute path."""
    import subprocess
    try:
        # Use osascript to open a native macOS folder selection dialog
        script = 'POSIX path of (choose folder with prompt "Select Test Repository:")'
        process = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            # User likely cancelled
            return {"path": None}
            
        selected_path = stdout.decode('utf-8').strip()
        return {"path": selected_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class GenerateRequest(BaseModel):
    spec_content: str
    repo_path: str
    tokens: Optional[Dict[str, str]] = None # { "scheme": "token" }
    server_url: Optional[str] = None
    generate_negative_tests: bool = True
    dry_run: bool = False

class TestFileResponse(BaseModel):
    fileName: str
    endpointId: str
    action: str
    timestamp: str
    code: str
    testType: str # "positive", "negative", "security"

@app.post("/generate", response_model=Dict[str, Any])
async def generate_tests(request: GenerateRequest):
    # 1. Save spec content to a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
        tmp.write(request.spec_content)
        tmp_path = tmp.name

    try:
        # 2. Load Spec
        api_spec = load_from_file(tmp_path)
        
        # 3. Read existing tests
        if not os.path.exists(request.repo_path):
            os.makedirs(request.repo_path, exist_ok=True)
            
        existing_tests = read_existing_tests(request.repo_path)
        
        # 4. Compute Diff
        diff_engine = DiffEngine(api_spec, existing_tests)
        diff = diff_engine.compute_diff()
        
        # 5. Initialize Engine
        engine = GenerationEngine(request.repo_path, dry_run=request.dry_run)
        
        # Helper to get file info after creation/update
        def get_file_info(endpoint, action, test_type="positive"):
            safe_path = re.sub(r'[^a-zA-Z0-9]', '_', endpoint.path).strip('_')
            filename = f"{endpoint.method.lower()}_{safe_path}.py"
            file_path = os.path.join(request.repo_path, "tests", test_type, filename)
            
            code = ""
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    code = f.read()
            elif request.dry_run:
                code = f"# [Dry Run] This file would be generated in tests/{test_type}/{filename}"
            
            return TestFileResponse(
                fileName=filename,
                endpointId=endpoint.id,
                action=action,
                timestamp="Just now",
                code=code,
                testType=test_type
            )

        # 6. Run Engine
        report = engine.run(
            api_spec, 
            diff, 
            base_url=request.server_url, 
            security_tokens=request.tokens, 
            generate_negative=request.generate_negative_tests
        )

        results = []
        for endpoint in api_spec.endpoints:
            # We want to show results for endpoints that were touched
            is_new = endpoint in diff.create
            is_updated = endpoint.id in diff.update
            is_skipped = endpoint.id in diff.skip
            
            action = "Skipped"
            if is_new: action = "Created"
            if is_updated: action = "Updated"
            
            # Add positive
            results.append(get_file_info(endpoint, action, "positive"))
            
            # Add negative if they exist
            if request.generate_negative_tests:
                # Check if file exists (or would exist)
                safe_path = re.sub(r'[^a-zA-Z0-9]', '_', endpoint.path).strip('_')
                neg_filename = f"{endpoint.method.lower()}_{safe_path}.py"
                
                if os.path.exists(os.path.join(request.repo_path, "tests/negative", neg_filename)) or is_new or is_updated or request.dry_run:
                    results.append(get_file_info(endpoint, action, "negative"))
                
                if os.path.exists(os.path.join(request.repo_path, "tests/security", neg_filename)) or is_new or is_updated or request.dry_run:
                    results.append(get_file_info(endpoint, action, "security"))

        for meta in diff.delete:
            results.append(TestFileResponse(
                fileName=meta.relative_path.split('/')[-1],
                endpointId=meta.endpoint_id,
                action="Deleted",
                timestamp="Just now",
                code="",
                testType="positive" # Deletes usually happen for positive files
            ))

        return {
            "files": results,
            "report": report
        }

    except Exception as e:
        logging.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
