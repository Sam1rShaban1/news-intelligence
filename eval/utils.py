"""Shared eval utilities — REQ-0.1 provenance, REQ-0.4 seeding, hardware snapshot."""

from __future__ import annotations

import datetime
import json
import os
import platform
import random
import subprocess
import sys
from pathlib import Path


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def git_short() -> str:
    c = git_commit()
    return c[:8] if c != "unknown" else c


def docker_image_tags() -> dict[str, str]:
    """Return resolved backend/frontend image tags from env + compose defaults."""
    return {
        "backend_image": os.environ.get("NI_BACKEND_IMAGE", "ghcr.io/sam1rshaban1/news-intelligence-worker"),
        "frontend_image": os.environ.get("NI_FRONTEND_IMAGE", "ghcr.io/sam1rshaban1/news-intelligence-frontend"),
        "image_tag": os.environ.get("NI_IMAGE_TAG", "latest"),
    }


def hardware_spec() -> dict:
    """Best-effort hardware snapshot for the REQ-0.1 header."""
    spec: dict = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }
    # RAM via /proc/meminfo when available
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    spec["mem_total"] = line.strip()
                    break
    except Exception:
        pass
    # Detect Pi vs VPS heuristic (not authoritative — REQ-5 says state explicitly)
    spec["tier_hint"] = "pi" if Path("/proc/device-tree/model").exists() else "vps-or-unknown"
    try:
        model = Path("/proc/device-tree/model").read_text(errors="ignore").strip("\x00\n ")
        if model:
            spec["device_model"] = model
    except Exception:
        pass
    return spec


def provenance_header(seed: int | None = None) -> dict:
    """REQ-0.1 header that every results file should start with."""
    return {
        "date_run": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "hardware": hardware_spec(),
        "docker_images": docker_image_tags(),
        "seed": seed,
        "python_argv": sys.argv[:],
    }


def ensure_seed(seed: int) -> None:
    """REQ-0.4 — pin all RNGs."""
    random.seed(seed)
    try:
        import numpy as np  # type: ignore

        np.random.seed(seed)
    except Exception:
        pass


def write_jsonl_with_header(path: Path, header: dict, rows: list[dict]) -> None:
    """Write a JSON Lines file whose first line is a provenance header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"_provenance": header}, ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_csv_with_header(path: Path, header: dict, csv_text: str) -> None:
    """Write CSV prefixed by a commented header (so REQ-0.1 is still searchable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# provenance: {json.dumps(header, ensure_ascii=False)}",
        csv_text.rstrip() + "\n",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
