import asyncio
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from scribd_downloader import DownloaderError
from scribd_downloader.pdf import finalize_pdf, partial_pdf_path, wait_for_pdf


def write_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        stream = DecodedStreamObject()
        stream.set_data(b"q 0 0 1 rg 0 0 10 10 re f Q")
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as file:
        writer.write(file)


def test_partial_path_stays_next_to_output(tmp_path: Path) -> None:
    output = tmp_path / "book.pdf"
    assert partial_pdf_path(output) == tmp_path / ".book.partial.pdf"


def test_wait_for_pdf_rejects_a_stable_file_without_eof(tmp_path: Path) -> None:
    partial = tmp_path / ".book.partial.pdf"

    async def finish_pdf() -> None:
        partial.write_bytes(b"%PDF-1.7\npartial body")

        async def append_eof() -> None:
            await asyncio.sleep(1)
            with partial.open("ab") as file:
                file.write(b"\n%%EOF\n")

        writer = asyncio.create_task(append_eof())
        await wait_for_pdf(partial, timeout_seconds=2)
        assert writer.done()
        assert partial.read_bytes().rstrip().endswith(b"%%EOF")

    asyncio.run(finish_pdf())


def test_finalize_replaces_output_after_validation(tmp_path: Path) -> None:
    output = tmp_path / "book.pdf"
    output.write_bytes(b"old")
    partial = partial_pdf_path(output)
    write_pdf(partial, 2)
    finalize_pdf(partial, output, expected_pages=2)
    assert output.read_bytes().startswith(b"%PDF")
    assert not partial.exists()


def test_finalize_preserves_output_on_page_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "book.pdf"
    output.write_bytes(b"old")
    partial = partial_pdf_path(output)
    write_pdf(partial, 1)
    with pytest.raises(DownloaderError, match="expected 2 PDF pages"):
        finalize_pdf(partial, output, expected_pages=2)
    assert output.read_bytes() == b"old"
    assert not partial.exists()


def test_finalize_rejects_an_empty_page(tmp_path: Path) -> None:
    output = tmp_path / "book.pdf"
    output.write_bytes(b"old")
    partial = partial_pdf_path(output)
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with partial.open("wb") as file:
        writer.write(file)
    with pytest.raises(DownloaderError, match="empty content on page 1"):
        finalize_pdf(partial, output, expected_pages=1)
    assert output.read_bytes() == b"old"
    assert not partial.exists()
