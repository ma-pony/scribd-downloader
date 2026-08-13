from __future__ import annotations

import asyncio
from pathlib import Path

from camoufox.async_api import AsyncCamoufox

from scribd_downloader import DownloaderError


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
