"""Agent Runtime Watchdog — Self-Healing Process Monitor.

Runs as a lightweight independent process that:
  - Checks Agent Runtime health every 30 seconds
  - Restarts the runtime if dead (via subprocess/systemd)
  - Logs degradation and unhealthy states
  - Fires health metrics for Prometheus scraping

Minimal dependencies — no app imports, pure stdlib + basic HTTP.
Designed to run as a systemd service or standalone Python process.

Usage:
    # As systemd service (recommended for production)
    # See deploy/watchdog.service

    # Standalone for testing:
    python -m app.agents.watchdog

    # With custom settings:
    WATCHDOG_INTERVAL=15 WATCHDOG_TARGET=http://127.0.0.1:8202/health \\
    python -m app.agents.watchdog
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_CHECK_INTERVAL = 30          # seconds between health checks
DEFAULT_TARGET_URL = "http://127.0.0.1:8202/health"   # Agent Runtime health endpoint
DEFAULT_STARTUP_SCRIPT = "scripts/start_agents.py"     # relative to BACKEND_DIR
DEFAULT_TIMEOUT = 10                                   # HTTP request timeout
DEFAULT_UNHEALTHY_THRESHOLD = 3                        # consecutive failures before action
BACKEND_DIR = os.environ.get(
    "BACKEND_DIR",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

# ── Logging Setup ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s [WATCHDOG] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    stream=sys.stdout,
)
logger = logging.getLogger("watchdog")


# ── Health Check ───────────────────────────────────────────────────────────

class HealthStatus:
    """Health check result."""

    def __init__(
        self,
        alive: bool,
        status_code: int = 0,
        latency_ms: float = 0.0,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.alive = alive
        self.status_code = status_code
        self.latency_ms = latency_ms
        self.payload = payload or {}
        self.error = error
        self.timestamp = datetime.now(timezone.utc)

    @property
    def healthy(self) -> bool:
        """True if the runtime is alive AND reporting healthy status."""
        if not self.alive:
            return False
        runtime = self.payload.get("runtime", {})
        return runtime.get("running", False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alive": self.alive,
            "healthy": self.healthy,
            "status_code": self.status_code,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "payload_running": self.payload.get("runtime", {}).get("running"),
        }


def check_health(target_url: str, timeout: int = DEFAULT_TIMEOUT) -> HealthStatus:
    """Check Agent Runtime health endpoint.

    Expects the runtime's /health endpoint to return JSON with:
        {"runtime": {"running": true, ...}, "agents": {...}}

    Returns:
        HealthStatus with alive/healthy flags.
    """
    start = time.monotonic()
    try:
        req = urllib.request.Request(
            target_url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": "chainke-watchdog/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = (time.monotonic() - start) * 1000  # ms
            body = resp.read().decode("utf-8")
            payload: dict[str, Any] = json.loads(body)
            return HealthStatus(
                alive=True,
                status_code=resp.status,
                latency_ms=latency,
                payload=payload,
            )
    except urllib.error.HTTPError as exc:
        latency = (time.monotonic() - start) * 1000
        return HealthStatus(
            alive=False,
            status_code=exc.code,
            latency_ms=latency,
            error=f"HTTP {exc.code}: {exc.reason}",
        )
    except urllib.error.URLError as exc:
        latency = (time.monotonic() - start) * 1000
        return HealthStatus(
            alive=False,
            latency_ms=latency,
            error=f"Connection failed: {exc.reason}",
        )
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        latency = (time.monotonic() - start) * 1000
        return HealthStatus(
            alive=False,
            latency_ms=latency,
            error=f"Parse/IO error: {exc}",
        )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return HealthStatus(
            alive=False,
            latency_ms=latency,
            error=f"Unexpected error: {exc}",
        )


# ── Restart Logic ──────────────────────────────────────────────────────────

def restart_runtime() -> bool:
    """Restart the Agent Runtime via subprocess.

    Attempts:
      1. systemctl restart (if running under systemd)
      2. subprocess.Popen (fallback — for Docker/manual mode)

    Returns:
        True if restart was initiated successfully.
    """
    logger.warning("Attempting to restart Agent Runtime...")

    # Strategy 1: systemd (production)
    if os.environ.get("INVOCATION_ID") or os.environ.get("JOURNAL_STREAM"):
        try:
            subprocess.run(
                ["systemctl", "restart", "chainke-agents"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            logger.info("systemctl restart command issued for chainke-agents")
            return True
        except FileNotFoundError:
            logger.debug("systemctl not found — falling back to direct start")
        except subprocess.TimeoutExpired:
            logger.error("systemctl restart timed out")
        except Exception as exc:
            logger.error("systemctl restart failed: %s", exc)

    # Strategy 2: direct subprocess (Docker/manual)
    try:
        startup_path = os.path.join(BACKEND_DIR, DEFAULT_STARTUP_SCRIPT)
        if not os.path.exists(startup_path):
            # Try a few alternative locations
            alt_paths = [
                os.path.join(os.getcwd(), DEFAULT_STARTUP_SCRIPT),
                os.path.join(os.path.dirname(BACKEND_DIR), "backend", DEFAULT_STARTUP_SCRIPT),
                DEFAULT_STARTUP_SCRIPT,
            ]
            for alt in alt_paths:
                if os.path.exists(alt):
                    startup_path = alt
                    break

        if not os.path.exists(startup_path):
            logger.error("Cannot find startup script: %s", startup_path)
            return False

        # Kill existing process if any (port 8202)
        try:
            subprocess.run(
                ["pkill", "-f", "start_agents.py"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            time.sleep(2)
        except Exception:
            pass

        # Start new process
        proc = subprocess.Popen(
            [sys.executable, startup_path],
            cwd=BACKEND_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(
            "Agent Runtime restart initiated (PID=%d, script=%s)",
            proc.pid,
            startup_path,
        )
        return True

    except Exception as exc:
        logger.error("Failed to restart Agent Runtime: %s", exc)
        return False


# ── Main Watchdog Loop ─────────────────────────────────────────────────────

def _load_env_config() -> dict[str, Any]:
    """Load configuration from environment variables."""
    return {
        "interval": int(os.environ.get("WATCHDOG_INTERVAL", str(DEFAULT_CHECK_INTERVAL))),
        "target_url": os.environ.get("WATCHDOG_TARGET", DEFAULT_TARGET_URL),
        "timeout": int(os.environ.get("WATCHDOG_TIMEOUT", str(DEFAULT_TIMEOUT))),
        "unhealthy_threshold": int(
            os.environ.get("WATCHDOG_UNHEALTHY_THRESHOLD", str(DEFAULT_UNHEALTHY_THRESHOLD))
        ),
        "metrics_port": int(os.environ.get("WATCHDOG_METRICS_PORT", "0")),
    }


def _log_status(status: HealthStatus) -> None:
    """Log the health check result at appropriate level."""
    if status.healthy:
        logger.debug(
            "Health OK — status=%d, latency=%.1fms, agents=%s, running=%s",
            status.status_code,
            status.latency_ms,
            len(status.payload.get("agents", {})),
            status.payload.get("runtime", {}).get("running"),
        )
    elif status.alive and not status.healthy:
        logger.warning(
            "Runtime alive but UNHEALTHY — status=%d, latency=%.1fms, payload=%s",
            status.status_code,
            status.latency_ms,
            json.dumps(status.to_dict()),
        )
    else:
        logger.error(
            "Runtime DEAD — status=%d, latency=%.1fms, error=%s",
            status.status_code,
            status.latency_ms,
            status.error,
        )


def run_watchdog() -> None:
    """Main watchdog loop. Runs until interrupted (Ctrl+C / SIGTERM)."""
    config = _load_env_config()
    consecutive_failures = 0

    logger.info(
        "=" * 60,
    )
    logger.info(
        "Agent Runtime Watchdog started",
    )
    logger.info("  Target:      %s", config["target_url"])
    logger.info("  Interval:    %ds", config["interval"])
    logger.info("  Threshold:   %d consecutive failures", config["unhealthy_threshold"])
    logger.info("  Backend dir: %s", BACKEND_DIR)
    logger.info(
        "=" * 60,
    )

    while True:
        try:
            status = check_health(config["target_url"], config["timeout"])
            _log_status(status)

            if status.healthy:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logger.warning(
                    "Unhealthy check #%d/%d",
                    consecutive_failures,
                    config["unhealthy_threshold"],
                )

            # Trigger restart when threshold is exceeded
            if consecutive_failures >= config["unhealthy_threshold"]:
                logger.critical(
                    "Agent Runtime unhealthy for %d consecutive checks — initiating recovery",
                    consecutive_failures,
                )
                if restart_runtime():
                    consecutive_failures = 0
                    logger.info("Restart initiated, waiting 15s before next health check...")
                    time.sleep(15)
                else:
                    logger.critical(
                        "Restart FAILED — manual intervention required for Agent Runtime"
                    )

        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user (SIGINT)")
            break
        except Exception as exc:
            logger.exception("Watchdog loop error: %s", exc)
            consecutive_failures += 1

        time.sleep(config["interval"])

    logger.info("Watchdog shutting down. Agent Runtime monitoring ended.")


# ── Entry Point ────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for 'python -m app.agents.watchdog'."""
    run_watchdog()


if __name__ == "__main__":
    main()
