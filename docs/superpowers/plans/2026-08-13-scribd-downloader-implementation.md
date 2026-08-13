# scribd-downloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that uses Camoufox to load every Scribd document page through Scribd's own renderer and prints the resulting DOM to one validated PDF without screenshots.

**Architecture:** The CLI opens either a temporary guest browser or a persistent login context. `scribd.py` is the only module that knows Scribd's private `docManager` contract; it drives `load()`, `display()`, `loadFonts()`, and `turnOnImages()`, then prepares a clean print DOM. Firefox writes a partial PDF, and `pdf.py` validates its page count before replacing the requested output.

**Tech Stack:** Python 3.12, `camoufox==0.5.4`, Playwright `<1.61` through Camoufox, `pypdf`, `pytest`, `uv`

**Spec:** `docs/superpowers/specs/2026-08-13-scribd-downloader-design.md`

## Global Constraints

- Use Python 3.12 and `uv`.
- Pin `camoufox==0.5.4`; do not install `cloverlabs-camoufox`.
- Use `pypdf` only to validate generated PDFs.
- Use standard-library `argparse`; do not add a CLI framework.
- Support `scribd-downloader login` and `scribd-downloader download <URL> [-o OUTPUT.pdf] [--guest]`.
- Store the persistent browser profile at `~/.scribd-downloader/profile`.
- Do not accept or store account credentials.
- Do not call Playwright screenshot APIs or create image intermediate files.
- Do not request an original uploaded file or add a pure-HTTP fallback.
- Only export pages visible to the current Scribd browser session.
- Keep every Scribd private object name and DOM selector inside `src/scribd_downloader/scribd.py`.
- The 2026-08-13 live probe confirmed `docManager.pageCount()` and page methods `load()`, `display()`, `loadFonts()`, `turnOnImages()` with `containerElem` and `innerPageElem`.

## File Map

- `pyproject.toml`: package metadata, pinned runtime dependencies, CLI entry point, pytest settings.
- `.gitignore`: Python, uv, test, generated PDF, and local profile artifacts.
- `src/scribd_downloader/__init__.py`: package version and shared `DownloaderError`.
- `src/scribd_downloader/__main__.py`: `python -m scribd_downloader` entry point.
- `src/scribd_downloader/cli.py`: argument parsing, default output naming, command orchestration, exit codes.
- `src/scribd_downloader/browser.py`: Camoufox options, persistent login flow, guest/persistent contexts, Firefox print preferences.
- `src/scribd_downloader/scribd.py`: Scribd URL parsing, resource monitor, `docManager` adapter, page loading, print-DOM preparation.
- `src/scribd_downloader/pdf.py`: partial path, print completion polling, PDF validation, atomic replacement.
- `tests/test_cli.py`: CLI parsing, naming, error and exit-code tests.
- `tests/test_browser.py`: browser option and print preference tests without launching Camoufox.
- `tests/test_scribd.py`: URL parsing, resource classification, and adapter result validation tests.
- `tests/test_live_scribd.py`: opt-in live probe against a five-page public Scribd document.
- `tests/test_pdf.py`: partial path, PDF validation, replacement and cleanup tests.
- `README.md`: installation, browser fetch, login, guest download, local profile security, current limits.

## Golden Path and Finish List

A user pastes a public five-page Scribd document URL into the guest command. The terminal reports loaded page batches, prints the final PDF path, and leaves one PDF containing all five pages with selectable text. A returning user can run `login` once, then use the shorter default download command with the saved session.

The build is complete only when all of these are true:

- `--help` shows the guest and persistent-session paths without requiring project knowledge.
- A long download reports `render: <loaded>/<total> pages` after each batch.
- The five-page public sample produces five non-empty PDF page streams and extractable text.
- A missing Camoufox browser tells the user to run `uv run camoufox fetch`.
- A guest initialization failure suggests `scribd-downloader login` and a retry without `--guest`.
- A failed print preserves an existing output and removes its partial file.
- The terminal never prints credentials, Cookie values, authorization headers, tokens, or profile contents.

---

