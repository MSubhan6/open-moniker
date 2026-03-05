#!/usr/bin/env python3
"""
Bootstrap script for Open Moniker - Multi-Resolver Support
==========================================================

Manages multiple resolver instances (Java/Go) alongside Python app.

Usage:
    python bootstrap_multi.py dev           # Start dev (1 Java, 0 Go)
    python bootstrap_multi.py multi         # Start multi (2 Java, 2 Go)
    python bootstrap_multi.py stop multi    # Stop multi environment
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
JAVA_RESOLVER = PROJECT_ROOT / "resolver-java"
GO_RESOLVER = PROJECT_ROOT / "resolver-go"
PYTHON_SRC = PROJECT_ROOT / "src"

# Environment configurations
ENVIRONMENTS = {
    "dev": {
        "python_port": 8050,
        "db_path": "dev/telemetry.db",
        "config_dir": "dev",
        "resolvers": {
            "java": [
                {"port": 8054, "name": "java-dev-1"},
            ],
            "go": [],
        },
    },
    "multi": {
        "python_port": 8050,
        "db_path": "multi/telemetry.db",
        "config_dir": "multi",
        "resolvers": {
            "java": [
                {"port": 8054, "name": "java-1"},
                {"port": 8055, "name": "java-2"},
            ],
            "go": [
                {"port": 8053, "name": "go-1"},
                {"port": 8056, "name": "go-2"},
            ],
        },
    },
}

PID_DIR = SCRIPT_DIR / ".pids"


class MultiResolverEnvironment:
    """Manages an environment with multiple resolvers."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.config_dir = SCRIPT_DIR / config["config_dir"]
        self.db_path = SCRIPT_DIR / config["db_path"]
        self.python_pid_file = PID_DIR / f"{name}-python.pid"
        self.resolver_pids = {}  # {resolver_name: pid_file}

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

        # Look for sample or existing file
        sample_file = PROJECT_ROOT / f"sample_{filename}"
        source_file = PROJECT_ROOT / filename

        if sample_file.exists():
            print(f"   Creating {filename} from sample...")
            shutil.copy(sample_file, dest_file)
        elif source_file.exists():
            print(f"   Copying {filename} from project root...")
            shutil.copy(source_file, dest_file)

    def start(self):
        """Start all resolvers and Python app."""
        print(f"\n🚀 Starting {self.name.upper()} environment...")

        self.setup()

        # Start all Java resolvers
        java_resolvers = self.config["resolvers"].get("java", [])
        for resolver in java_resolvers:
            print(f"   Starting Java resolver '{resolver['name']}' on port {resolver['port']}...")
            success = self._start_java_resolver(resolver)
            if not success:
                print(f"   ❌ Failed to start {resolver['name']}")
                self.stop()
                return False

        # Start all Go resolvers
        go_resolvers = self.config["resolvers"].get("go", [])
        for resolver in go_resolvers:
            print(f"   Starting Go resolver '{resolver['name']}' on port {resolver['port']}...")
            success = self._start_go_resolver(resolver)
            if not success:
                print(f"   ❌ Failed to start {resolver['name']}")
                self.stop()
                return False

        # Start Python app
        print(f"   Starting Python app on port {self.config['python_port']}...")
        python_success = self._start_python()

        if python_success:
            self._print_summary()
            return True
        else:
            print(f"❌ Failed to start Python app")
            self.stop()
            return False

    def _start_java_resolver(self, resolver: dict) -> bool:
        """Start a single Java resolver instance."""
        try:
            # Build if JAR doesn't exist
            jar_file = JAVA_RESOLVER / "target" / "resolver-java-0.1.0.jar"
            if not jar_file.exists():
                print("      Building Java resolver (first time)...")
                result = subprocess.run(
                    ["mvn", "clean", "package", "-DskipTests"],
                    cwd=JAVA_RESOLVER,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    print(f"      ❌ Maven build failed")
                    return False

            # Start Java process
            log_file = SCRIPT_DIR / f"{self.name}-{resolver['name']}.log"
            env = os.environ.copy()
            env.update({
                "SERVER_PORT": str(resolver["port"]),
                "CONFIG_FILE": str(self.config_dir / "config.yaml"),
                "CATALOG_FILE": str(self.config_dir / "catalog.yaml"),
            })

            with open(log_file, "w") as log:
                process = subprocess.Popen(
                    [
                        "java",
                        f"-Dmoniker.config-file={self.config_dir / 'config.yaml'}",
                        f"-Dmoniker.telemetry.enabled=true",
                        f"-Dmoniker.telemetry.sinkType=sqlite",
                        f"-Dmoniker.telemetry.sinkConfig.dbPath={self.db_path}",
                        f"-Dserver.port={resolver['port']}",
                        f"-Dmoniker.resolver.name={resolver['name']}",
                        "-jar",
                        str(jar_file)
                    ],
                    cwd=JAVA_RESOLVER,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )

            # Save PID
            pid_file = PID_DIR / f"{self.name}-{resolver['name']}.pid"
            pid_file.write_text(str(process.pid))
            self.resolver_pids[resolver['name']] = pid_file

            # Wait for startup
            if self._wait_for_health(resolver['port'], timeout=30):
                print(f"      ✅ Started {resolver['name']} (PID {process.pid})")
                return True
            else:
                print(f"      ❌ Health check failed (check {log_file})")
                return False

        except Exception as e:
            print(f"      ❌ Error: {e}")
            return False

    def _start_go_resolver(self, resolver: dict) -> bool:
        """Start a single Go resolver instance."""
        try:
            # Check if Go resolver binary exists
            go_binary = GO_RESOLVER / "bin" / "resolver"
            if not go_binary.exists():
                print("      Building Go resolver (first time)...")
                result = subprocess.run(
                    ["make", "build"],
                    cwd=GO_RESOLVER,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    print(f"      ❌ Go build failed")
                    return False

            # Start Go process
            log_file = SCRIPT_DIR / f"{self.name}-{resolver['name']}.log"
            env = os.environ.copy()
            env.update({
                "PORT": str(resolver["port"]),
                "CONFIG_FILE": str(self.config_dir / "config.yaml"),
                "CATALOG_FILE": str(self.config_dir / "catalog.yaml"),
                "TELEMETRY_DB_PATH": str(self.db_path),
                "RESOLVER_NAME": resolver['name'],
            })

            with open(log_file, "w") as log:
                process = subprocess.Popen(
                    [str(go_binary), "--port", str(resolver["port"])],
                    cwd=GO_RESOLVER,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )

            # Save PID
            pid_file = PID_DIR / f"{self.name}-{resolver['name']}.pid"
            pid_file.write_text(str(process.pid))
            self.resolver_pids[resolver['name']] = pid_file

            # Wait for startup
            if self._wait_for_health(resolver['port'], timeout=30):
                print(f"      ✅ Started {resolver['name']} (PID {process.pid})")
                return True
            else:
                print(f"      ❌ Health check failed (check {log_file})")
                return False

        except Exception as e:
            print(f"      ❌ Error: {e}")
            return False

    def _start_python(self) -> bool:
        """Start Python app."""
        try:
            env = os.environ.copy()
            env.update({
                "PYTHONPATH": str(PYTHON_SRC),
                "PORT": str(self.config["python_port"]),
                "CONFIG_FILE": str(self.config_dir / "config.yaml"),
                "CATALOG_FILE": str(self.config_dir / "catalog.yaml"),
                "TELEMETRY_DB_TYPE": "sqlite",
                "TELEMETRY_DB_PATH": str(self.db_path),
            })

            log_file = SCRIPT_DIR / f"{self.name}-python.log"
            with open(log_file, "w") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "moniker_svc.main:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        str(self.config["python_port"]),
                    ],
                    cwd=PYTHON_SRC.parent,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )

            # Save PID
            self.python_pid_file.write_text(str(process.pid))

            # Wait for startup
            if self._wait_for_health(self.config["python_port"], timeout=30):
                print(f"      ✅ Started Python app (PID {process.pid})")
                return True
            else:
                print(f"      ❌ Health check failed (check {log_file})")
                return False

        except Exception as e:
            print(f"      ❌ Error: {e}")
            return False

    def _wait_for_health(self, port: int, timeout: int = 30) -> bool:
        """Wait for service health check to pass."""
        url = f"http://localhost:{port}/health"
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(1)

        return False

    def _print_summary(self):
        """Print environment summary."""
        print(f"\n✅ {self.name.upper()} environment started successfully\n")

        print("📊 Resolvers:")
        for resolver in self.config["resolvers"].get("java", []):
            print(f"   • Java {resolver['name']}: http://localhost:{resolver['port']}/health")
        for resolver in self.config["resolvers"].get("go", []):
            print(f"   • Go {resolver['name']}: http://localhost:{resolver['port']}/health")

        print(f"\n🎛  Python App:")
        print(f"   • Landing: http://localhost:{self.config['python_port']}/")
        print(f"   • Telemetry: http://localhost:{self.config['python_port']}/telemetry")
        print(f"   • Health: http://localhost:{self.config['python_port']}/health")

    def stop(self):
        """Stop all services."""
        print(f"\n🛑 Stopping {self.name.upper()} environment...")

        stopped = 0

        # Stop all resolvers
        for name, pid_file in list(self.resolver_pids.items()):
            if self._stop_service(pid_file, name):
                stopped += 1

        # Stop Python app
        if self._stop_service(self.python_pid_file, "Python app"):
            stopped += 1

        if stopped > 0:
            print(f"✅ Stopped {stopped} service(s)")

    def _stop_service(self, pid_file: Path, name: str) -> bool:
        """Stop a single service by PID file."""
        if not pid_file.exists():
            return False

        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            try:
                os.kill(pid, 0)  # Check if still running
                os.kill(pid, signal.SIGKILL)  # Force kill
            except ProcessLookupError:
                pass
            pid_file.unlink()
            print(f"   ✅ Stopped {name} (PID {pid})")
            return True
        except (ValueError, ProcessLookupError):
            pid_file.unlink()
            return False


def main():
    parser = argparse.ArgumentParser(description="Multi-resolver bootstrap")
    parser.add_argument("action", choices=["dev", "multi", "stop"], help="Action to perform")
    parser.add_argument("env", nargs="?", help="Environment (for stop)")
    args = parser.parse_args()

    if args.action == "stop":
        env_name = args.env or "dev"
        if env_name not in ENVIRONMENTS:
            print(f"❌ Unknown environment: {env_name}")
            return 1

        env = MultiResolverEnvironment(env_name, ENVIRONMENTS[env_name])
        env.stop()
        return 0

    else:
        env_name = args.action
        if env_name not in ENVIRONMENTS:
            print(f"❌ Unknown environment: {env_name}")
            return 1

        env = MultiResolverEnvironment(env_name, ENVIRONMENTS[env_name])
        success = env.start()
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
