# Browser Server API

## Base URL

`http://<host>:<port>`

Defaults:

- BROWSER_HOST: `0.0.0.0`
- BROWSER_PORT: `3456`
- BROWSER_USER_DATA_DIR: `./user_data`
- BROWSER_HEADLESS: `true`
- BROWSER_AUTO_START: `true`
- BROWSER_CHANNEL: `chrome`

## Endpoints

## Quickstart (PowerShell)

```powershell
$base = "http://localhost:3456"

# 1) 启动浏览器（可省略，默认 AUTO_START=true）
Invoke-RestMethod -Uri "$base/start" -Method POST -ContentType "application/json" -Body '{"headless":false,"channel":"chrome"}'

# 2) 访问页面
Invoke-RestMethod -Uri "$base/navigate" -Method POST -ContentType "application/json" -Body '{"url":"https://example.com","wait_until":"networkidle","extra_wait_ms":1000}'

# 3) 新建标签并切换
Invoke-RestMethod -Uri "$base/page/new" -Method POST -ContentType "application/json" -Body '{"url":"https://www.wikipedia.org"}'

# 4) 列出标签
Invoke-RestMethod -Uri "$base/pages" -Method GET

# 5) 切换到指定标签
Invoke-RestMethod -Uri "$base/page/switch" -Method POST -ContentType "application/json" -Body '{"id":0}'

# 6) 获取当前页信息
Invoke-RestMethod -Uri "$base/current?include_text=true" -Method GET

# 7) 截图
Invoke-RestMethod -Uri "$base/screenshot" -Method POST -ContentType "application/json" -Body '{"full_page":true}' | % { [IO.File]::WriteAllBytes("screenshot.png",[Convert]::FromBase64String($_.image_base64)) }

# 8) 等待元素与点击
Invoke-RestMethod -Uri "$base/wait" -Method POST -ContentType "application/json" -Body '{"selector":"h1","timeout":10000}'
Invoke-RestMethod -Uri "$base/click" -Method POST -ContentType "application/json" -Body '{"selector":"a"}'

# 9) 通过 CDP 调用 DevTools（示例：获取版本）
Invoke-RestMethod -Uri "$base/cdp/version" -Method GET

# 10) 通过 CDP 调用 DevTools（示例：启用 Network 并获取性能指标）
Invoke-RestMethod -Uri "$base/cdp/send" -Method POST -ContentType "application/json" -Body '{"method":"Network.enable"}'
Invoke-RestMethod -Uri "$base/cdp/send" -Method POST -ContentType "application/json" -Body '{"method":"Performance.getMetrics"}'

# 11) 弹窗等待与处理（示例：alert/confirm/prompt）
Invoke-RestMethod -Uri "$base/dialog/await" -Method POST -ContentType "application/json" -Body '{"timeout":10000,"action":"accept"}'

# 12) 关闭其他标签或当前页面
Invoke-RestMethod -Uri "$base/page/close_others" -Method POST
Invoke-RestMethod -Uri "$base/page/close" -Method POST

# 13) 设置下载目录
Invoke-RestMethod -Uri "$base/download/dir" -Method POST -ContentType "application/json" -Body '{"path":"./downloads"}'

# 14) 查看最近下载
Invoke-RestMethod -Uri "$base/downloads/last" -Method GET

# 15) 等待下载完成
Invoke-RestMethod -Uri "$base/download/await" -Method POST -ContentType "application/json" -Body '{"timeout":30000}'

# 16) 导出存储状态（cookie、localStorage 等）
Invoke-RestMethod -Uri "$base/storage/export" -Method POST -ContentType "application/json" -Body '{"include_json":true}'

# 17) 健康检查
Invoke-RestMethod -Uri "$base/health" -Method GET
```

## Quickstart (curl)