### Task 1: Package scaffold and CLI contract

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/scribd_downloader/__init__.py`
- Create: `src/scribd_downloader/__main__.py`
- Create: `src/scribd_downloader/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Produces: `DownloaderError(message: str)` in `scribd_downloader.__init__`.
- Produces: `sanitize_filename(value: str) -> str`.
- Produces: `default_output_path(title: str, document_id: str) -> Path`.
- Produces: `build_parser() -> argparse.ArgumentParser`.
- Produces: `main(argv: Sequence[str] | None = None) -> int`.
- Temporarily imports `login` and `download` lazily; Tasks 2 and 4 provide them.

- [ ] **Step 1: Write the failing CLI tests**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run the tests and verify the scaffold is missing**

Run: `uv run pytest tests/test_cli.py -q`

Expected: FAIL because `pyproject.toml` and `scribd_downloader` do not exist.

- [ ] **Step 3: Create package metadata and ignore rules**

Create `pyproject.toml`:

```toml
[project]
name = "scribd-downloader"
version = "0.1.0"
description = "Render Scribd document pages with Camoufox and save them as PDF"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "camoufox==0.5.4",
  "pypdf==6.14.2",
]

[project.scripts]
scribd-downloader = "scribd_downloader.cli:entrypoint"

[dependency-groups]
dev = ["pytest==9.1.1"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/scribd_downloader"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

Create `.gitignore`:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
dist/
*.egg-info/
*.pdf
.scribd-downloader/
```

Create the initial `README.md` so the package metadata is valid before the full usage guide is written:

```markdown
# scribd-downloader

Camoufox-based Scribd document renderer. Implementation is in progress.
```

Run: `uv lock`

Expected: `uv.lock` is created and resolves `camoufox==0.5.4` with Playwright below 1.61.

- [ ] **Step 4: Implement the package and CLI**

Create `src/scribd_downloader/__init__.py`:

```python
__version__ = "0.1.0"


class DownloaderError(RuntimeError):
    """A user-facing download failure."""
```

Create `src/scribd_downloader/cli.py`:

```python
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
```

Create `src/scribd_downloader/__main__.py`:

```python
from scribd_downloader.cli import entrypoint


entrypoint()
```

- [ ] **Step 5: Run the focused tests**

Run: `uv run pytest tests/test_cli.py -q`

Expected: 5 passed.

- [ ] **Step 6: Commit the CLI scaffold**

```bash
git add pyproject.toml uv.lock .gitignore README.md src/scribd_downloader tests/test_cli.py
git commit -m "feat: scaffold scribd downloader CLI"
```

---

### Task 2: Camoufox sessions and manual login

**Files:**
- Create: `src/scribd_downloader/browser.py`
- Create: `tests/test_browser.py`

**Interfaces:**
- Consumes: `DownloaderError` from `scribd_downloader.__init__`.
- Produces: `PROFILE_DIR: Path`.
- Produces: `print_preferences(output: Path) -> dict[str, object]`.
- Produces: `launch_options(*, guest: bool, headless: bool, print_path: Path | None = None) -> dict[str, object]`.
- Produces: `login() -> Awaitable[None]`.
- Task 4 extends this module with `download(url, output, guest) -> Awaitable[Path]`.

- [ ] **Step 1: Write option tests that do not launch a browser**

Create `tests/test_browser.py`:

```python
from pathlib import Path

from scribd_downloader.browser import PROFILE_DIR, launch_options, print_preferences


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
```

- [ ] **Step 2: Run the tests and verify the module is missing**

Run: `uv run pytest tests/test_browser.py -q`

Expected: FAIL with `ModuleNotFoundError: scribd_downloader.browser`.

- [ ] **Step 3: Implement browser options and login**

Create `src/scribd_downloader/browser.py`:

```python
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


def launch_options(*, guest: bool, headless: bool, print_path: Path | None = None) -> dict[str, object]:
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
            await asyncio.to_thread(input, "Complete Scribd login in Camoufox, then press Enter here: ")
    except DownloaderError:
        raise
    except Exception as error:
        raise DownloaderError(
            "browser: Camoufox failed; run `uv run camoufox fetch` and retry"
        ) from error
```

The persistent-context branch intentionally uses the object returned by `AsyncCamoufox` as the context. The official API returns a browser context when `persistent_context=True`.

