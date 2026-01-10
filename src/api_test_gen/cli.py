import os
import sys
import click
import logging
from typing import Optional

from .parser.openapi import load_from_file
from .state.repo_manager import read_existing_tests
from .diff.engine import DiffEngine
from .generator.engine import GenerationEngine, update_or_create_test_file

# Setup simplified logging for CLI
def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    format_str = '%(levelname)s: %(message)s' if not verbose else '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=level, format=format_str)

@click.group()
def cli():
    """Automated API Test Generator CLI."""
    pass

@cli.command()
@click.option('--spec', required=True, type=click.Path(exists=True), help='Path to OpenAPI JSON/YAML file')
@click.option('--repo', required=True, type=click.Path(exists=True), help='Path to local repository where test files are stored')
@click.option('--verbose', is_flag=True, help='Print detailed logs')
def generate(spec: str, repo: str, verbose: bool):
    """Generate or update test files from an OpenAPI spec."""
    setup_logging(verbose)
    logger = logging.getLogger("apitestgen")

    repo_path = os.path.abspath(repo)
    spec_path = os.path.abspath(spec)

    # 1. Parse OpenAPI Spec
    if verbose:
        logger.info(f"Loading API Spec from {spec_path}...")
    try:
        api_spec = load_from_file(spec_path)
    except Exception as e:
        click.echo(f"Error parsing spec: {e}", err=True)
        sys.exit(1)

    if verbose:
        logger.info(f"Parsed Spec: {api_spec.title} v{api_spec.version} with {len(api_spec.endpoints)} endpoints.")

    # 2. Scan Existing Repo
    if verbose:
        logger.info(f"Scanning repository at {repo_path}...")
    try:
        existing_tests = read_existing_tests(repo_path)
    except Exception as e:
        click.echo(f"Error reading repository state: {e}", err=True)
        sys.exit(2)

    if verbose:
        logger.info(f"Found {len(existing_tests)} existing test files.")

    # 3. Compute Diff
    if verbose:
        logger.info("Computing diff...")
    diff_engine = DiffEngine(api_spec, existing_tests)
    diff = diff_engine.compute_diff()

    # 4. Generate/Update files
    generator = GenerationEngine(repo_path)
    
    try:
        # Create
        for endpoint in diff.create:
            if verbose:
                logger.info(f"Creating: {endpoint.method} {endpoint.path} ({endpoint.id})")
            update_or_create_test_file(endpoint, api_spec.components, repo_path)
            
        # Update
        for endpoint_id in diff.update:
            endpoint = api_spec.endpoint_map.get(endpoint_id)
            if endpoint:
                if verbose:
                    logger.info(f"Updating: {endpoint.method} {endpoint.path} ({endpoint.id})")
                update_or_create_test_file(endpoint, api_spec.components, repo_path)
            elif verbose:
                logger.warning(f"Endpoint {endpoint_id} marked for update but not found in spec.")

        # Skip
        if verbose:
            for endpoint_id in diff.skip:
                endpoint = api_spec.endpoint_map.get(endpoint_id)
                status = f"{endpoint.method} {endpoint.path}" if endpoint else endpoint_id
                logger.info(f"Skipping (unchanged): {status}")

        # Delete
        for metadata in diff.delete:
            if verbose:
                logger.info(f"Deleting obsolete: {metadata.relative_path} ({metadata.endpoint_id})")
            # GenerationEngine has a private delete method, but we can call it or implement here
            generator._delete_test_file(metadata)

    except Exception as e:
        click.echo(f"Error writing files: {e}", err=True)
        sys.exit(2)

    # 5. Output summary
    click.echo("\nGeneration Summary:")
    click.echo(f"  Created: {len(diff.create)} files")
    click.echo(f"  Updated: {len(diff.update)} files")
    click.echo(f"  Skipped: {len(diff.skip)} files")
    if diff.delete:
        click.echo(f"  Deleted: {len(diff.delete)} files")

@cli.command()
@click.option('--spec', required=True, type=click.Path(exists=True))
@click.option('--repo', required=True, type=click.Path(exists=True))
def diff(spec: str, repo: str):
    """Show endpoints that would be created/updated/skipped."""
    api_spec = load_from_file(spec)
    existing_tests = read_existing_tests(repo)
    diff_engine = DiffEngine(api_spec, existing_tests)
    diff_res = diff_engine.compute_diff()
    
    click.echo("Diff Result:")
    click.echo(f"  To Create: {len(diff_res.create)}")
    for e in diff_res.create:
        click.echo(f"    + {e.method} {e.path}")
    
    click.echo(f"  To Update: {len(diff_res.update)}")
    for eid in diff_res.update:
        click.echo(f"    ~ {eid}")
        
    click.echo(f"  To Skip: {len(diff_res.skip)}")
    
    click.echo(f"  To Delete: {len(diff_res.delete)}")
    for m in diff_res.delete:
        click.echo(f"    - {m.relative_path}")

@cli.command()
@click.option('--repo', required=True, type=click.Path(exists=True))
@click.option('--dry-run', is_flag=True)
def clean(repo: str, dry_run: bool):
    """Remove obsolete generated tests."""
    # Current implementation of clean would need a spec to know what's obsolete,
    # or it could just clean everything in tests/endpoints that's not in the spec.
    # For now, this is a placeholder.
    click.echo("Clean command is not fully implemented yet.")

def main():
    cli()

if __name__ == "__main__":
    main()
