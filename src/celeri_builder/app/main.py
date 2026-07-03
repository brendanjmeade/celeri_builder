"""Console entry point for celeri_builder."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from celeri_builder.app.core import CeleriBuilderApp


def main(server=None, **kwargs):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root-dir", default=None, help="file-browser root")
    parser.add_argument(
        "--no-basemap", action="store_true", help="run without a basemap"
    )
    args, _ = parser.parse_known_args()
    if args.no_basemap:
        os.environ["CELERI_BUILDER_NO_BASEMAP"] = "1"
    root = Path(args.root_dir) if args.root_dir else None
    app = CeleriBuilderApp(server, root_dir=root)
    app.server.start(**kwargs)
