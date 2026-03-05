#!/usr/bin/env python3
"""
Local Development Bootstrap for Open Moniker

Manages side-by-side dev/UAT environments for local development.

Usage:
    python bootstrap.py dev          # Start dev environment
    python bootstrap.py uat          # Start UAT environment
    python bootstrap.py both         # Start dev and UAT side-by-side
    python bootstrap.py stop dev     # Stop dev environment
    python bootstrap.py stop uat     # Stop UAT environment
    python bootstrap.py stop all     # Stop all environments
    python bootstrap.py status       # Show status of all environments
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
JAVA_RESOLVER = PROJECT_ROOT / "resolver-java"
PYTHON_SRC = PROJECT_ROOT / "src"

# Environment configurations
ENVIRONMENTS = {
    "dev": {
        "java_port": 8054,
        "python_port": 8052,
        "db_path": "dev/telemetry.db",
        "config_dir": "dev",
        "resolver_name": "local-dev",
    },
    "uat": {
        "java_port": 9054,
        "python_port": 9052,
        "db_path": "uat/telemetry.db",
        "config_dir": "uat",
        "resolver_name": "local-uat",
    },
}

# PID file directory
PID_DIR = SCRIPT_DIR / ".pids"


class Environment:
    """Manages a single environment (dev or uat)."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.config_dir = SCRIPT_DIR / config["config_dir"]
        self.db_path = SCRIPT_DIR / config["db_path"]
        self.java_pid_file = PID_DIR / f"{name}-java.pid"
        self.python_pid_file = PID_DIR / f"{name}-python.pid"

    def setup(self):
        """Create directory structure and config files."""
        print(f"📁 Setting up {self.name} environment...")

        # Create directories
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        PID_DIR.mkdir(parents=True, exist_ok=True)

        # Copy config files if they don't exist
        self._create_config_if_missing("config.yaml")
        self._create_config_if_missing("catalog.yaml")

        print(f"✅ {self.name.upper()} environment ready")
        print(f"   Config dir: {self.config_dir}")
        print(f"   DB path: {self.db_path}")

    def _create_config_if_missing(self, filename: str):
        """Create config file from sample if it doesn't exist."""
        dest_file = self.config_dir / filename
        if dest_file.exists():
            return

        # Look for sample file
        sample_file = PROJECT_ROOT / f"sample_{filename}"
        if sample_file.exists():
            print(f"   Creating {filename} from sample...")
            shutil.copy(sample_file, dest_file)
        else:
            # Look for existing config in project root
            source_file = PROJECT_ROOT / filename
            if source_file.exists():
                print(f"   Copying {filename} from project root...")
                shutil.copy(source_file, dest_file)
            else:
                print(f"   ⚠️  Warning: No {filename} found, skipping...")

    def start(self):
        """Start Java resolver and Python admin for this environment."""
        print(f"\n🚀 Starting {self.name.upper()} environment...")

        # Check if already running
        if self.is_running():
            print(f"⚠️  {self.name.upper()} is already running")
            return False

        # Setup first
        self.setup()

        # Start Java resolver
        print(f"   Starting Java resolver on port {self.config['java_port']}...")
        java_success = self._start_java()

        # Start Python admin
        print(f"   Starting Python admin on port {self.config['python_port']}...")
        python_success = self._start_python()

        if java_success and python_success:
            print(f"✅ {self.name.upper()} environment started successfully")
            print(f"   Java resolver: http://localhost:{self.config['java_port']}/health")
            print(f"   Python admin:  http://localhost:{self.config['python_port']}/health")
            print(f"   Dashboard:     http://localhost:{self.config['python_port']}/dashboard")
            return True
        else:
            print(f"❌ Failed to start {self.name.upper()} environment")
            self.stop()
            return False

    def _start_java(self) -> bool:
        """Start Java resolver."""
        try:
            # Build if JAR doesn't exist
            jar_file = JAVA_RESOLVER / "target" / "resolver-java-0.1.0.jar"
            if not jar_file.exists():
                print("   Building Java resolver...")
                result = subprocess.run(
                    ["mvn", "clean", "package", "-DskipTests"],
                    cwd=JAVA_RESOLVER,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    print(f"   ❌ Maven build failed: {result.stderr}")
                    return False

            # Prepare environment variables
            env = os.environ.copy()
            env.update({
                "PORT": str(self.config["java_port"]),
                "CONFIG_FILE": str(self.config_dir / "config.yaml"),
                "CATALOG_FILE": str(self.config_dir / "catalog.yaml"),
                "TELEMETRY_ENABLED": "true",
                "TELEMETRY_SINK_TYPE": "sqlite",
                "TELEMETRY_DB_PATH": str(self.db_path),
                "RESOLVER_NAME": self.config["resolver_name"],
                "AWS_REGION": "local",
                "AWS_AZ": "local",
            })

            # Start Java process with system properties
            log_file = SCRIPT_DIR / f"{self.name}-java.log"
            with open(log_file, "w") as log:
                process = subprocess.Popen(
                    [
                        "java",
                        f"-Dmoniker.telemetry.enabled=true",
                        f"-Dmoniker.telemetry.sink-type=sqlite",
                        f"-Dmoniker.telemetry.sink-config.db-path={self.db_path}",
                        f"-Dmoniker.resolver-name={self.config['resolver_name']}",
                        f"-Dmoniker.region=local",
                        f"-Dmoniker.az=local",
                        "-jar",
                        str(jar_file),
                    ],
                    cwd=JAVA_RESOLVER,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )

            # Save PID
            self.java_pid_file.write_text(str(process.pid))

            # Wait for startup
            if self._wait_for_health(self.config["java_port"], timeout=30):
                print(f"   ✅ Java resolver started (PID {process.pid})")
                return True
            else:
                print(f"   ❌ Java resolver failed to start (check {log_file})")
                return False

        except Exception as e:
            print(f"   ❌ Error starting Java resolver: {e}")
            return False

    def _start_python(self) -> bool:
        """Start Python admin service."""
        try:
            # Prepare environment variables
            env = os.environ.copy()
            env.update({
                "PYTHONPATH": str(PYTHON_SRC),
                "PORT": str(self.config["python_port"]),
                "CONFIG_FILE": str(self.config_dir / "config.yaml"),
                "CATALOG_FILE": str(self.config_dir / "catalog.yaml"),
                "TELEMETRY_DB_TYPE": "sqlite",
                "TELEMETRY_DB_PATH": str(self.db_path),
            })

            # Start Python process
            log_file = SCRIPT_DIR / f"{self.name}-python.log"
            with open(log_file, "w") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "moniker_svc.management_app:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        str(self.config["python_port"]),
                    ],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )

            # Save PID
            self.python_pid_file.write_text(str(process.pid))

            # Wait for startup
            if self._wait_for_health(self.config["python_port"], timeout=30):
                print(f"   ✅ Python admin started (PID {process.pid})")
                return True
            else:
                print(f"   ❌ Python admin failed to start (check {log_file})")
                return False

        except Exception as e:
            print(f"   ❌ Error starting Python admin: {e}")
            return False

    def _wait_for_health(self, port: int, timeout: int = 30) -> bool:
        """Wait for health endpoint to respond."""
        import urllib.request

        start = time.time()
        while time.time() - start < timeout:
            try:
                with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1) as response:
                    if response.status == 200:
                        return True
            except:
                pass
            time.sleep(0.5)

        return False

    def stop(self):
        """Stop Java and Python services."""
        print(f"\n🛑 Stopping {self.name.upper()} environment...")

        stopped_any = False

        # Stop Java
        if self.java_pid_file.exists():
            pid = int(self.java_pid_file.read_text())
            if self._kill_process(pid):
                print(f"   ✅ Stopped Java resolver (PID {pid})")
                stopped_any = True
            self.java_pid_file.unlink()

        # Stop Python
        if self.python_pid_file.exists():
            pid = int(self.python_pid_file.read_text())
            if self._kill_process(pid):
                print(f"   ✅ Stopped Python admin (PID {pid})")
                stopped_any = True
            self.python_pid_file.unlink()

        if not stopped_any:
            print(f"   ℹ️  {self.name.upper()} was not running")

    def _kill_process(self, pid: int) -> bool:
        """Kill a process by PID."""
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)

            # Check if still running
            try:
                os.kill(pid, 0)
                # Still running, force kill
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
            except ProcessLookupError:
                pass

            return True

        except ProcessLookupError:
            return False
        except Exception as e:
            print(f"   ⚠️  Error killing process {pid}: {e}")
            return False

    def is_running(self) -> bool:
        """Check if environment is running."""
        java_running = self._is_process_running(self.java_pid_file)
        python_running = self._is_process_running(self.python_pid_file)
        return java_running or python_running

    def _is_process_running(self, pid_file: Path) -> bool:
        """Check if process from PID file is running."""
        if not pid_file.exists():
            return False

        try:
            pid = int(pid_file.read_text())
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError):
            return False

    def status(self) -> Dict[str, any]:
        """Get environment status."""
        java_running = self._is_process_running(self.java_pid_file)
        python_running = self._is_process_running(self.python_pid_file)

        return {
            "name": self.name,
            "running": java_running or python_running,
            "java": {
                "running": java_running,
                "port": self.config["java_port"],
                "pid": int(self.java_pid_file.read_text()) if self.java_pid_file.exists() else None,
            },
            "python": {
                "running": python_running,
                "port": self.config["python_port"],
                "pid": int(self.python_pid_file.read_text()) if self.python_pid_file.exists() else None,
            },
        }


