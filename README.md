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
