from pathlib import Path

import pytest

from scribd_downloader import DownloaderError
from scribd_downloader.cli import build_parser, default_output_path, main, sanitize_filename


def test_parser_accepts_guest_download() -> None:
    args = build_parser().parse_args(
        ["download", "https://www.scribd.com/document/884183779/sample", "--guest", "-o", "book.pdf"]
    )
    assert args.command == "download"
    assert args.url.endswith("/884183779/sample")
    assert args.guest is True
    assert args.output == Path("book.pdf")


def test_sanitize_filename_removes_path_characters() -> None:
    assert sanitize_filename("  A/B: C  ") == "A_B_ C"


def test_default_output_uses_document_id_for_empty_title() -> None:
    assert default_output_path("", "884183779") == Path("884183779.pdf")


def test_main_returns_one_for_downloader_error(monkeypatch, capsys) -> None:
    async def fail(*args, **kwargs) -> Path:
        raise DownloaderError("render: page 3 failed")

    monkeypatch.setattr("scribd_downloader.cli.download", fail)
    assert main(["download", "https://www.scribd.com/document/884183779/sample", "--guest"]) == 1
    assert "render: page 3 failed" in capsys.readouterr().err


def test_parser_error_uses_exit_code_two() -> None:
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["download"])
    assert error.value.code == 2