```bash
base="http://localhost:3456"

# 1) 启动浏览器（可省略）
curl -s "$base/start" -X POST -H "Content-Type: application/json" -d '{"headless":false,"channel":"chrome"}'

# 2) 访问页面
curl -s "$base/navigate" -X POST -H "Content-Type: application/json" -d '{"url":"https://example.com","wait_until":"networkidle","extra_wait_ms":1000}'

# 3) 新建标签并切换
curl -s "$base/page/new" -X POST -H "Content-Type: application/json" -d '{"url":"https://www.wikipedia.org"}'

# 4) 列出标签
curl -s "$base/pages"

# 5) 切换到指定标签
curl -s "$base/page/switch" -X POST -H "Content-Type: application/json" -d '{"id":0}'

# 6) 获取当前页信息
curl -s "$base/current?include_text=true"

# 7) 截图到文件
img64=$(curl -s "$base/screenshot" -X POST -H "Content-Type: application/json" -d '{"full_page":true}' | jq -r '.image_base64')
echo "$img64" | base64 -d > screenshot.png

# 8) 等待元素与点击
curl -s "$base/wait" -X POST -H "Content-Type: application/json" -d '{"selector":"h1","timeout":10000}'
curl -s "$base/click" -X POST -H "Content-Type: application/json" -d '{"selector":"a"}'

# 9) 通过 CDP 调用 DevTools（示例：获取版本）
curl -s "$base/cdp/version"

# 10) 通过 CDP 调用 DevTools（示例：启用 Network 并获取性能指标）
curl -s "$base/cdp/send" -X POST -H "Content-Type: application/json" -d '{"method":"Network.enable"}'
curl -s "$base/cdp/send" -X POST -H "Content-Type: application/json" -d '{"method":"Performance.getMetrics"}'

# 11) 弹窗等待与处理（示例：alert/confirm/prompt）
curl -s "$base/dialog/await" -X POST -H "Content-Type: application/json" -d '{"timeout":10000,"action":"accept"}'

# 12) 关闭其他标签或当前页面
curl -s "$base/page/close_others" -X POST
curl -s "$base/page/close" -X POST

# 13) 设置下载目录
curl -s "$base/download/dir" -X POST -H "Content-Type: application/json" -d '{"path":"./downloads"}'

# 14) 查看最近下载
curl -s "$base/downloads/last"

# 15) 等待下载完成
curl -s "$base/download/await" -X POST -H "Content-Type: application/json" -d '{"timeout":30000}'

# 16) 导出存储状态
curl -s "$base/storage/export" -X POST -H "Content-Type: application/json" -d '{"include_json":true}'

# 17) 健康检查
curl -s "$base/health"

# 18) 队列状态
curl -s "$base/queue/status"

# 19) 获取完整说明文档
curl -s "$base/docs/raw"
```

### GET /

Service info and current browser status.

Response:

- service
- version
- status
- browser: same as GET /health

Example:

```bash
curl -s "$base/"
```

### GET /health

Current browser status.

Response:

- running
- url
- title
- headless
- user_data_dir

Example:

```bash
curl -s "$base/health"
```

### GET /queue/status

Queue status.
This endpoint does not enter the request queue.

Response:

- success
- current_request_id
- queue_length
- waiting

Example:

```bash
curl -s "$base/queue/status"
```

### GET /docs/raw

Return full API documentation (plain text).
This endpoint does not enter the request queue.

Example:

```bash
curl -s "$base/docs/raw"
```

### Queue bypass endpoints

- /
- /health
- /queue/status
- /docs/raw
- /downloads
- /downloads/last

### Queue headers

Every response includes:

- X-Queue-Request-Id
- X-Queue-Start-Position
- X-Queue-Wait-Ms

### POST /start

Start browser with a persistent profile.

Body:

- headless: boolean, optional
- user_data_dir: string, optional
- user_agent: string, optional
- channel: string, optional

Response:

- success
- message
- headless
- user_data_dir

Example:

```bash
curl -s "$base/start" -X POST -H "Content-Type: application/json" -d '{"headless":false,"channel":"chrome"}'
```

### POST /stop

Stop browser. This does not stop the service process.

Response:

- success
- message

Example:

```bash
curl -s "$base/stop" -X POST
```

### POST /navigate

Navigate to a URL.

