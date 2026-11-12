"""Installed Veil CLI entry point."""
from veil.command import main

__all__ = ["main"]

if __name__ == "__main__":
    import sys
    sys.exit(main())
