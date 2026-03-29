---
name: "browser-cli"
description: "Controls Browser Server with browser-cli on Windows or Linux. Invoke when user wants terminal browser automation (start, navigate, evaluate, mcp) instead of raw HTTP requests."
---

# Browser CLI

Use this skill when you need to control Browser Server through terminal commands on either Windows or Linux.

## Preconditions

- Browser Server is running and reachable
- `browser-cli` is installed from `browser-cli/install-windows.ps1` or `browser-cli/install-linux.sh`

## Default Target

- Base URL comes from `BROWSER_SERVER_URL`
- If not set, defaults to `http://192.168.31.118:3456`

## Help

```bash
browser-cli --help
browser-cli apis --help
browser-cli apis
browser-cli apis --json
browser-cli start --help
browser-cli navigate --help
browser-cli mcp-call --help
browser-cli install --help
```

`--help` 提供常用命令与示例；全量接口请用 `browser-cli apis` 查看。

## Install

### Linux

```bash
browser-cli install --base-url "http://192.168.31.118:3456"
source ~/.bashrc
```

### Windows

```powershell
browser-cli install --base-url "http://192.168.31.118:3456"
browser-cli install --base-url "http://192.168.31.118:3456" --machine
```

## Common Commands

默认先用 `navigate`，遇到机器人/反爬拦截再切换到 MCP。
例如 Reuters / DataDome 场景直接用 `mcp-open`，接口会自动确保 MCP 已启动。

### Linux

#### 传统流程（默认）

```bash
browser-cli health
browser-cli start --headless false --engine patchright --channel chrome
browser-cli navigate --url "https://example.com" --wait-until networkidle --timeout 60000
browser-cli wait --selector 'input[name="q"]' --timeout 15000
browser-cli click --selector "a" --text-contains "News" --timeout 10000
browser-cli type --selector 'input[name="q"]' --text "browser automation" --clear-first true --timeout 10000
browser-cli current --html --text
browser-cli eval --script '() => ({href: location.href, title: document.title})'
browser-cli stop
```

#### MCP 流程（被反爬拦截时）

```bash
browser-cli health
browser-cli mcp-open --url "https://www.reuters.com/" --timeout-ms 120000
browser-cli mcp-web-wait --text "Markets" --timeout-ms 15000
browser-cli mcp-web-click --selector 'a[href*="/world/"]' --timeout-ms 15000
browser-cli mcp-web-type --selector 'input[type="search"]' --text "oil" --clear-first true --timeout-ms 15000
browser-cli mcp-call --name list_pages --arguments-json '{}'
browser-cli mcp-call --name take_snapshot --arguments-json '{}'
browser-cli mcp-read --selector "body" --timeout-ms 30000
```

### Windows

#### 传统流程（默认）

```powershell
browser-cli health
browser-cli start --headless false --engine patchright --channel chrome
browser-cli navigate --url "https://example.com" --wait-until networkidle --timeout 60000
browser-cli wait --selector "input[name='q']" --timeout 15000
browser-cli click --selector "a" --text-contains "News" --timeout 10000
browser-cli type --selector "input[name='q']" --text "browser automation" --clear-first true --timeout 10000
browser-cli current --html --text
browser-cli eval --script "() => ({href: location.href, title: document.title})"
browser-cli stop
```

#### MCP 流程（被反爬拦截时）

```powershell
browser-cli health
browser-cli mcp-open --url "https://www.reuters.com/" --timeout-ms 120000
browser-cli mcp-web-wait --text "Markets" --timeout-ms 15000
browser-cli mcp-web-click --selector "a[href*='/world/']" --timeout-ms 15000
browser-cli mcp-web-type --selector "input[type='search']" --text "oil" --clear-first true --timeout-ms 15000
browser-cli mcp-call --name list_pages --arguments-json "{}"
browser-cli mcp-call --name take_snapshot --arguments-json "{}"
browser-cli mcp-read --selector "body" --timeout-ms 30000
```

## More Common APIs

优先使用已有子命令；以下是常用能力补充，便于 skill 直接调用。
`get` / `post` 建议只在没有专用子命令时使用。

### Linux

```bash
browser-cli get --path /mcp/status
browser-cli get --path /mcp/tools
browser-cli get --path /mcp/console/messages
browser-cli get --path /mcp/network/requests
browser-cli mcp-read --selector "body" --timeout-ms 30000
browser-cli mcp-web-wait --text "Sign in" --timeout-ms 15000
browser-cli get --path /debug/snapshot
```

### Windows

```powershell
browser-cli get --path /mcp/status
browser-cli get --path /mcp/tools
browser-cli get --path /mcp/console/messages
browser-cli get --path /mcp/network/requests
browser-cli mcp-read --selector "body" --timeout-ms 30000
browser-cli mcp-web-wait --text "Sign in" --timeout-ms 15000
browser-cli get --path /debug/snapshot
```

## Raw Request

### Linux

```bash
browser-cli request --method POST --path /mcp/call --body-json '{"name":"take_snapshot","arguments":{},"timeout_ms":30000}'
```

### Windows

```powershell
browser-cli request --method POST --path /mcp/call --body-json "{\"name\":\"take_snapshot\",\"arguments\":{},\"timeout_ms\":30000}"
```
