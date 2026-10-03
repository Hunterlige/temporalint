"""Static checks for Temporal Python SDK usage."""

import sys

__version__ = "0.1.0"


def main() -> None:
    from temporalint.cli import main as cli_main

    sys.exit(cli_main())
