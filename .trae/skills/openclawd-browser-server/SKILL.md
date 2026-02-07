---
name: "openclawd-browser-server"
description: "Calls the Windows Browser Server HTTP API to control a persistent browser session. Invoke when OpenClawd needs to navigate, evaluate JS, screenshot, or reuse logged-in cookies."
---

# OpenClawd Browser Server

Use this skill when OpenClawd must control a Windows browser via HTTP API and reuse a logged-in session.

## Preconditions

- Browser Server is running on Windows
- Base URL is reachable on the LAN
- A persistent user_data_dir was used for login reuse

## Notes

- Default channel is chrome unless BROWSER_CHANNEL is set
- For Gmail reuse, keep the same user_data_dir across UI and headless
- Complete login in visible mode before switching to headless

## Base URL

Use the environment variable in OpenClawd:

```bash
export BROWSER_SERVER_URL="http://192.168.31.118:3456"
```

## Common API Calls

### Start browser with persistent profile

user_data_dir can be omitted to use the project default (./user_data). Use a custom path only when you need to share profiles across machines.

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/start",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "headless": false,
      "channel": "chrome"
    }
  }
}
```

### Stop browser

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/stop",
    "method": "POST"
  }
}
```

### Navigate

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/navigate",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "url": "https://example.com",
      "wait_until": "networkidle",
      "extra_wait_ms": 3000
    }
  }
}
```

### Evaluate JavaScript

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/evaluate",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "script": "() => document.title"
    }
  }
}
```

### DevTools (CDP) version

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/cdp/version",
    "method": "GET"
  }
}
```

### DevTools (CDP) command

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/cdp/send",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "method": "Performance.getMetrics"
    }
  }
}
```

### CDP DOM text/HTML/attributes

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/cdp/dom/text",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "selector": "h1" }
  }
}
```

### Dialog wait/accept/dismiss

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/dialog/await",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "timeout": 10000, "action": "accept" }
  }
}
```

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/dialog/accept",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "prompt_text": "ok" }
  }
}
```

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/dialog/dismiss",
    "method": "POST"
  }
}
```

### Download directory and last download

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/download/dir",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "path": "./downloads" }
  }
}
```

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/downloads/last",
    "method": "GET"
  }
}
```

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/download/await",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "timeout": 30000 }
  }
}
```

### Element box and point click

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/element/box",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "selector": "#captcha" }
  }
}
```

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/click/point",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "x": 520, "y": 360 }
  }
}
```

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/cdp/dom/html",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "selector": "h1" }
  }
}
```

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/cdp/dom/attributes",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "selector": "h1" }
  }
}
```

### Wait for selector or text

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/wait",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "selector": "button[type='submit']",
      "timeout": 10000
    }
  }
}
```

### Click element

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/click",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "selector": "button[type='submit']",
      "timeout": 10000
    }
  }
}
```

### Type text

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/type",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "selector": "input[name='q']",
      "text": "openclawd",
      "clear_first": true
    }
  }
}
```

### Upload file(s)

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/upload",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "selector": "input[type='file']",
      "paths": ["C:/path/to/file.txt"]
    }
  }
}
```

### Scroll

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/scroll",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "direction": "down",
      "to_bottom": false,
      "amount": 600
    }
  }
}
```

### Get page text

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/text",
    "method": "GET"
  }
}
```

### Get current page info

Use include_html/include_text and optional selector to control content size.

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/current?include_text=true",
    "method": "GET"
  }
}
```

### List tabs

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/pages",
    "method": "GET"
  }
}
```

### New tab

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/page/new",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "url": "https://example.com" }
  }
}
```

### Switch tab

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/page/switch",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "id": 0 }
  }
}
```

### Close other tabs

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/page/close_others",
    "method": "POST"
  }
}
```

### Close current page

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/page/close",
    "method": "POST"
  }
}
```

Tip: 建议在任务完成后调用关闭页面，保持仅 about:blank 或必要标签，避免占用内存与句柄。

### Screenshot

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/screenshot",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": { "full_page": true }
  }
}
```

### Export storage state

path can be omitted to export into the default profile directory (./user_data/storage_state.json).

```json
{
  "tool": "fetch",
  "params": {
    "url": "${BROWSER_SERVER_URL}/storage/export",
    "method": "POST",
    "headers": { "Content-Type": "application/json" },
    "body": {
      "include_json": false
    }
  }
}
```
