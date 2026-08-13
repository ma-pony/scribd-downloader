import pytest

from scribd_downloader import DownloaderError
from scribd_downloader.scribd import (
    ResourceMonitor,
    parse_document_url,
    validate_document_state,
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