- [ ] **Step 4: Run browser and CLI tests**

Run: `uv run pytest tests/test_browser.py tests/test_cli.py -q`

Expected: 8 passed.

- [ ] **Step 5: Verify the real manual-login window**

Run: `uv run camoufox fetch`

Expected: Camoufox reports an installed official browser.

Run: `uv run scribd-downloader login`

Expected: a visible Camoufox window opens Scribd login; pressing Enter closes it; `~/.scribd-downloader/profile` exists. A real account login is optional for this check.

- [ ] **Step 6: Commit session support**

```bash
git add src/scribd_downloader/browser.py tests/test_browser.py
git commit -m "feat: add Camoufox login sessions"
```

---

### Task 3: Scribd source renderer adapter

**Files:**
- Create: `src/scribd_downloader/scribd.py`
- Create: `tests/test_scribd.py`

**Interfaces:**
- Consumes: Playwright `Page`, `Response`, and `Request` objects.
- Produces: `DocumentRef(document_id: str, embed_url: str)`.
- Produces: `DocumentInfo(document_id: str, title: str, page_count: int, width: float, height: float)`.
- Produces: `ResourceFailure(kind: str, url: str, detail: str)`.
- Produces: `ResourceMonitor.attach(page) -> None` and `.failures -> list[ResourceFailure]`.
- Produces: `parse_document_url(url: str) -> DocumentRef`.
- Produces: `ProgressCallback = Callable[[int, int], None]`.
- Produces: `render_document(page, ref, progress=None) -> Awaitable[DocumentInfo]`.
- Produces: `prepare_print_dom(page, info) -> Awaitable[None]`.

- [ ] **Step 1: Write pure adapter tests**

Create `tests/test_scribd.py`:

```python
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
```

- [ ] **Step 2: Run the tests and verify the adapter is missing**

Run: `uv run pytest tests/test_scribd.py -q`

Expected: FAIL with `ModuleNotFoundError: scribd_downloader.scribd`.

- [ ] **Step 3: Implement URL, state, and resource primitives**

Create the Python portion of `src/scribd_downloader/scribd.py`:

```python
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

from playwright.async_api import Page, Request, Response

from scribd_downloader import DownloaderError


ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class DocumentRef:
    document_id: str
    embed_url: str


@dataclass(frozen=True)
class DocumentInfo:
    document_id: str
    title: str
    page_count: int
    width: float
    height: float


@dataclass(frozen=True)
class ResourceFailure:
    kind: str
    url: str
    detail: str


def parse_document_url(url: str) -> DocumentRef:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if host not in {"scribd.com", "www.scribd.com"}:
        raise DownloaderError("URL: expected a scribd.com document URL")
    match = re.fullmatch(r"/(?:document|embeds)/(\d+)(?:/.*)?", parsed.path)
    if not match:
        raise DownloaderError("URL: only Scribd document and embed URLs are supported")
    document_id = match.group(1)
    return DocumentRef(
        document_id=document_id,
        embed_url=(
            f"https://www.scribd.com/embeds/{document_id}/content"
            "?start_page=1&view_mode=scroll"
        ),
    )


def validate_document_state(document_id: str, state: dict[str, Any]) -> DocumentInfo:
    missing = state.get("missing", [])
    if missing:
        raise DownloaderError(f"render: Scribd interface missing {', '.join(missing)}")
    page_count = int(state.get("pageCount") or 0)
    sizes = [tuple(size) for size in state.get("sizes", [])]
    if page_count < 1 or len(sizes) != page_count:
        raise DownloaderError("render: Scribd did not expose every document page")
    width, height = sizes[0]
    return DocumentInfo(document_id, str(state.get("title") or "").strip(), page_count, width, height)


class ResourceMonitor:
    def __init__(self) -> None:
        self.failures: list[ResourceFailure] = []

    @staticmethod
    def classify(url: str, resource_type: str) -> str | None:
        host = urlsplit(url).hostname or ""
        if not host.endswith("scribdassets.com"):
            return None
        path = urlsplit(url).path.lower()
        if path.endswith(".jsonp") or "/pages/" in path:
            return "page"
        if resource_type == "image" and "/images/" in path:
            return "image"
        if resource_type == "font" or path.endswith((".woff", ".woff2", ".ttf", ".otf")):
            return "font"
        return None

    def record_failure(self, url: str, resource_type: str, detail: str) -> None:
        kind = self.classify(url, resource_type)
        if kind is not None:
            self.failures.append(ResourceFailure(kind, url, detail))

    def attach(self, page: Page) -> None:
        def on_response(response: Response) -> None:
            if response.status >= 400:
                self.record_failure(response.url, response.request.resource_type, f"HTTP {response.status}")

        def on_request_failed(request: Request) -> None:
            self.record_failure(request.url, request.resource_type, request.failure or "request failed")

        page.on("response", on_response)
        page.on("requestfailed", on_request_failed)
```

