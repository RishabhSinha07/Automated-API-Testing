import os
import tempfile
import json
import logging
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .parser.openapi import load_from_file
from .state.repo_manager import read_existing_tests, TestFileMetadata
from .diff.engine import DiffEngine
from .generator.engine import update_or_create_test_file

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

class TestFileResponse(BaseModel):
    fileName: str
    endpointId: str
    action: str
    timestamp: str
    code: str

@app.post("/generate", response_model=List[TestFileResponse])
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
        
        results = []
        
        # Helper to get file info after creation/update
        def get_file_info(endpoint, action):
            # This logic mimics GenerationEngine._get_file_path
            import re
            safe_path = re.sub(r'[^a-zA-Z0-9]', '_', endpoint.path).strip('_')
            filename = f"{endpoint.method.lower()}_{safe_path}.py"
            file_path = os.path.join(request.repo_path, "tests/endpoints", filename)
            
            code = ""
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    code = f.read()
            
            from datetime import datetime
            return TestFileResponse(
                fileName=filename,
                endpointId=endpoint.id,
                action=action,
                timestamp="Just now",
                code=code
            )

        # 5. Apply changes and collect results
        # Creates
        for endpoint in diff.create:
            update_or_create_test_file(
                endpoint, 
                api_spec.components, 
                request.repo_path,
                base_url=request.server_url,
                security_tokens=request.tokens,
                generate_negative=request.generate_negative_tests
            )
            results.append(get_file_info(endpoint, "Created"))
            
        # Updates
        for eid in diff.update:
            endpoint = api_spec.endpoint_map.get(eid)
            if endpoint:
                update_or_create_test_file(
                    endpoint, 
                    api_spec.components, 
                    request.repo_path,
                    base_url=request.server_url,
                    security_tokens=request.tokens,
                    generate_negative=request.generate_negative_tests
                )
                results.append(get_file_info(endpoint, "Updated"))
                
        # Skips (optional: show them in results too)
        for eid in diff.skip:
            endpoint = api_spec.endpoint_map.get(eid)
            if endpoint:
                # We don't update file, but we can read it to show current state
                results.append(get_file_info(endpoint, "Skipped"))

        # Deletes
        for meta in diff.delete:
            # For now just note it was deleted
            results.append(TestFileResponse(
                fileName=meta.relative_path.split('/')[-1],
                endpointId=meta.endpoint_id,
                action="Deleted",
                timestamp="Just now",
                code="# This file would be deleted in a real run."
            ))

        return results

    except Exception as e:
        logging.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
