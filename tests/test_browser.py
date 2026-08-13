import asyncio
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

import scribd_downloader.browser as browser_module
from scribd_downloader import DownloaderError
from scribd_downloader.browser import (
    PROFILE_DIR,
    download,
    launch_options,
    print_preferences,
)
from scribd_downloader.pdf import partial_pdf_path
from scribd_downloader.scribd import DocumentInfo


def write_pdf(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    stream = DecodedStreamObject()
    stream.set_data(b"q 0 0 1 rg 0 0 10 10 re f Q")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as file:
        writer.write(file)


def test_persistent_launch_uses_local_profile() -> None:
    options = launch_options(guest=False, headless=True)
    assert options["persistent_context"] is True
    assert options["user_data_dir"] == str(PROFILE_DIR)
    assert options["main_world_eval"] is True


def test_guest_launch_has_no_profile() -> None:
    options = launch_options(guest=True, headless=True)
    assert "persistent_context" not in options
    assert "user_data_dir" not in options


def test_print_preferences_target_partial_file(tmp_path: Path) -> None:
    output = tmp_path / ".book.partial.pdf"
    preferences = print_preferences(output)
    assert preferences["print.always_print_silent"] is True
    assert preferences["print.print_to_filename"] == str(output.resolve())
    assert preferences["print.save_as_pdf.use_page_rule_size_as_paper_size.enabled"] is True


def test_guest_print_launch_has_no_profile(tmp_path: Path) -> None:
    options = launch_options(
        guest=True,
        headless=True,
        print_path=tmp_path / ".book.partial.pdf",
    )
    assert options["main_world_eval"] is True
    assert "user_data_dir" not in options
    assert "firefox_user_prefs" in options


def test_download_preserves_output_when_browser_teardown_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "book.pdf"
    output.write_bytes(b"old")
    partial = partial_pdf_path(output)

    class PrintingPage:
        async def evaluate(self, script: str) -> None:
            write_pdf(partial)

    class TeardownFailureContext:
        async def __aenter__(self) -> "TeardownFailureContext":
            return self

        async def __aexit__(self, *args: object) -> None:
            raise RuntimeError("teardown failed")

        async def new_page(self) -> PrintingPage:
            return PrintingPage()

    async def fake_render_document(*args: object, **kwargs: object) -> DocumentInfo:
        return DocumentInfo("884183779", "Book", 1, 612, 792)

    async def fake_prepare_print_dom(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        browser_module, "AsyncCamoufox", lambda **kwargs: TeardownFailureContext()
    )
    monkeypatch.setattr(browser_module, "render_document", fake_render_document)
    monkeypatch.setattr(browser_module, "prepare_print_dom", fake_prepare_print_dom)

    with pytest.raises(DownloaderError, match="browser: download failed.*teardown failed"):
        asyncio.run(
            download(
                "https://www.scribd.com/document/884183779/Sample-5-Page-PDF",
                output,
                guest=True,
            )
        )

    assert output.read_bytes() == b"old"
    assert not partial.exists()


def test_download_translates_invalid_output_setup(tmp_path: Path) -> None:
    parent = tmp_path / "not-a-directory"
    parent.write_text("blocker")

    with pytest.raises(DownloaderError, match="output: failed to prepare destination"):
        asyncio.run(
            download(
                "https://www.scribd.com/document/884183779/Sample-5-Page-PDF",
                parent / "book.pdf",
                guest=True,
            )
        )