- [ ] **Step 4: Implement the exact `docManager` loader**

Add these constants and functions to `scribd.py`. Keep the JavaScript here; no other module may refer to `docManager`, `.outer_page`, or `.newpage`.

```python
MANAGER_STATE_SCRIPT = r"""mw:() => {
  const manager = window.docManager;
  const requiredManager = ["pageCount"];
  const requiredPage = ["load", "display", "loadFonts", "turnOnImages"];
  const missing = [];
  if (!manager) return {title: document.title, pageCount: 0, sizes: [], missing: ["window.docManager"]};
  for (const name of requiredManager) {
    if (typeof manager[name] !== "function") missing.push(`docManager.${name}`);
  }
  const pages = Object.values(manager.pages || {}).filter(Boolean).sort((a, b) => a.pageNum - b.pageNum);
  const sample = pages[0];
  for (const name of requiredPage) {
    if (!sample || typeof sample[name] !== "function") missing.push(`page.${name}`);
  }
  for (const page of pages) {
    if (!page.containerElem || typeof page.origWidth !== "number" || typeof page.origHeight !== "number") {
      missing.push(`page.${page.pageNum}.shape`);
    }
  }
  return {
    title: document.title.replace(/\s*[|\-]\s*Scribd.*$/i, "").trim(),
    pageCount: typeof manager.pageCount === "function" ? manager.pageCount() : 0,
    sizes: pages.map((page) => [page.origWidth, page.origHeight]),
    missing: Array.from(new Set(missing)),
  };
}"""

LOAD_BATCH_SCRIPT = r"""mw:async ({start, end}) => {
  const manager = window.docManager;
  manager._removeUnusedPages = () => {};
  const pages = Object.values(manager.pages || {}).filter(Boolean).sort((a, b) => a.pageNum - b.pageNum);
  await Promise.all(pages.slice(start, end).map(async (page) => {
    const fontResult = page.loadFonts();
    if (fontResult && typeof fontResult.then === "function") await fontResult;
    const loadResult = page.load();
    if (loadResult && typeof loadResult.then === "function") await loadResult;
    page.display();
    page.turnOnImages();
  }));
  return pages.slice(start, end).map((page) => page.pageNum);
}"""

BATCH_READY_SCRIPT = r"""mw:({start, end}) => {
  const pages = Object.values(window.docManager.pages || {}).filter(Boolean).sort((a, b) => a.pageNum - b.pageNum);
  return pages.slice(start, end).every((page) => {
    const inner = page.innerPageElem;
    if (!inner || !inner.isConnected || inner.childElementCount === 0) return false;
    return Array.from(inner.querySelectorAll("img")).every(
      (image) => image.complete && image.naturalWidth > 0
    );
  });
}"""


async def wait_for_manager(page: Page, timeout_seconds: float = 60) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_state: dict[str, Any] = {}
    while asyncio.get_running_loop().time() < deadline:
        last_state = await page.evaluate(MANAGER_STATE_SCRIPT)
        if last_state.get("pageCount") and not last_state.get("missing"):
            return last_state
        await asyncio.sleep(0.25)
    missing = ", ".join(last_state.get("missing", [])) or "window.docManager"
    raise DownloaderError(f"render: Scribd initialization timed out ({missing})")


async def wait_for_batch(page: Page, start: int, end: int, timeout_seconds: float = 45) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if await page.evaluate(BATCH_READY_SCRIPT, {"start": start, "end": end}):
            return
        await asyncio.sleep(0.25)
    raise DownloaderError(f"render: pages {start + 1}-{end} did not finish loading")


async def render_document(
    page: Page,
    ref: DocumentRef,
    progress: ProgressCallback | None = None,
) -> DocumentInfo:
    monitor = ResourceMonitor()
    monitor.attach(page)
    response = await page.goto(ref.embed_url, wait_until="domcontentloaded", timeout=120_000)
    if response is None or response.status >= 400:
        status = response.status if response else "no response"
        raise DownloaderError(f"navigation: Scribd returned {status}")

    info = validate_document_state(ref.document_id, await wait_for_manager(page))
    batch_size = 8
    for start in range(0, info.page_count, batch_size):
        end = min(start + batch_size, info.page_count)
        await page.evaluate(LOAD_BATCH_SCRIPT, {"start": start, "end": end})
        await wait_for_batch(page, start, end)
        if progress is not None:
            progress(end, info.page_count)

    await page.evaluate("mw:async () => { await document.fonts.ready; }")
    if monitor.failures:
        failure = monitor.failures[0]
        raise DownloaderError(f"resources: {failure.kind} failed: {failure.detail} ({failure.url})")
    return info
```