def main():
    parser = argparse.ArgumentParser(
        description="Local development bootstrap for Open Moniker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        choices=["dev", "uat", "both", "stop", "status"],
        help="Command to execute",
    )
    parser.add_argument(
        "target",
        nargs="?",
        choices=["dev", "uat", "all"],
        help="Target environment (for stop command)",
    )

    args = parser.parse_args()

    # Create environment instances
    envs = {name: Environment(name, config) for name, config in ENVIRONMENTS.items()}

    if args.command == "dev":
        envs["dev"].start()

    elif args.command == "uat":
        envs["uat"].start()

    elif args.command == "both":
        envs["dev"].start()
        envs["uat"].start()

    elif args.command == "stop":
        if args.target == "dev":
            envs["dev"].stop()
        elif args.target == "uat":
            envs["uat"].stop()
        elif args.target == "all":
            envs["dev"].stop()
            envs["uat"].stop()
        else:
            print("❌ Please specify target: dev, uat, or all")
            sys.exit(1)

    elif args.command == "status":
        print("\n📊 Environment Status:\n")
        for name, env in envs.items():
            status = env.status()
            running_indicator = "🟢" if status["running"] else "⚪"

            print(f"{running_indicator} {name.upper()}")
            print(f"   Java Resolver:  {'🟢 Running' if status['java']['running'] else '⚪ Stopped'}"
                  f" (port {status['java']['port']})" +
                  (f" [PID {status['java']['pid']}]" if status['java']['pid'] else ""))
            print(f"   Python Admin:   {'🟢 Running' if status['python']['running'] else '⚪ Stopped'}"
                  f" (port {status['python']['port']})" +
                  (f" [PID {status['python']['pid']}]" if status['python']['pid'] else ""))
            print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