Body:

- url: string, required
- wait_until: string, default `networkidle`
- timeout: number, default `60000`
- extra_wait_ms: number, default `3000`

Response:

- success
- url
- title

Example:

```bash
curl -s "$base/navigate" -X POST -H "Content-Type: application/json" -d '{"url":"https://example.com","wait_until":"networkidle","extra_wait_ms":1000}'
```

### POST /evaluate

Evaluate JavaScript in page context.

Body:

- script: string, required
- args: array, optional
- timeout: number, default `30000`

Response:

- success
- result

Example:

```bash
curl -s "$base/evaluate" -X POST -H "Content-Type: application/json" -d '{"script":"() => document.title"}'
```

### GET /cdp/version

Get DevTools version via CDP.

Response:

- success
- version

Example:

```bash
curl -s "$base/cdp/version"
```

### POST /cdp/send

Send a CDP command to the current page.

Body:

- method: string, required (CDP method name)
- params: object, optional
- timeout: number, default `30000`

Response:

- success
- result

Example:

```bash
curl -s "$base/cdp/send" -X POST -H "Content-Type: application/json" -d '{"method":"Network.enable"}'
```

### POST /cdp/dom/text

Get element textContent via CDP.

Body:

- selector: string, required
- timeout: number, default `30000`

Response:

- success
- text
- length

Example:

```bash
curl -s "$base/cdp/dom/text" -X POST -H "Content-Type: application/json" -d '{"selector":"h1"}'
```

### POST /cdp/dom/html

Get element outerHTML via CDP.

Body:

- selector: string, required
- timeout: number, default `30000`

Response:

- success
- html
- length

Example:

```bash
curl -s "$base/cdp/dom/html" -X POST -H "Content-Type: application/json" -d '{"selector":"body"}'
```

### POST /cdp/dom/attributes

Get element attributes via CDP.

Body:

- selector: string, required
- timeout: number, default `30000`

Response:

- success
- attributes

Example:

```bash
curl -s "$base/cdp/dom/attributes" -X POST -H "Content-Type: application/json" -d '{"selector":"a"}'
```

### POST /upload

Upload file(s) to input[type=file].

Body:

- selector: string, required
- paths: array of string, required
- timeout: number, default `30000`

Response:

- success
- count

Example:

```bash
curl -s "$base/upload" -X POST -H "Content-Type: application/json" -d '{"selector":"input[type=file]","paths":["./sample.txt"]}'
```

### POST /download/dir

Set download directory.

Body:

- path: string, optional

Response:

- success
- download_dir

Example:

```bash
curl -s "$base/download/dir" -X POST -H "Content-Type: application/json" -d '{"path":"./downloads"}'
```

### GET /downloads

Get download history.

Response:

- success
- downloads

Example:

```bash
curl -s "$base/downloads"
```

### GET /downloads/last

Get last downloaded file.

Response:

- success
- download

Example:

```bash
curl -s "$base/downloads/last"
```

### POST /download/await

Wait for a download to complete.

Body:

- timeout: number, default `30000`

Response:

- success
- download

Example:

```bash
curl -s "$base/download/await" -X POST -H "Content-Type: application/json" -d '{"timeout":30000}'
```

### POST /dialog/await

Wait for dialog.

Body:

- timeout: number, default `30000`
- action: string, optional (`accept` or `dismiss`)
- prompt_text: string, optional

Response:

- success
- type
- message
- default_value
- handled (when action provided)

Example:

```bash
curl -s "$base/dialog/await" -X POST -H "Content-Type: application/json" -d '{"timeout":10000,"action":"accept"}'
```

### POST /dialog/accept

Accept dialog.

Body:

- prompt_text: string, optional

Response:

- success

Example:

```bash
curl -s "$base/dialog/accept" -X POST -H "Content-Type: application/json" -d '{"prompt_text":"ok"}'
```

### POST /dialog/dismiss

Dismiss dialog.

Response:

- success

Example:

```bash
curl -s "$base/dialog/dismiss" -X POST
```

### POST /element/box

