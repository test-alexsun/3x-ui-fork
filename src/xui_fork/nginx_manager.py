"""Safe syntax validation for candidate Nginx configuration."""

import subprocess
from pathlib import Path


def validate(config: Path) -> None:
    subprocess.run(["nginx", "-t", "-c", str(config)], check=True)