- [ ] **Step 5: Implement clean print-DOM preparation**

Add to `scribd.py`:

```python
PREPARE_PRINT_SCRIPT = r"""mw:({pageCount}) => {
  const manager = window.docManager;
  const pages = Object.values(manager.pages || {}).filter(Boolean).sort((a, b) => a.pageNum - b.pageNum);
  if (pages.length !== pageCount) throw new Error(`expected ${pageCount} pages, got ${pages.length}`);
  const sizes = pages.map((page) => {
    const rect = page.containerElem.getBoundingClientRect();
    return [rect.width, rect.height];
  });
  const width = Math.max(...sizes.map((size) => size[0]));
  const height = Math.max(...sizes.map((size) => size[1]));

  const root = document.createElement("main");
  root.id = "scribd-downloader-pages";
  for (const page of pages) root.appendChild(page.containerElem);
  document.body.replaceChildren(root);

  const style = document.createElement("style");
  style.id = "scribd-downloader-print-style";
  style.textContent = `
    @page { size: ${width}px ${height}px; margin: 0; }
    html, body, #scribd-downloader-pages {
      margin: 0 !important; padding: 0 !important; width: ${width}px !important;
      height: auto !important; overflow: visible !important; background: white !important;
    }
    #scribd-downloader-pages > .outer_page {
      display: block !important; position: relative !important;
      margin: 0 !important; padding: 0 !important;
      max-width: ${width}px !important; max-height: ${height}px !important;
      break-after: page; page-break-after: always;
      overflow: hidden !important; box-shadow: none !important;
    }
    #scribd-downloader-pages > .outer_page:last-child {
      break-after: auto; page-break-after: auto;
    }
  `;
  document.head.appendChild(style);
  return {renderedPages: root.children.length, width, height};
}"""


async def prepare_print_dom(page: Page, info: DocumentInfo) -> None:
    try:
        result = await page.evaluate(PREPARE_PRINT_SCRIPT, {"pageCount": info.page_count})
    except Exception as error:
        raise DownloaderError(f"print DOM: {error}") from error
    if result["renderedPages"] != info.page_count:
        raise DownloaderError("print DOM: page count changed during preparation")
```

- [ ] **Step 6: Run unit tests and a live five-page renderer probe**

Run: `uv run pytest tests/test_scribd.py -q`

Expected: 9 passed.

Create `tests/test_live_scribd.py`:

```python
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
```

Run: `SCRIBD_LIVE=1 uv run pytest tests/test_live_scribd.py -q`

Expected: 1 passed; the DOM contains exactly five `.outer_page` nodes; no screenshot file is created.

- [ ] **Step 7: Commit the Scribd adapter**

```bash
git add src/scribd_downloader/scribd.py tests/test_scribd.py tests/test_live_scribd.py
git commit -m "feat: render Scribd page sources"
```