Get element bounding box.

Body:

- selector: string, required
- timeout: number, default `30000`

Response:

- success
- box

Example:

```bash
curl -s "$base/element/box" -X POST -H "Content-Type: application/json" -d '{"selector":"h1"}'
```

### POST /click/point

Click at viewport coordinates.

Body:

- x: number, required
- y: number, required
- button: string, default `left`
- clicks: number, default `1`
- delay: number, default `0`

Response:

- success

Example:

```bash
curl -s "$base/click/point" -X POST -H "Content-Type: application/json" -d '{"x":120,"y":220,"button":"left","clicks":1}'
```
### GET /text

Get page text.

Query:

- selector: string, optional
- timeout: number, default `30000`

Response:

- success
- text
- length

Example:

```bash
curl -s "$base/text"
```

### GET /current

Get current page info and optional content.

Query:

- include_html: boolean, default `false`
- include_text: boolean, default `false`
- selector: string, optional
- timeout: number, default `30000`

Response:

- success
- url
- title
- html, html_length (when include_html=true)
- text, text_length (when include_text=true)

Example:

```bash
curl -s "$base/current?include_text=true"
```

### GET /pages

List all tabs.

Response:

- success
- pages: array of { id, url, title, current }

Example:

```bash
curl -s "$base/pages"
```

### POST /page/new

Open a new tab and optionally navigate.

Body:

- url: string, optional
- wait_until: string, default `networkidle`
- timeout: number, default `60000`
- extra_wait_ms: number, default `3000`

Response:

- success
- id
- url
- title

Example:

```bash
curl -s "$base/page/new" -X POST -H "Content-Type: application/json" -d '{"url":"https://example.com"}'
```

### POST /page/switch

Switch current tab.

Body:

- id: number, required

Response:

- success
- current_id
- url
- title

Example:

```bash
curl -s "$base/page/switch" -X POST -H "Content-Type: application/json" -d '{"id":0}'
```

### POST /page/close

Close current page.

Response:

- success
- remaining_pages

Example:

```bash
curl -s "$base/page/close" -X POST
```

### POST /page/close_others

Close all tabs except current.

Response:

- success
- remaining_pages

Example:

```bash
curl -s "$base/page/close_others" -X POST
```

### POST /screenshot

Take screenshot.

Body:

- full_page: boolean, default `true`
- selector: string, optional
- timeout: number, default `60000`

Response:

- success
- image_base64
- mime_type
- size

Example:

```bash
curl -s "$base/screenshot" -X POST -H "Content-Type: application/json" -d '{"full_page":true}'
```

### POST /wait

Wait for selector or text.

Body:

- selector: string, optional
- text: string, optional
- timeout: number, default `30000`

Response:

- success
- message

Example:

```bash
curl -s "$base/wait" -X POST -H "Content-Type: application/json" -d '{"selector":"h1","timeout":10000}'
```

### POST /click

Click element.

Body:

- selector: string, required
- timeout: number, default `10000`

Response:

- success

Example:

```bash
curl -s "$base/click" -X POST -H "Content-Type: application/json" -d '{"selector":"a"}'
```

### POST /type

Type into element.

Body:

- selector: string, required
- text: string, required
- timeout: number, default `10000`
- clear_first: boolean, default `true`

Response:

- success

Example:

```bash
curl -s "$base/type" -X POST -H "Content-Type: application/json" -d '{"selector":"input[name=q]","text":"hello"}'
```

### POST /scroll

Scroll page.

Body:

- direction: string, default `down`
- to_bottom: boolean, default `false`
- amount: number, optional

Response:

- success

Example:

```bash
curl -s "$base/scroll" -X POST -H "Content-Type: application/json" -d '{"direction":"down","amount":600}'
```

### POST /storage/export

Export storage state.

Body:

- path: string, optional
- include_json: boolean, default `false`

Response:

- success
- path
- storage_state (when include_json=true)

Example:

```bash
curl -s "$base/storage/export" -X POST -H "Content-Type: application/json" -d '{"include_json":true}'
```
