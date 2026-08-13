from __future__ import annotations

import asyncio
import os
from pathlib import Path

from pypdf import PdfReader

from scribd_downloader import DownloaderError


def partial_pdf_path(output: Path) -> Path:
    return output.with_name(f".{output.stem}.partial.pdf")


async def wait_for_pdf(path: Path, timeout_seconds: float = 60) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        size = path.stat().st_size if path.exists() else 0
        if size > 0:
            with path.open("rb") as file:
                file.seek(max(0, size - 1024))
                if file.read().rstrip().endswith(b"%%EOF"):
                    return
        await asyncio.sleep(0.25)
    raise DownloaderError("print: Firefox did not finish writing the PDF")


def finalize_pdf(partial: Path, output: Path, expected_pages: int) -> None:
    try:
        if not partial.exists() or partial.stat().st_size == 0:
            raise DownloaderError("print: Firefox produced an empty PDF")
        reader = PdfReader(partial)
        actual_pages = len(reader.pages)
        if actual_pages != expected_pages:
            raise DownloaderError(
                f"print: expected {expected_pages} PDF pages, got {actual_pages}"
            )
        for page_number, page in enumerate(reader.pages, start=1):
            contents = page.get_contents()
            if contents is None or not contents.get_data().strip():
                raise DownloaderError(f"print: empty content on page {page_number}")
        os.replace(partial, output)
    except DownloaderError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as error:
        partial.unlink(missing_ok=True)
        raise DownloaderError(f"print: generated PDF is invalid ({error})") from error
