"""Static version gates. Source support is not an E2E certification."""

from __future__ import annotations

import json
from pathlib import Path

SUPPORTED_OS = {("debian", "12"), ("debian", "13"), ("ubuntu", "24.04")}
SUPPORTED_ARCH = {"x86_64", "amd64", "aarch64", "arm64"}
SUPPORTED_PANEL = "3.11.0"


def load_capabilities() -> dict:
    path = Path(__file__).resolve().parents[2] / "config" / "capabilities.json"
    return json.loads(path.read_text(encoding="utf-8"))


def version_supported(version: str | None) -> bool:
    return version is not None and version.lstrip("v") == SUPPORTED_PANEL


def profile_supported(name: str, version: str | None) -> bool:
    return version_supported(version) and name in load_capabilities()["profiles"]
