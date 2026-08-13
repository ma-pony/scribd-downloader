import asyncio
import re
from types import SimpleNamespace

import pytest
from playwright.async_api import Error as PlaywrightError

from scribd_downloader import DownloaderError
from scribd_downloader.scribd import (
    DocumentInfo,
    ResourceMonitor,
    parse_document_url,
    prepare_print_dom,
    render_document,
    validate_document_state,
    wait_for_manager,
)


def test_parse_document_url_accepts_document_page() -> None:
    ref = parse_document_url("https://www.scribd.com/document/884183779/Sample-5-Page-PDF")
    assert ref.document_id == "884183779"
    assert ref.embed_url == (
        "https://www.scribd.com/embeds/884183779/content?start_page=1&view_mode=scroll"
    )


def test_parse_document_url_accepts_embed_page() -> None:
    ref = parse_document_url("https://www.scribd.com/embeds/884183779/content")
    assert ref.document_id == "884183779"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/document/884183779/sample",
        "https://www.scribd.com/book/884183779/sample",
        "https://www.scribd.com/document/not-a-number/sample",
    ],
)
def test_parse_document_url_rejects_unsupported_urls(url: str) -> None:
    with pytest.raises(DownloaderError, match="URL"):
        parse_document_url(url)


def test_validate_document_state_returns_metadata() -> None:
    info = validate_document_state(
        "884183779",
        {"title": "Sample", "pageCount": 5, "sizes": [[612, 792]] * 5, "missing": []},
    )
    assert info.page_count == 5
    assert (info.width, info.height) == (612, 792)


def test_validate_document_state_clears_generic_scribd_title() -> None:
    info = validate_document_state(
        "884183779",
        {"title": "  SCRIBD  ", "pageCount": 1, "sizes": [[612, 792]], "missing": []},
    )
    assert info.title == ""


def test_validate_document_state_rejects_missing_methods() -> None:
    with pytest.raises(DownloaderError, match="turnOnImages"):
        validate_document_state(
            "884183779",
            {"title": "Sample", "pageCount": 5, "sizes": [], "missing": ["page.turnOnImages"]},
        )


def test_resource_monitor_ignores_unrelated_failures() -> None:
    monitor = ResourceMonitor()
    monitor.record_failure("https://analytics.example/pixel", "image", "blocked")
    assert monitor.failures == []


def test_resource_monitor_keeps_page_asset_failure() -> None:
    monitor = ResourceMonitor()
    monitor.record_failure(
        "https://html.scribdassets.com/abc/pages/3-page.jsonp", "script", "HTTP 503"
    )
    assert monitor.failures[0].kind == "page"


def test_resource_monitor_ignores_viewer_ui_font_failure() -> None:
    monitor = ResourceMonitor()
    monitor.record_failure(
        "https://html.scribdassets.com/webpack/assets/fonts/scribd_sans/ScribdSans.woff2",
        "font",
        "blocked",
    )
    assert monitor.failures == []


def test_resource_monitor_keeps_document_font_failure() -> None:
    monitor = ResourceMonitor()
    monitor.record_failure(
        "https://html.scribdassets.com/abc/fonts/3-document.woff2", "font", "HTTP 503"
    )
    assert monitor.failures[0].kind == "font"


def test_wait_for_manager_retries_context_destruction() -> None:
    class Page:
        calls = 0

        async def evaluate(self, script: str) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                raise PlaywrightError("Execution context was destroyed")
            return {"title": "Sample", "pageCount": 1, "sizes": [[612, 792]], "missing": []}

    page = Page()
    state = asyncio.run(wait_for_manager(page, timeout_seconds=1))  # type: ignore[arg-type]
    assert state["pageCount"] == 1
    assert page.calls == 2


def test_render_document_translates_navigation_failure() -> None:
    class Page:
        def on(self, event: str, callback: object) -> None:
            pass

        async def goto(self, url: str, **options: object) -> None:
            raise PlaywrightError("NS_ERROR_NET_TIMEOUT")

    with pytest.raises(DownloaderError, match=r"^navigation:.*NS_ERROR_NET_TIMEOUT"):
        asyncio.run(
            render_document(
                Page(),  # type: ignore[arg-type]
                parse_document_url("https://www.scribd.com/document/884183779/sample"),
            )
        )


def test_render_document_translates_batch_evaluation_failure() -> None:
    class Page:
        evaluate_calls = 0

        def on(self, event: str, callback: object) -> None:
            pass

        async def goto(self, url: str, **options: object) -> SimpleNamespace:
            return SimpleNamespace(status=200)

        async def evaluate(self, script: str, argument: object = None) -> dict[str, object]:
            self.evaluate_calls += 1
            if self.evaluate_calls == 1:
                return {
                    "title": "Sample",
                    "pageCount": 1,
                    "sizes": [[612, 792]],
                    "missing": [],
                }
            raise PlaywrightError("pages 1-1 did not finish loading")

    with pytest.raises(
        DownloaderError, match=r"^render: pages 1-1.*did not finish loading"
    ):
        asyncio.run(
            render_document(
                Page(),  # type: ignore[arg-type]
                parse_document_url("https://www.scribd.com/document/884183779/sample"),
            )
        )


@pytest.mark.parametrize(
    "failure",
    [
        "page 1 border box changed from 902x1274 to 900x1272",
        "page 1 content 901x1272 exceeds visible box 900x1272",
    ],
)
def test_prepare_print_dom_rejects_incomplete_page_layout(failure: str) -> None:
    class Page:
        async def evaluate(self, script: str, argument: object) -> dict[str, object]:
            return {"renderedPages": 1, "layoutFailures": [failure]}

    info = DocumentInfo("884183779", "Sample", 1, 902, 1274)
    with pytest.raises(DownloaderError, match=re.escape(failure)):
        asyncio.run(prepare_print_dom(Page(), info))  # type: ignore[arg-type]
