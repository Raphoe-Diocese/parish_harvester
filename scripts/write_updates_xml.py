#!/usr/bin/env python3
"""Write Pages updates.xml for packed CRX + leftover unpacked zip."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packed-id", required=True)
    parser.add_argument("--legacy-id", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">\n'
        f'  <app appid="{args.packed_id}">\n'
        f'    <updatecheck codebase="{base}/extension/parish_trainer.crx" version="{args.version}" />\n'
        "  </app>\n"
        f'  <app appid="{args.legacy_id}">\n'
        f'    <updatecheck codebase="{base}/extension/parish_trainer.zip" version="{args.version}" />\n'
        "  </app>\n"
        "</gupdate>\n"
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