---

### Task 4: Native PDF printing and download orchestration

**Files:**
- Create: `src/scribd_downloader/pdf.py`
- Create: `tests/test_pdf.py`
- Modify: `src/scribd_downloader/browser.py`
- Modify: `tests/test_browser.py`

**Interfaces:**
- Consumes: `parse_document_url`, `render_document`, and `prepare_print_dom` from Task 3.
- Consumes: `default_output_path` from Task 1.
- Produces: `partial_pdf_path(output: Path) -> Path`.
- Produces: `wait_for_pdf(path: Path, timeout_seconds: float = 60) -> Awaitable[None]`.
- Produces: `finalize_pdf(partial: Path, output: Path, expected_pages: int) -> None`.
- Produces: `browser.download(url: str, output: Path | None, guest: bool, progress=None) -> Awaitable[Path]`.

- [ ] **Step 1: Write PDF lifecycle tests**

Create `tests/test_pdf.py`:

```python
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from scribd_downloader import DownloaderError
from scribd_downloader.pdf import finalize_pdf, partial_pdf_path


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
```

Append to `tests/test_browser.py`:

```python
def test_download_uses_guest_option_without_profile(monkeypatch, tmp_path: Path) -> None:
    options = launch_options(
        guest=True,
        headless=True,
        print_path=tmp_path / ".book.partial.pdf",
    )
    assert options["main_world_eval"] is True
    assert "user_data_dir" not in options
    assert "firefox_user_prefs" in options
```

- [ ] **Step 2: Run the PDF tests and verify the module is missing**

Run: `uv run pytest tests/test_pdf.py tests/test_browser.py -q`

Expected: FAIL with `ModuleNotFoundError: scribd_downloader.pdf`.

- [ ] **Step 3: Implement partial-file validation**

Create `src/scribd_downloader/pdf.py`:

```python
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
    previous_size = -1
    stable_checks = 0
    while asyncio.get_running_loop().time() < deadline:
        size = path.stat().st_size if path.exists() else 0
        if size > 0 and size == previous_size:
            stable_checks += 1
            if stable_checks >= 3:
                return
        else:
            stable_checks = 0
        previous_size = size
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
```

- [ ] **Step 4: Implement the complete browser download flow**

Add to `src/scribd_downloader/browser.py`:

```python
from scribd_downloader.cli import default_output_path
from scribd_downloader.pdf import finalize_pdf, partial_pdf_path, wait_for_pdf
from scribd_downloader.scribd import parse_document_url, prepare_print_dom, render_document


async def download(
    url: str,
    output: Path | None,
    guest: bool,
    progress: ProgressCallback | None = None,
) -> Path:
    ref = parse_document_url(url)
    base_dir = (output.expanduser().resolve().parent if output else Path.cwd())
    base_dir.mkdir(parents=True, exist_ok=True)
    partial = (
        partial_pdf_path(output.expanduser().resolve())
        if output
        else base_dir / f".{ref.document_id}.partial.pdf"
    )
    partial.unlink(missing_ok=True)
    try:
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
            final_output = (
                output.expanduser().resolve()
                if output
                else (Path.cwd() / default_output_path(info.title, info.document_id)).resolve()
            )
            final_output.parent.mkdir(parents=True, exist_ok=True)
            await prepare_print_dom(page, info)
            await page.evaluate("mw:window.print()")
            await wait_for_pdf(partial)
            finalize_pdf(partial, final_output, info.page_count)
            return final_output
    except DownloaderError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as error:
        partial.unlink(missing_ok=True)
        raise DownloaderError(f"browser: download failed ({error})") from error
```

- [ ] **Step 5: Run the complete unit suite**

Run: `uv run pytest -q`

Expected: all tests pass.

- [ ] **Step 6: Run the public five-page end-to-end download**

Run:

```bash
uv run scribd-downloader download \
  https://www.scribd.com/document/884183779/Sample-5-Page-PDF \
  --guest \
  -o /tmp/scribd-sample-5-pages.pdf
```

Expected: exit code 0 and `/tmp/scribd-sample-5-pages.pdf` exists.

Run:

```bash
uv run python -c 'from pypdf import PdfReader; p=PdfReader("/tmp/scribd-sample-5-pages.pdf"); print(len(p.pages)); print(len("".join(page.extract_text() or "" for page in p.pages)))'
```

Expected: first line is `5`; second line is greater than zero, proving that textual content was printed as PDF text rather than captured as screenshots.

Run: `find /tmp -maxdepth 1 \( -name '.884183779.partial.pdf' -o -name 'scribd-downloader-*.png' -o -name 'scribd-downloader-*.jpg' \)`

Expected: no partial PDF and no image intermediates created by this run.

- [ ] **Step 7: Commit native PDF output**

```bash
git add src/scribd_downloader/browser.py src/scribd_downloader/pdf.py tests/test_browser.py tests/test_pdf.py
git commit -m "feat: print rendered documents to PDF"
```

---

### Task 5: User documentation and final acceptance

**Files:**
- Modify: `README.md`
- Modify: no runtime files unless a final acceptance command exposes a defect.

**Interfaces:**
- Documents the two commands and the exact security boundary.
- Does not change the CLI contract from Tasks 1-4.

- [ ] **Step 1: Replace the initial README with the usage guide**

Replace `README.md` with these sections and commands:

```markdown
# scribd-downloader

`scribd-downloader` uses Camoufox to load document pages that the current Scribd browser session can read, then prints Scribd's rendered text and image DOM to one PDF. It does not take page screenshots.

## Install

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/).

```console
uv sync
uv run camoufox fetch
```

## Guest download

```console
uv run scribd-downloader download <scribd-document-url> --guest -o document.pdf
```

## Login and reuse the session

```console
uv run scribd-downloader login
uv run scribd-downloader download <scribd-document-url> -o document.pdf
```

The login command opens a visible browser. Enter credentials and any verification code directly on Scribd, then return to the terminal and press Enter. The CLI never receives the credentials.

The browser profile is stored in `~/.scribd-downloader/profile`. It may contain Scribd cookies and session tokens. Keep it private. Delete that directory to remove the local login session.

## Output behavior

- The output is written only after Firefox creates a readable PDF with the expected page count.
- A failed run removes its partial PDF and preserves an existing output file.
- Omit `-o` to use the Scribd title as the filename. An empty title uses the document ID.

## Limits

- Documents only. Books, audiobooks, audio and SlideShare are outside the current scope.
- The tool uses access already available to the active browser session. It does not bypass Scribd permissions or CAPTCHA.
- PDF paper size may differ slightly from the source; page content completeness is the acceptance criterion.
- Scribd's private page renderer can change; an unsupported shape produces an explicit interface error.
```

- [ ] **Step 2: Run static and unit verification**

Run: `uv run pytest -q`

Expected: all tests pass.

Run: `uv run python -m scribd_downloader --help`

Expected: help lists `login` and `download`.

Run: `rg -n "screenshot|\.screenshot\(" src tests README.md`

Expected: the only occurrence is README prose stating that screenshots are not used; runtime code contains no screenshot API call.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 3: Repeat the real guest acceptance test**

Run the Task 4 five-page command again after removing only the prior `/tmp/scribd-sample-5-pages.pdf` test artifact.

Expected: exit code 0, exactly 5 PDF pages, extracted text length greater than zero, no `.partial.pdf`.

- [ ] **Step 4: Verify persistent mode without exposing credentials**

Run: `uv run scribd-downloader login` and close after terminal confirmation.

Run the same public document without `--guest`:

```bash
uv run scribd-downloader download \
  https://www.scribd.com/document/884183779/Sample-5-Page-PDF \
  -o /tmp/scribd-session-sample.pdf
```

Expected: exit code 0 and five PDF pages. Inspect terminal output to confirm it contains no Cookie, authorization header, password, token, or profile contents.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md
git commit -m "docs: add Scribd downloader usage"
```

- [ ] **Step 6: Final repository review**

Run:

```bash
git status --short
git log --oneline --decorate -6
uv run pytest -q
```

Expected: clean working tree; the design, plan, scaffold, session, renderer, PDF, and README commits are present; all tests pass.

Do not push or create a remote unless the user asks.
