import asyncio
import os

import pytest
from camoufox.async_api import AsyncCamoufox

from scribd_downloader.scribd import (
    ProgressCallback,
    parse_document_url,
    prepare_print_dom,
    render_document,
)


@pytest.mark.skipif(os.environ.get("SCRIBD_LIVE") != "1", reason="set SCRIBD_LIVE=1")
def test_public_five_page_document_renders_all_pages() -> None:
    async def run() -> tuple[int, list[tuple[int, int]]]:
        progress: list[tuple[int, int]] = []
        async with AsyncCamoufox(
            headless=True,
            main_world_eval=True,
            enable_cache=True,
        ) as browser:
            page = await browser.new_page()
            info = await render_document(
                page,
                parse_document_url(
                    "https://www.scribd.com/document/884183779/Sample-5-Page-PDF"
                ),
                progress=lambda loaded, total: progress.append((loaded, total)),
            )
            await prepare_print_dom(page, info)
            return info.page_count, progress

    assert asyncio.run(run()) == (5, [(5, 5)])
