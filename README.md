# scribd-downloader

[English](#english) | [简体中文](#简体中文)

## English

`scribd-downloader` uses Camoufox to load document pages that the current Scribd browser session can read, then prints Scribd's rendered text and image DOM to one PDF. It does not take page screenshots.

### Install

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/).

```console
uv sync
uv run camoufox fetch
```

### Guest download

```console
uv run scribd-downloader download <scribd-document-url> --guest -o document.pdf
```

### Login and reuse the session

```console
uv run scribd-downloader login
uv run scribd-downloader download <scribd-document-url> -o document.pdf
```

The login command opens a visible browser. Enter credentials and any verification code directly on Scribd, then return to the terminal and press Enter. The CLI never receives the credentials.

The browser profile is stored in `~/.scribd-downloader/profile`. It may contain Scribd cookies and session tokens. Keep it private. Delete that directory to remove the local login session.

### Output behavior

- The output is written only after Firefox creates a readable PDF with the expected page count.
- A failed run removes its partial PDF and preserves an existing output file.
- Omit `-o` to use the Scribd title as the filename. An empty title uses the document ID.

### Limits

- Documents only. Books, audiobooks, audio and SlideShare are outside the current scope.
- The tool uses access already available to the active browser session. It does not bypass Scribd permissions or CAPTCHA.
- PDF paper size may differ slightly from the source; page content completeness is the acceptance criterion.
- Scribd's private page renderer can change; an unsupported shape produces an explicit interface error.

## 简体中文

`scribd-downloader` 使用 Camoufox 加载当前 Scribd 浏览器会话有权阅读的文档页面，然后将 Scribd 渲染出的文本和图片 DOM 打印到一个 PDF 文件中。它不会截取页面截图。

### 安装

环境要求：Python 3.12 和 [uv](https://docs.astral.sh/uv/)。

```console
uv sync
uv run camoufox fetch
```

### 游客模式下载

```console
uv run scribd-downloader download <scribd-document-url> --guest -o document.pdf
```

### 登录并复用会话

```console
uv run scribd-downloader login
uv run scribd-downloader download <scribd-document-url> -o document.pdf
```

登录命令会打开一个可见的浏览器窗口。请直接在 Scribd 页面中输入账号、密码及验证码，然后返回终端并按 Enter。命令行工具不会接触你的登录凭据。

浏览器配置保存在 `~/.scribd-downloader/profile`。其中可能包含 Scribd Cookie 和会话令牌，请妥善保管。删除该目录即可移除本地登录会话。

### 输出行为

- 只有当 Firefox 生成可正常读取、且页数符合预期的 PDF 后，程序才会写入输出文件。
- 运行失败时，程序会删除未完成的 PDF，并保留原有输出文件。
- 省略 `-o` 时，程序会使用 Scribd 文档标题作为文件名；如果标题为空，则使用文档 ID。

### 使用限制

- 仅支持文档，不支持图书、有声书、音频和 SlideShare。
- 本工具只使用当前浏览器会话已有的访问权限，不会绕过 Scribd 权限控制或 CAPTCHA。
- PDF 纸张尺寸可能与源文档略有不同；验收标准是页面内容完整。
- Scribd 的私有页面渲染器可能发生变化；遇到不支持的数据结构时，程序会明确报告接口错误。
