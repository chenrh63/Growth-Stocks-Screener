from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def copy_project(destination: Path, force: bool = False) -> Path:
    skill_root = Path(__file__).resolve().parents[1]
    template = skill_root / "assets" / "a-share-growth-screener-project"
    if not template.exists():
        raise FileNotFoundError(f"Bundled project template not found: {template}")

    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()) and not force:
        raise FileExistsError(
            f"Destination is not empty: {destination}. "
            "Pass --force to merge/overwrite template files."
        )

    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, destination, dirs_exist_ok=True)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the bundled A-share growth screener project.")
    parser.add_argument("destination", nargs="?", default="a-share-growth-screener-project")
    parser.add_argument("--force", action="store_true", help="Merge into an existing destination.")
    args = parser.parse_args()

    destination = copy_project(Path(args.destination), force=args.force)
    print(f"Copied project to: {destination}")
    print("")
    print("Next commands:")
    print(f"  cd {destination}")
    print("  python -m venv .venv")
    print("  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    print("  copy .env.example .env")
    print("  # Fill TUSHARE_TOKEN and optional LLM settings in .env")
    print("  .\\.venv\\Scripts\\python.exe -m stock_screener.screen_market --period 20260331 --target-count 30")


if __name__ == "__main__":
    main()
