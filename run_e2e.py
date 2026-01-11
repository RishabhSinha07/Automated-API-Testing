import os
import logging
from api_test_gen.parser.openapi import load_from_file
from api_test_gen.state.repo_manager import read_existing_tests
from api_test_gen.diff.engine import DiffEngine
from api_test_gen.generator.engine import GenerationEngine

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    repo_path = os.path.abspath("dummyGitRepo")
    spec_path = "swaggerDocForTesting/petStore.json"

    logger.info("=== Starting E2E Test Run ===")

    # 1. Parse OpenAPI Spec
    logger.info(f"Loading API Spec from {spec_path}...")
    try:
        spec = load_from_file(spec_path)
    except Exception as e:
        logger.error(f"Failed to parse spec: {e}")
        return
    logger.info(f"Parsed Spec: {spec.title} v{spec.version} with {len(spec.endpoints)} endpoints.")

    # 2. Scan Existing Repo
    logger.info(f"Scanning repository at {repo_path}...")
    existing_tests = read_existing_tests(repo_path)
    logger.info(f"Found {len(existing_tests)} existing test files.")

    # 3. Compute Diff
    logger.info("Computing Diff...")
    diff_engine = DiffEngine(spec, existing_tests)
    diff = diff_engine.compute_diff()
    
    logger.info(f"Diff Result: Create={len(diff.create)}, Update={len(diff.update)}, Skip={len(diff.skip)}, Delete={len(diff.delete)}")

    # 4. Apply Changes
    if diff.create or diff.update or diff.delete:
        logger.info("Applying changes...")
        generator = GenerationEngine(repo_path)
        report = generator.run(spec, diff)
        logger.info(f"Changes applied successfully. Coverage: {report.get('coverage_percentage', 0):.2f}%")
    else:
        logger.info("No changes needed.")

    # Verification
    final_files = []
    for root, _, files in os.walk(repo_path):
        for f in files:
            if f.endswith(".py"):
                final_files.append(os.path.join(root, f))
    
    logger.info(f"Final file count in repo: {len(final_files)}")
    for f in final_files:
        logger.info(f" - {os.path.relpath(f, repo_path)}")

if __name__ == "__main__":
    main()
