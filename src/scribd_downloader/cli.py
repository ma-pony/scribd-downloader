from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Sequence

from scribd_downloader import DownloaderError


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip(" .")
    return re.sub(r"\s+", " ", cleaned)


def default_output_path(title: str, document_id: str) -> Path:
    stem = sanitize_filename(title) or document_id
    return Path(f"{stem}.pdf")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scribd-downloader")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("login", help="Open Camoufox for a manual Scribd login")

    download_parser = subparsers.add_parser("download", help="Render a Scribd document to PDF")
    download_parser.add_argument("url")
    download_parser.add_argument("-o", "--output", type=Path)
    download_parser.add_argument("--guest", action="store_true")
    return parser


async def login() -> None:
    from scribd_downloader.browser import login as browser_login

    await browser_login()


async def download(url: str, output: Path | None, guest: bool) -> Path:
    from scribd_downloader.browser import download as browser_download

    return await browser_download(
        url=url,
        output=output,
        guest=guest,
        progress=lambda loaded, total: print(
            f"render: {loaded}/{total} pages", file=sys.stderr
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "login":
            asyncio.run(login())
        else:
            result = asyncio.run(download(args.url, args.output, args.guest))
            print(result)
        return 0
    except DownloaderError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def entrypoint() -> None:
    raise SystemExit(main())
