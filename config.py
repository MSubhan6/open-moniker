#!/usr/bin/env python
"""Initialize configuration files from samples.

Usage:
    python config.py          # Copy all sample configs (won't overwrite existing)
    python config.py --force  # Overwrite existing config files
"""

import argparse
import shutil
from pathlib import Path

# Config file mappings: sample -> target
CONFIG_FILES = {
    "config.sample.yaml": "config.yaml",
    "config_zmq.sample.yaml": "config_zmq.yaml",
    "sample_domains.yaml": "domains.yaml",
    "sample_catalog.yaml": "catalog.yaml",
    "sample_demo_monikers.yaml": "demo_monikers.yaml",
}


def main():
    parser = argparse.ArgumentParser(description="Initialize configuration files from samples")
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing config files"
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent.resolve()

    for sample, target in CONFIG_FILES.items():
        sample_path = script_dir / sample
        target_path = script_dir / target

        if not sample_path.exists():
            print(f"  skip: {sample} (sample not found)")
            continue

        if target_path.exists() and not args.force:
            print(f"  skip: {target} (already exists, use --force to overwrite)")
            continue

        shutil.copy(sample_path, target_path)
        action = "overwrite" if target_path.exists() else "create"
        print(f"  {action}: {target} <- {sample}")


if __name__ == "__main__":
    print("Initializing config files...")
    main()
    print("Done.")
