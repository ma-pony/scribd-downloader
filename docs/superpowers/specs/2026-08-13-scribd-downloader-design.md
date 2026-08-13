# scribd-downloader 设计说明

日期：2026-08-13
状态：待实现

## 1. 目标

创建一个 Python 命令行项目，使用官方 `camoufox` 包访问 Scribd，并把当前浏览器会话可阅读的文档导出为单个 PDF。

首版支持两种会话：

- 访客模式：使用临时浏览器配置访问公开文档。
- 登录模式：用户在可见的 Camoufox 窗口中手工登录，后续下载复用本地浏览器配置。

PDF 来自 Scribd 已渲染的页面 DOM。程序触发并检查 JSONP、图片、字体等页面资源，然后调用 Firefox 原生打印。实现中不使用逐页截图，也不保存账号或密码。

## 2. 范围

### 2.1 命令

```console
scribd-downloader login
scribd-downloader download <URL> [-o OUTPUT.pdf] [--guest]
```

`login` 执行以下操作：

1. 以有界面模式打开 Camoufox。
2. 使用 `~/.scribd-downloader/profile` 作为持久化浏览器配置。
3. 打开 Scribd 登录页，等待用户完成登录并在终端确认。
4. 关闭浏览器。Cookie 和站点存储保留在该配置目录中。

`download` 默认复用持久化配置。`--guest` 改用临时配置，不读取登录会话。未提供 `-o` 时，文件名取文档标题；无法取得标题时使用 Scribd 文档 ID。

### 2.2 首版不做

- 不绕过付费权限、验证码或 Scribd 的访问控制。
- 不下载 Scribd 原始上传文件。
- 不逐页截图，不把页面栅格化后再合并。
- 不实现纯 HTTP 备用下载器。
- 不支持书籍、音频、有声书和幻灯片等其他产品页面。
- 不处理同一文档内混合纸张尺寸。
- 不为超大文档实现磁盘分页缓存或分段合并。

## 3. 技术基线

- Python 3.12
- `camoufox==0.5.4`
- `pypdf`，只用于验证生成结果
- 标准库 `argparse`，不引入额外 CLI 框架
- `uv` 管理依赖和命令入口

选择 `camoufox==0.5.4` 是为了使用 daijro 发布的官方包及其 `playwright<1.61` 约束。当前 Camoufox Firefox 协议不接受 Playwright 1.61 起发送的 `isMobile` 参数，保持该依赖边界可以避免创建页面时报协议错误。

首次安装需要执行：

```console
uv sync
uv run camoufox fetch
```

## 4. 项目结构

```text
scribd-downloader/
├── pyproject.toml
├── README.md
├── src/scribd_downloader/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── browser.py
│   ├── scribd.py
│   └── pdf.py
└── tests/
    ├── test_cli.py
    └── test_scribd.py
```

职责划分：

- `cli.py`：解析参数、选择会话模式、生成默认输出路径、设置退出码。
- `browser.py`：创建 Camoufox、管理持久化配置、设置 Firefox 静默打印参数。
- `scribd.py`：解析文档 URL、打开嵌入页、驱动 Scribd 页面管理器、检查资源加载状态、整理打印 DOM。
- `pdf.py`：写入临时 PDF、验证 PDF 页数、原子移动到目标路径。

Scribd 私有页面接口只出现在 `scribd.py`。站点结构变化时，修改范围保持在这个模块内。

## 5. 下载数据流

### 5.1 打开文档

1. 从输入 URL 提取数字文档 ID。
2. 构造 Scribd 嵌入页 URL，通过 Camoufox 打开。
3. 等待页面完成客户端挑战，并确认 `window.docManager` 已创建。
4. 读取页面总数、标题、第一页原始宽高。

页面停留在挑战页、登录页或错误页时，命令直接失败并给出当前状态，不继续生成 PDF。

### 5.2 触发源码渲染

程序遍历 `window.docManager.pages`，调用 Scribd 页面对象提供的加载和显示方法：

1. 按小批次调用页面对象的加载和显示方法，避免同时发起全部网络请求。
2. 监听网络响应，记录页面 JSONP、图片和字体的 URL、状态码与失败原因。
3. 等待每个页面生成 `.outer_page` 和内部页面 DOM。
4. 等待该页图片完成加载，并等待 `document.fonts.ready`。
5. 保留已渲染的页面节点，供一次性打印。

