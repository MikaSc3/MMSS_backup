"""Compatibility launcher. Prefer ``python run_app.py``."""

from run_app import main


if __name__ == "__main__":
    raise SystemExit(main())
