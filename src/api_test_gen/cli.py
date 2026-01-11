import os
import sys
import click
import logging
import json
from typing import Optional

from .parser.openapi import load_from_file
from .state.repo_manager import read_existing_tests
from .diff.engine import DiffEngine
from .generator.engine import GenerationEngine
from .generator.report_generator import ReportGenerator

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
@click.option('--token', multiple=True, help='Security tokens in SCHEME:TOKEN format (e.g. Bearer:my_token)')
@click.option('--server-url', help='Override the base URL for the API')
@click.option('--negative/--no-negative', default=True, help='Automatically generate negative test cases')
@click.option('--dry-run', is_flag=True, help='Simulate actions without writing files')
@click.option('--verbose', is_flag=True, help='Print detailed logs')
def generate(spec: str, repo: str, token: tuple, server_url: Optional[str], negative: bool, dry_run: bool, verbose: bool):
    """Generate or update test files from an OpenAPI spec."""
    setup_logging(verbose)
    logger = logging.getLogger("apitestgen")

    repo_path = os.path.abspath(repo)
    spec_path = os.path.abspath(spec)

    # 1. Parse OpenAPI Spec
    try:
        api_spec = load_from_file(spec_path)
    except Exception as e:
        click.echo(f"Error parsing spec: {e}", err=True)
        sys.exit(1)

    # 2. Scan Existing Repo
    try:
        existing_tests = read_existing_tests(repo_path)
    except Exception as e:
        click.echo(f"Error reading repository state: {e}", err=True)
        sys.exit(2)

    # Handle tokens
    tokens_dict = {}
    for t in token:
        if ':' in t:
            scheme, val = t.split(':', 1)
            tokens_dict[scheme] = val
        else:
            tokens_dict['default'] = t

    # Resolve Server URL
    base_url = server_url
    if not base_url and api_spec.servers:
        base_url = api_spec.servers[0].get('url')

    # 3. Compute Diff
    diff_engine = DiffEngine(api_spec, existing_tests)
    diff = diff_engine.compute_diff()

    # 4. Generate/Update files
    engine = GenerationEngine(repo_path, dry_run=dry_run)
    
    try:
        report = engine.run(
            api_spec, 
            diff, 
            base_url=base_url, 
            security_tokens=tokens_dict, 
            generate_negative=negative
        )
        
        # 5. Output summary
        click.echo("\nGeneration Summary:")
        if dry_run:
            click.echo("  [DRY RUN] No files were actually written.")
        click.echo(f"  Total Endpoints: {report.get('total_endpoints', 0)}")
        click.echo(f"  Positive Tests: {report.get('positive_tests_count', 0)}")
        click.echo(f"  Negative Tests: {report.get('negative_tests_count', 0)}")
        click.echo(f"  Security Tests: {report.get('security_tests_count', 0)}")
        click.echo(f"  Coverage: {report.get('coverage_percentage', 0.0):.2f}%")
        
        if not dry_run:
            click.echo(f"\nReport saved to {os.path.join(repo_path, 'tests/report.json')}")

    except Exception as e:
        logger.exception("Generation failed")
        click.echo(f"Error during generation: {e}", err=True)
        sys.exit(2)

@cli.command()
@click.option('--repo', required=True, type=click.Path(exists=True), help='Path to local repository')
def report(repo: str):
    """Display the latest generation report."""
    repo_path = os.path.abspath(repo)
    report_data = ReportGenerator.get_report(repo_path)
    if not report_data:
        click.echo("No report found. Run 'generate' first.")
        return

    click.echo(f"API Test Generation Report")
    click.echo(f"==========================")
    click.echo(f"Total Endpoints: {report_data['total_endpoints']}")
    click.echo(f"Positive Tests:  {report_data['positive_tests_count']}")
    click.echo(f"Negative Tests:  {report_data['negative_tests_count']}")
    click.echo(f"Security Tests:  {report_data['security_tests_count']}")
    click.echo(f"Overall Coverage: {report_data['coverage_percentage']:.2f}%")
    click.echo(f"\nEndpoint Details:")
    for ep in report_data['endpoints']:
        click.echo(f"  {ep['id']}: Pos={ep['positive']}, Neg={ep['negative']}, Sec={ep['security']}")

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
    click.echo("Clean command is not fully implemented yet.")

def main():
    cli()

if __name__ == "__main__":
    main()
