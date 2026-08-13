from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
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
    title = str(state.get("title") or "").strip()
    if title.casefold() == "scribd":
        title = ""
    return DocumentInfo(document_id, title, page_count, width, height)


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
        if "/webpack/" not in path and (
            resource_type == "font" or path.endswith((".woff", ".woff2", ".ttf", ".otf"))
        ):
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
  const batch = pages.slice(start, end);
  await Promise.all(batch.map(async (page) => {
    if (page.innerPageElem || page.loadHasStarted) return;
    const fontResult = page.loadFonts();
    if (fontResult && typeof fontResult.then === "function") await fontResult;
    const loadResult = page.load();
    if (loadResult && typeof loadResult.then === "function") await loadResult;
  }));
  const deadline = Date.now() + 45000;
  while (batch.some((page) => !page.innerPageElem || !page.innerPageElem.isConnected)) {
    if (Date.now() >= deadline) throw new Error(`pages ${start + 1}-${end} did not finish loading`);
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  for (const page of batch) {
    page.display();
    page.turnOnImages();
  }
  return batch.map((page) => page.pageNum);
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
        try:
            last_state = await page.evaluate(MANAGER_STATE_SCRIPT)
        except PlaywrightError as error:
            detail = str(error)
            lowered = detail.casefold()
            if "execution context was destroyed" not in lowered:
                raise DownloaderError(f"render: Scribd initialization failed: {detail}") from error
            await asyncio.sleep(0.25)
            continue
        if last_state.get("pageCount") and not last_state.get("missing"):
            return last_state
        await asyncio.sleep(0.25)
    missing = ", ".join(last_state.get("missing", [])) or "window.docManager"
    raise DownloaderError(f"render: Scribd initialization timed out ({missing})")


async def wait_for_batch(page: Page, start: int, end: int, timeout_seconds: float = 45) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        try:
            ready = await page.evaluate(BATCH_READY_SCRIPT, {"start": start, "end": end})
        except PlaywrightError as error:
            raise DownloaderError(
                f"render: pages {start + 1}-{end} readiness failed: {error}"
            ) from error
        if ready:
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
    try:
        response = await page.goto(ref.embed_url, wait_until="domcontentloaded", timeout=120_000)
    except PlaywrightError as error:
        raise DownloaderError(f"navigation: Scribd navigation failed: {error}") from error
    if response is None or response.status >= 400:
        status = response.status if response else "no response"
        raise DownloaderError(f"navigation: Scribd returned {status}")

    info = validate_document_state(ref.document_id, await wait_for_manager(page))
    batch_size = 8
    for start in range(0, info.page_count, batch_size):
        end = min(start + batch_size, info.page_count)
        try:
            await page.evaluate(LOAD_BATCH_SCRIPT, {"start": start, "end": end})
        except PlaywrightError as error:
            raise DownloaderError(
                f"render: pages {start + 1}-{end} loading failed: {error}"
            ) from error
        await wait_for_batch(page, start, end)
        if progress is not None:
            progress(end, info.page_count)

    try:
        await page.evaluate("mw:async () => { await document.fonts.ready; }")
    except PlaywrightError as error:
        raise DownloaderError(f"render: document fonts failed: {error}") from error
    if monitor.failures:
        failure = monitor.failures[0]
        raise DownloaderError(f"resources: {failure.kind} failed: {failure.detail} ({failure.url})")
    return info


PREPARE_PRINT_SCRIPT = r"""mw:({pageCount}) => {
  const manager = window.docManager;
  const pages = Object.values(manager.pages || {}).filter(Boolean).sort((a, b) => a.pageNum - b.pageNum);
  if (pages.length !== pageCount) throw new Error(`expected ${pageCount} pages, got ${pages.length}`);
  const layouts = pages.map((page) => {
    const rect = page.containerElem.getBoundingClientRect();
    return {page, width: rect.width, height: rect.height};
  });
  const width = Math.max(...layouts.map((layout) => layout.width));
  const height = Math.max(...layouts.map((layout) => layout.height));

  const root = document.createElement("main");
  root.id = "scribd-downloader-pages";
  for (const {page, width: pageWidth, height: pageHeight} of layouts) {
    const element = page.containerElem;
    element.style.setProperty("box-sizing", "border-box", "important");
    element.style.setProperty("width", `${pageWidth}px`, "important");
    element.style.setProperty("height", `${pageHeight}px`, "important");
    element.style.setProperty("min-width", `${pageWidth}px`, "important");
    element.style.setProperty("min-height", `${pageHeight}px`, "important");
    root.appendChild(element);
  }
  document.body.replaceChildren(root);

  const style = document.createElement("style");
  style.id = "scribd-downloader-print-style";
  style.textContent = `
    @page { size: ${width}px ${height}px; margin: 0; }
    html, body, #scribd-downloader-pages {
      margin: 0 !important; padding: 0 !important; width: ${width}px !important;
      height: auto !important; overflow: visible !important; background: white !important;
    }
    #scribd-downloader-pages > * {
      display: block !important; position: relative !important;
      margin: 0 !important;
      break-after: page; page-break-after: always;
      overflow: visible !important; box-shadow: none !important;
    }
    #scribd-downloader-pages > *:last-child {
      break-after: auto; page-break-after: auto;
    }
  `;
  document.head.appendChild(style);
  void root.offsetHeight;

  const layoutFailures = [];
  const format = (value) => Number.isInteger(value) ? String(value) : value.toFixed(2);
  for (const {page, width: pageWidth, height: pageHeight} of layouts) {
    const element = page.containerElem;
    const rect = element.getBoundingClientRect();
    if (Math.abs(rect.width - pageWidth) > 0.5 || Math.abs(rect.height - pageHeight) > 0.5) {
      layoutFailures.push(
        `page ${page.pageNum} border box changed from ${format(pageWidth)}x${format(pageHeight)} ` +
        `to ${format(rect.width)}x${format(rect.height)}`
      );
    }
    if (element.scrollWidth > element.clientWidth || element.scrollHeight > element.clientHeight) {
      layoutFailures.push(
        `page ${page.pageNum} content ${element.scrollWidth}x${element.scrollHeight} exceeds visible box ` +
        `${element.clientWidth}x${element.clientHeight}`
      );
    }
  }
  return {renderedPages: root.children.length, width, height, layoutFailures};
}"""


async def prepare_print_dom(page: Page, info: DocumentInfo) -> None:
    try:
        result = await page.evaluate(PREPARE_PRINT_SCRIPT, {"pageCount": info.page_count})
    except Exception as error:
        raise DownloaderError(f"print DOM: {error}") from error
    if result["renderedPages"] != info.page_count:
        raise DownloaderError("print DOM: page count changed during preparation")
    if result.get("layoutFailures"):
        raise DownloaderError(f"print DOM: {result['layoutFailures'][0]}")
