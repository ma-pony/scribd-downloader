from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

from camoufox.async_api import AsyncCamoufox

from scribd_downloader import DownloaderError
from scribd_downloader.cli import default_output_path
from scribd_downloader.pdf import finalize_pdf, partial_pdf_path, wait_for_pdf
from scribd_downloader.scribd import (
    ProgressCallback,
    parse_document_url,
    prepare_print_dom,
    render_document,
)


PROFILE_DIR = Path.home() / ".scribd-downloader" / "profile"
LOGIN_URL = "https://www.scribd.com/login"


def print_preferences(output: Path) -> dict[str, object]:
    filename = str(output.resolve())
    prefix = "print.printer_Mozilla_Save_to_PDF"
    return {
        "print.always_print_silent": True,
        "print_printer": "Mozilla Save to PDF",
        "print.print_to_file": True,
        "print.print_to_filename": filename,
        f"{prefix}.print_to_file": True,
        f"{prefix}.print_to_filename": filename,
        f"{prefix}.print_bgcolor": True,
        f"{prefix}.print_bgimages": True,
        f"{prefix}.print_margin_top": "0",
        f"{prefix}.print_margin_bottom": "0",
        f"{prefix}.print_margin_left": "0",
        f"{prefix}.print_margin_right": "0",
        f"{prefix}.print_headerleft": "",
        f"{prefix}.print_headercenter": "",
        f"{prefix}.print_headerright": "",
        f"{prefix}.print_footerleft": "",
        f"{prefix}.print_footercenter": "",
        f"{prefix}.print_footerright": "",
        f"{prefix}.print_shrink_to_fit": True,
        f"{prefix}.print_scaling": "1",
        "print.save_as_pdf.use_page_rule_size_as_paper_size.enabled": True,
    }


def launch_options(
    *, guest: bool, headless: bool, print_path: Path | None = None
) -> dict[str, object]:
    options: dict[str, object] = {
        "headless": headless,
        "main_world_eval": True,
        "enable_cache": True,
    }
    if not guest:
        options.update(
            persistent_context=True,
            user_data_dir=str(PROFILE_DIR),
        )
    if print_path is not None:
        options["firefox_user_prefs"] = print_preferences(print_path)
    return options


async def login() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with AsyncCamoufox(**launch_options(guest=False, headless=False)) as context:
            page = await context.new_page()
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=120_000)
            await asyncio.to_thread(
                input, "Complete Scribd login in Camoufox, then press Enter here: "
            )
    except DownloaderError:
        raise
    except Exception as error:
        raise DownloaderError(
            "browser: Camoufox failed; run `uv run camoufox fetch` and retry"
        ) from error


async def download(
    url: str,
    output: Path | None,
    guest: bool,
    progress: ProgressCallback | None = None,
) -> Path:
    partial: Path | None = None
    try:
        ref = parse_document_url(url)
        try:
            resolved_output = output.expanduser().resolve() if output else None
            base_dir = resolved_output.parent if resolved_output else Path.cwd()
            base_dir.mkdir(parents=True, exist_ok=True)
            partial = (
                partial_pdf_path(resolved_output)
                if resolved_output
                else base_dir / f".{ref.document_id}.partial.pdf"
            )
            partial.unlink(missing_ok=True)
        except Exception as error:
            raise DownloaderError(
                f"output: failed to prepare destination ({error})"
            ) from error

        async with AsyncCamoufox(
            **launch_options(guest=guest, headless=True, print_path=partial)
        ) as browser_or_context:
            page = await browser_or_context.new_page()
            try:
                info = await render_document(page, ref, progress=progress)
            except DownloaderError as error:
                if guest and "initialization timed out" in str(error):
                    raise DownloaderError(
                        f"{error}; run `scribd-downloader login` and retry without --guest"
                    ) from error
                raise
            if resolved_output:
                final_output = resolved_output
            else:
                try:
                    final_output = (
                        Path.cwd()
                        / default_output_path(info.title, info.document_id)
                    ).resolve()
                    final_output.parent.mkdir(parents=True, exist_ok=True)
                except Exception as error:
                    raise DownloaderError(
                        f"output: failed to prepare destination ({error})"
                    ) from error
            await prepare_print_dom(page, info)
            await page.evaluate("mw:window.print()")
            await wait_for_pdf(partial)

        finalize_pdf(partial, final_output, info.page_count)
        return final_output
    except DownloaderError:
        if partial is not None:
            with suppress(OSError):
                partial.unlink(missing_ok=True)
        raise
    except Exception as error:
        if partial is not None:
            with suppress(OSError):
                partial.unlink(missing_ok=True)
        raise DownloaderError(f"browser: download failed ({error})") from error