这里由 Scribd 的脚本解释页面 JSONP，并生成绝对定位的文本和图片节点。程序不重新实现坐标排版，也不从像素结果反推页面内容。

完成加载必须同时满足：

- 已渲染页面数等于 `docManager` 报告的页面总数。
- 每页都有可打印的内部 DOM。
- 页面 JSONP 没有网络失败。
- 页面引用的图片没有加载失败。
- 字体加载过程已结束。

任一条件失败，命令退出且不保留目标 PDF。

### 5.3 整理打印页面

全部页面加载后，程序在当前文档中执行以下调整：

- 移除工具栏、推荐内容、广告和非文档节点。
- 取消阅读器滚动容器的固定高度与裁剪。
- 保持页面原始宽高、背景、文本层、图片层和层叠顺序。
- 为每个 `.outer_page` 设置打印分页边界。
- 使用第一页的宽高配置 PDF 打印纸张。

首版假设同一文档的页面尺寸一致。发现不同尺寸时给出明确错误。

### 5.4 原生打印与验证

Camoufox 启动时设置 Firefox 静默打印参数，打印目标是 `Mozilla Save to PDF`。打印先写入目标目录中的临时文件：

```text
.<output-name>.partial.pdf
```

打印完成后，`pypdf` 执行以下检查：

- 文件存在且大小大于零。
- 文件可以解析。
- PDF 页数等于 Scribd 页面总数。

检查通过后再原子重命名为最终文件。检查失败时删除临时文件，保留已有的同名最终文件。

## 6. 登录与本地数据

登录由用户在 Camoufox 窗口中完成。项目不接收账号、密码或二次验证码。持久化目录可能包含 Cookie 和登录令牌，README 需要提醒用户保护该目录，并提供退出登录的最小操作：删除 `~/.scribd-downloader/profile`。

下载行为只使用当前会话已经取得的访问权限。文档在访客模式不可读时，错误信息建议用户运行 `scribd-downloader login` 后重试。

## 7. 错误处理

首版覆盖以下失败：

- URL 中没有可识别的 Scribd 文档 ID。
- Camoufox 浏览器文件尚未安装。
- 客户端挑战、登录或文档初始化超时。
- 当前会话无权读取文档。
- JSONP、图片或字体加载失败。
- 页面数量或页面尺寸不一致。
- Firefox 没有产生 PDF。
- PDF 无法解析或页数不一致。

参数错误使用退出码 `2`，下载或打印失败使用退出码 `1`，成功使用退出码 `0`。错误输出包含失败阶段和下一步操作，不输出 Cookie、令牌或完整浏览器配置。

## 8. 验收标准

### 8.1 访客下载

对一个可公开阅读的 Scribd 文档执行：

```console
scribd-downloader download <public-document-url> -o public.pdf --guest
```

结果应满足：

- 命令退出码为 `0`。
- 生成一个可打开的 PDF。
- PDF 页数与 Scribd 页面管理器报告值相同。
- 文本型页面在 PDF 中保留可选择文本。
- 代码不调用截图 API，输出链路不生成图片中间文件。

### 8.2 登录会话

1. 运行 `scribd-downloader login`，手工完成登录。
2. 确认 `~/.scribd-downloader/profile` 已创建。
3. 运行不带 `--guest` 的 `download`。
4. 确认下载进程复用现有会话，且 CLI 没有请求账号或密码。

### 8.3 失败清理

人为阻断一个页面资源后，命令应返回 `1`，指出失败的页面或资源类型，不留下 `.partial.pdf`，也不覆盖原有目标文件。

## 9. 已知风险

Scribd 的 `docManager`、页面对象方法和 DOM 类名属于站点私有实现，后续可能变化。首版采用显式结构检查；不匹配时停止并报告检测到的对象和缺失字段。

Firefox 原生打印依赖浏览器打印参数。实现阶段需要用一份公开文档做真实打印测试，确认背景、页面尺寸、分页和字体结果。测试结果不满足验收标准时，应先修正打印 CSS 或 Firefox 参数，再扩展其他功能。

大型文档会同时保留全部页面 DOM，内存随页数增长。首版以普通文档为目标，不加入复杂的分段打印与 PDF 合并流程。
