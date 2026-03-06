#!/usr/bin/env python
"""Start the Moniker Service.

Usage:
    python start.py                          # Monolith on port 8050
    python start.py --service management     # Management on port 8052
    python start.py --service resolver       # Resolver on port 8051
    python start.py --port 9000              # Custom port
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path

# Change to script directory so relative paths work correctly
script_dir = Path(__file__).parent.resolve()
os.chdir(script_dir)

# Add src to path
src_path = script_dir / "src"
sys.path.insert(0, str(src_path))

# Set PYTHONPATH environment variable
os.environ['PYTHONPATH'] = str(src_path)

# Service configurations
SERVICES = {
    "main": {
        "module": "moniker_svc.main:app",
        "port": 8050,
        "name": "Moniker Monolith (all endpoints)"
    },
    "management": {
        "module": "moniker_svc.management_app:app",
        "port": 8052,
        "name": "Management Service (config/dashboard only)"
    },
    "resolver": {
        "module": "moniker_svc.resolver_app:app",
        "port": 8051,
        "name": "Resolver Service (resolve/catalog only)"
    }
}


def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import fastapi
        import uvicorn
        import pydantic
        import yaml
        return True
    except ImportError as e:
        print(f"Error: Missing dependency: {e.name}")
        print("\nPlease install dependencies:")
        print("  pip install -r requirements.txt")
        return False


def check_config_files():
    """Check if configuration files exist."""
    config_file = os.environ.get('CONFIG_FILE', 'sample_config.yaml')
    catalog_file = os.environ.get('CATALOG_FILE', 'sample_catalog.yaml')

    if not Path(config_file).exists():
        print(f"Warning: Config file not found: {config_file}")
        print("Using default: sample_config.yaml")
        os.environ['CONFIG_FILE'] = 'sample_config.yaml'

    if not Path(catalog_file).exists():
        print(f"Warning: Catalog file not found: {catalog_file}")
        print("Using default: sample_catalog.yaml")
        os.environ['CATALOG_FILE'] = 'sample_catalog.yaml'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Start the Moniker Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python start.py                          # Start monolith on port 8050
  python start.py --service management     # Start management on port 8052
  python start.py --service resolver       # Start resolver on port 8051
  python start.py --port 9000              # Start monolith on custom port
        """
    )
    parser.add_argument(
        "--service", "-s",
        choices=["main", "management", "resolver"],
        default="main",
        help="Service to start (default: main)"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="Custom port (overrides default)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes"
    )

    args = parser.parse_args()

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Check config files
    check_config_files()

    # Get service config
    service_config = SERVICES[args.service]
    port = args.port if args.port else service_config["port"]
    module = service_config["module"]
    name = service_config["name"]

    print(f"Starting: {name}")
    print(f"  Host: {args.host}")
    print(f"  Port: {port}")
    print(f"  Module: {module}")
    print(f"  PYTHONPATH: {os.environ['PYTHONPATH']}")
    print(f"  Config: {os.environ.get('CONFIG_FILE', 'sample_config.yaml')}")
    print(f"  Catalog: {os.environ.get('CATALOG_FILE', 'sample_catalog.yaml')}")
    print()
    print("Access at:")
    print(f"  http://localhost:{port}/health")
    print(f"  http://localhost:{port}/docs")
    print()

    try:
        import uvicorn
        uvicorn.run(
            module,
            host=args.host,
            port=port,
            reload=args.reload
        )
    except KeyboardInterrupt:
        print("\nService stopped")
    except Exception as e:
        print(f"\nError starting service: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure you're in the project root directory")
        print("  2. Install dependencies: pip install -r requirements.txt")
        print("  3. Check that sample_config.yaml and sample_catalog.yaml exist")
        sys.exit(1)
