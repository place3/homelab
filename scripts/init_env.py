"""Create a private local .env with a random Grafana password; never overwrite it."""

import argparse
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    content = (
        "PROMETHEUS_PORT=29090\nGRAFANA_PORT=23030\nGRAFANA_ADMIN_USER=admin\n"
        f"GRAFANA_ADMIN_PASSWORD={secrets.token_urlsafe(32)}\n"
    )
    try:
        descriptor = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.exit(1, f"Already exists: {args.path}; not overwritten.\n")
    with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
        destination.write(content)
    print(f"Created {args.path}. Password is stored there and is not printed.")


if __name__ == "__main__":
    main()
