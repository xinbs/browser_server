import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request


DEFAULT_BASE_URL = os.getenv("BROWSER_SERVER_URL", "http://192.168.31.118:3456")
API_ROUTES = [
    ("GET", "/health"),
    ("GET", "/queue/status"),
    ("GET", "/docs/raw"),
    ("POST", "/start"),
    ("POST", "/stop"),
    ("POST", "/navigate"),
    ("POST", "/evaluate"),
    ("GET", "/text"),
    ("GET", "/current"),
    ("GET", "/find"),
    ("POST", "/screenshot"),
    ("POST", "/wait"),
    ("POST", "/click"),
    ("POST", "/type"),
    ("POST", "/fill"),
    ("POST", "/press"),
    ("POST", "/drag"),
    ("POST", "/scroll"),
    ("POST", "/click/point"),
    ("POST", "/element/box"),
    ("POST", "/upload"),
    ("POST", "/download/dir"),
    ("GET", "/downloads"),
    ("GET", "/downloads/last"),
    ("POST", "/download/await"),
    ("POST", "/download"),
    ("POST", "/dialog/await"),
    ("POST", "/dialog/accept"),
    ("POST", "/dialog/dismiss"),
    ("POST", "/page/close"),
    ("GET", "/pages"),
    ("POST", "/page/new"),
    ("POST", "/page/switch"),
    ("POST", "/page/close_others"),
    ("POST", "/cdp/send"),
    ("GET", "/cdp/version"),
    ("POST", "/cdp/dom/text"),
    ("POST", "/cdp/dom/html"),
    ("POST", "/cdp/dom/attributes"),
    ("POST", "/storage/export"),
    ("POST", "/storage/import"),
    ("GET", "/network/requests"),
    ("GET", "/network/request/{request_id}"),
    ("GET", "/debug/info"),
    ("GET", "/debug/snapshot"),
    ("POST", "/mcp/start"),
    ("POST", "/mcp/reconnect"),
    ("POST", "/mcp/stop"),
    ("GET", "/mcp/status"),
    ("GET", "/mcp/tools"),
    ("POST", "/mcp/call"),
    ("POST", "/mcp/tool/{tool_name}"),
    ("POST", "/mcp/call/batch"),
    ("POST", "/mcp/navigate"),
    ("POST", "/mcp/open"),
    ("POST", "/mcp/read"),
    ("GET", "/mcp/network/requests"),
    ("GET", "/mcp/network/request"),
    ("GET", "/mcp/console/messages"),
    ("POST", "/mcp/web/wait"),
    ("POST", "/mcp/web/click"),
    ("POST", "/mcp/web/type"),
    ("POST", "/mcp/web/scroll"),
    ("POST", "/mcp/web/html"),
]


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _request(base_url: str, method: str, path: str, body: dict | None):
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, method=method.upper(), headers=headers, data=data)
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
        if not payload.strip():
            return {"success": True, "status_code": resp.status, "body": None}
        try:
            parsed = json.loads(payload)
            return parsed
        except Exception:
            return {"success": True, "status_code": resp.status, "body": payload}


def _optional_json(json_text: str | None, default: dict | list | None = None):
    if not json_text:
        return default
    parsed = json.loads(json_text)
    return parsed


def _print_result(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _api_guide():
    direct = {
        "/health": "health",
        "/start": "start",
        "/stop": "stop",
        "/navigate": "navigate",
        "/current": "current",
        "/evaluate": "eval",
        "/wait": "wait",
        "/click": "click",
        "/type": "type",
        "/mcp/start": "mcp-start",
        "/mcp/open": "mcp-open",
        "/mcp/read": "mcp-read",
        "/mcp/web/wait": "mcp-web-wait",
        "/mcp/web/click": "mcp-web-click",
        "/mcp/web/type": "mcp-web-type",
        "/mcp/call": "mcp-call",
    }
    examples = {
        "/health": "browser-cli health",
        "/start": "browser-cli start --headless false --engine patchright",
        "/stop": "browser-cli stop",
        "/navigate": "browser-cli navigate --url https://example.com --wait-until networkidle",
        "/current": "browser-cli current --text",
        "/evaluate": "browser-cli eval --script '() => document.title'",
        "/wait": "browser-cli wait --selector \"body\" --timeout 15000",
        "/click": "browser-cli click --selector \"a\" --timeout 10000",
        "/type": "browser-cli type --selector \"input\" --text \"hello\" --clear-first true",
        "/mcp/start": "browser-cli mcp-start",
        "/mcp/open": "browser-cli mcp-open --url https://www.reuters.com/ --timeout-ms 120000",
        "/mcp/read": "browser-cli mcp-read --selector \"body\" --timeout-ms 30000",
        "/mcp/web/wait": "browser-cli mcp-web-wait --text \"Sign in\" --timeout-ms 15000",
        "/mcp/web/click": "browser-cli mcp-web-click --selector \"a\" --timeout-ms 15000",
        "/mcp/web/type": "browser-cli mcp-web-type --selector \"input\" --text \"hello\" --clear-first true",
        "/mcp/call": "browser-cli mcp-call --name list_pages --arguments-json '{}'",
    }
    sample_path = {
        "/network/request/{request_id}": "/network/request/1",
        "/mcp/tool/{tool_name}": "/mcp/tool/list_pages",
    }
    items = []
    for method, path in API_ROUTES:
        recommended_cli = direct.get(path, "get/post/request")
        normalized_path = sample_path.get(path, path)
        if path in examples:
            example_cmd = examples[path]
        elif method == "GET":
            example_cmd = f"browser-cli get --path {normalized_path}"
        else:
            example_cmd = f"browser-cli post --path {normalized_path}"
        items.append(
            {
                "method": method,
                "path": path,
                "recommended_cli": recommended_cli,
                "example": example_cmd,
            }
        )
    return items


def _add_common(parser: argparse.ArgumentParser):
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Browser Server base URL")


def _install_cli(base_url: str, machine: bool):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.name == "nt":
        script_path = os.path.join(script_dir, "install-windows.ps1")
        command = ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path, "-BaseUrl", base_url]
        if machine:
            command.append("-Machine")
        target = "machine" if machine else "user"
    else:
        script_path = os.path.join(script_dir, "install-linux.sh")
        command = ["bash", script_path, base_url]
        target = "shell"
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        error_text = process.stderr.strip() or process.stdout.strip() or "install failed"
        raise RuntimeError(error_text)
    return {
        "success": True,
        "installed": True,
        "target": target,
        "base_url": base_url,
        "message": process.stdout.strip() or "ok",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="browser-cli",
        description="Browser Server CLI (use `browser-cli apis` for full route list)",
        epilog=(
            "Examples:\n"
            "  browser-cli health\n"
            "  browser-cli start --headless false --engine patchright --channel chrome\n"
            "  browser-cli navigate --url https://example.com --wait-until networkidle --timeout 60000\n"
            "  browser-cli wait --selector \"input[name='q']\" --timeout 15000\n"
            "  browser-cli mcp-open --url https://www.reuters.com/ --timeout-ms 120000   (fallback when blocked, auto-start MCP)\n"
            "  browser-cli mcp-web-wait --text Markets --timeout-ms 15000\n"
            "  browser-cli mcp-call --name list_pages --arguments-json '{}'\n"
            "  browser-cli apis\n"
            "  browser-cli get --path /mcp/status\n"
            "  browser-cli post --path /mcp/read --body-json '{\"selector\":\"body\",\"timeout_ms\":30000}'\n"
            "  browser-cli request --method POST --path /mcp/call --body-json '{\"name\":\"take_snapshot\",\"arguments\":{}}'\n"
            "\n"
            "Full API list:\n"
            "  browser-cli apis\n"
            "  browser-cli apis --json\n"
            "  browser-cli install"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", help="Get /health status", description="Get current browser status from /health")
    _add_common(p_health)

    p_start = sub.add_parser("start", help="Start browser session", description="Call /start to launch browser")
    _add_common(p_start)
    p_start.add_argument("--headless", help="true/false")
    p_start.add_argument("--engine", help="playwright or patchright")
    p_start.add_argument("--channel", help="browser channel, e.g. chrome")
    p_start.add_argument("--user-data-dir", help="persistent profile directory")
    p_start.add_argument("--user-agent", help="override user-agent")

    p_stop = sub.add_parser("stop", help="Stop browser session", description="Call /stop to close browser")
    _add_common(p_stop)

    p_nav = sub.add_parser("navigate", help="Navigate current page", description="Call /navigate to open URL")
    _add_common(p_nav)
    p_nav.add_argument("--url", required=True, help="target URL")
    p_nav.add_argument("--wait-until", default="networkidle", help="load state: load/domcontentloaded/networkidle")
    p_nav.add_argument("--timeout", type=int, default=60000, help="timeout in ms")
    p_nav.add_argument("--extra-wait-ms", type=int, default=3000, help="extra wait after navigation in ms")
    p_nav.add_argument("--wait-for-selector", help="wait until selector appears")
    p_nav.add_argument("--wait-for-text", help="wait until page contains text")

    p_current = sub.add_parser("current", help="Get current page info", description="Call /current with optional html/text")
    _add_common(p_current)
    p_current.add_argument("--html", action="store_true", help="include html")
    p_current.add_argument("--text", action="store_true", help="include text")
    p_current.add_argument("--selector", help="optional selector scope")
    p_current.add_argument("--timeout", type=int, default=30000, help="timeout in ms")

    p_eval = sub.add_parser("eval", help="Evaluate JavaScript", description="Call /evaluate with script")
    _add_common(p_eval)
    p_eval.add_argument("--script", required=True, help="JS function body, e.g. () => document.title")
    p_eval.add_argument("--args-json", help="JSON array args")
    p_eval.add_argument("--timeout", type=int, default=30000, help="timeout in ms")

    p_wait = sub.add_parser("wait", help="Wait for selector/text", description="Call /wait")
    _add_common(p_wait)
    p_wait.add_argument("--selector", help="wait for selector")
    p_wait.add_argument("--text", help="wait for text")
    p_wait.add_argument("--timeout", type=int, default=30000, help="timeout in ms")

    p_click = sub.add_parser("click", help="Click element", description="Call /click")
    _add_common(p_click)
    p_click.add_argument("--selector", required=True, help="target selector")
    p_click.add_argument("--text-contains", help="optional text filter")
    p_click.add_argument("--index", type=int, help="optional matched element index")
    p_click.add_argument("--timeout", type=int, default=10000, help="timeout in ms")

    p_type = sub.add_parser("type", help="Type text", description="Call /type")
    _add_common(p_type)
    p_type.add_argument("--selector", required=True, help="target selector")
    p_type.add_argument("--text", required=True, help="text to type")
    p_type.add_argument("--clear-first", help="true/false")
    p_type.add_argument("--timeout", type=int, default=10000, help="timeout in ms")

    p_mcp_start = sub.add_parser("mcp-start", help="Start MCP session", description="Call /mcp/start")
    _add_common(p_mcp_start)
    p_mcp_start.add_argument("--timeout-ms", type=int, default=15000, help="timeout in ms")

    p_mcp_open = sub.add_parser("mcp-open", help="Open URL via MCP", description="Call /mcp/open")
    _add_common(p_mcp_open)
    p_mcp_open.add_argument("--url", required=True, help="target URL")
    p_mcp_open.add_argument("--timeout-ms", type=int, default=30000, help="timeout in ms")

    p_mcp_read = sub.add_parser("mcp-read", help="Read text via MCP", description="Call /mcp/read")
    _add_common(p_mcp_read)
    p_mcp_read.add_argument("--selector", help="optional selector")
    p_mcp_read.add_argument("--timeout-ms", type=int, default=30000, help="timeout in ms")

    p_mcp_web_wait = sub.add_parser("mcp-web-wait", help="Wait element/text via MCP", description="Call /mcp/web/wait")
    _add_common(p_mcp_web_wait)
    p_mcp_web_wait.add_argument("--selector", help="wait for selector")
    p_mcp_web_wait.add_argument("--text", help="wait for text")
    p_mcp_web_wait.add_argument("--timeout-ms", type=int, default=30000, help="timeout in ms")
    p_mcp_web_wait.add_argument("--poll-interval-ms", type=int, default=300, help="poll interval in ms")

    p_mcp_web_click = sub.add_parser("mcp-web-click", help="Click via MCP", description="Call /mcp/web/click")
    _add_common(p_mcp_web_click)
    p_mcp_web_click.add_argument("--selector", required=True, help="target selector")
    p_mcp_web_click.add_argument("--index", type=int, default=0, help="matched element index")
    p_mcp_web_click.add_argument("--timeout-ms", type=int, default=30000, help="timeout in ms")
    p_mcp_web_click.add_argument("--poll-interval-ms", type=int, default=300, help="poll interval in ms")

    p_mcp_web_type = sub.add_parser("mcp-web-type", help="Type via MCP", description="Call /mcp/web/type")
    _add_common(p_mcp_web_type)
    p_mcp_web_type.add_argument("--selector", required=True, help="target selector")
    p_mcp_web_type.add_argument("--text", required=True, help="text to type")
    p_mcp_web_type.add_argument("--clear-first", help="true/false")
    p_mcp_web_type.add_argument("--submit-key", help="optional key, e.g. Enter")
    p_mcp_web_type.add_argument("--timeout-ms", type=int, default=30000, help="timeout in ms")

    p_mcp_call = sub.add_parser("mcp-call", help="Call MCP tool", description="Call /mcp/call by tool name")
    _add_common(p_mcp_call)
    p_mcp_call.add_argument("--name", required=True, help="tool name")
    p_mcp_call.add_argument("--arguments-json", help="JSON object arguments")
    p_mcp_call.add_argument("--timeout-ms", type=int, default=30000, help="timeout in ms")

    p_req = sub.add_parser("request", help="Raw HTTP passthrough", description="Call any Browser Server endpoint")
    _add_common(p_req)
    p_req.add_argument("--method", required=True, help="HTTP method")
    p_req.add_argument("--path", required=True, help="endpoint path, e.g. /mcp/call")
    p_req.add_argument("--body-json", help="JSON body")

    p_get = sub.add_parser("get", help="GET shortcut", description="Shortcut of request --method GET")
    _add_common(p_get)
    p_get.add_argument("--path", required=True, help="endpoint path, e.g. /mcp/status")

    p_post = sub.add_parser("post", help="POST shortcut", description="Shortcut of request --method POST")
    _add_common(p_post)
    p_post.add_argument("--path", required=True, help="endpoint path, e.g. /mcp/read")
    p_post.add_argument("--body-json", help="JSON body")

    p_apis = sub.add_parser("apis", help="List full API routes", description="List all Browser Server routes, suggested CLI command, and example usage")
    p_apis.add_argument("--json", action="store_true", help="output as json")

    p_install = sub.add_parser("install", help="Install browser-cli to PATH", description="Install CLI to PATH and set BROWSER_SERVER_URL")
    _add_common(p_install)
    p_install.add_argument("--machine", action="store_true", help="Windows only: install to Machine PATH")

    return parser


def run(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command
    try:
        if command == "health":
            result = _request(args.base_url, "GET", "/health", None)
        elif command == "start":
            body = {}
            if args.headless is not None:
                body["headless"] = _parse_bool(args.headless)
            if args.engine:
                body["engine"] = args.engine
            if args.channel:
                body["channel"] = args.channel
            if args.user_data_dir:
                body["user_data_dir"] = args.user_data_dir
            if args.user_agent:
                body["user_agent"] = args.user_agent
            result = _request(args.base_url, "POST", "/start", body)
        elif command == "stop":
            result = _request(args.base_url, "POST", "/stop", None)
        elif command == "navigate":
            body = {
                "url": args.url,
                "wait_until": args.wait_until,
                "timeout": args.timeout,
                "extra_wait_ms": args.extra_wait_ms,
                "wait_for_selector": args.wait_for_selector,
                "wait_for_text": args.wait_for_text,
            }
            result = _request(args.base_url, "POST", "/navigate", body)
        elif command == "current":
            query = urllib.parse.urlencode(
                {
                    "include_html": str(bool(args.html)).lower(),
                    "include_text": str(bool(args.text)).lower(),
                    "selector": args.selector or "",
                    "timeout": args.timeout,
                }
            )
            result = _request(args.base_url, "GET", f"/current?{query}", None)
        elif command == "eval":
            body = {
                "script": args.script,
                "args": _optional_json(args.args_json, default=None),
                "timeout": args.timeout,
            }
            result = _request(args.base_url, "POST", "/evaluate", body)
        elif command == "wait":
            body = {
                "selector": args.selector,
                "text": args.text,
                "timeout": args.timeout,
            }
            result = _request(args.base_url, "POST", "/wait", body)
        elif command == "click":
            body = {
                "selector": args.selector,
                "text_contains": args.text_contains,
                "index": args.index,
                "timeout": args.timeout,
            }
            result = _request(args.base_url, "POST", "/click", body)
        elif command == "type":
            body = {
                "selector": args.selector,
                "text": args.text,
                "timeout": args.timeout,
            }
            if args.clear_first is not None:
                body["clear_first"] = _parse_bool(args.clear_first)
            result = _request(args.base_url, "POST", "/type", body)
        elif command == "mcp-start":
            body = {"timeout_ms": args.timeout_ms}
            result = _request(args.base_url, "POST", "/mcp/start", body)
        elif command == "mcp-open":
            body = {"url": args.url, "timeout_ms": args.timeout_ms}
            result = _request(args.base_url, "POST", "/mcp/open", body)
        elif command == "mcp-read":
            body = {"selector": args.selector, "timeout_ms": args.timeout_ms}
            result = _request(args.base_url, "POST", "/mcp/read", body)
        elif command == "mcp-web-wait":
            body = {
                "selector": args.selector,
                "text": args.text,
                "timeout_ms": args.timeout_ms,
                "poll_interval_ms": args.poll_interval_ms,
            }
            result = _request(args.base_url, "POST", "/mcp/web/wait", body)
        elif command == "mcp-web-click":
            body = {
                "selector": args.selector,
                "index": args.index,
                "timeout_ms": args.timeout_ms,
                "poll_interval_ms": args.poll_interval_ms,
            }
            result = _request(args.base_url, "POST", "/mcp/web/click", body)
        elif command == "mcp-web-type":
            body = {
                "selector": args.selector,
                "text": args.text,
                "timeout_ms": args.timeout_ms,
            }
            if args.clear_first is not None:
                body["clear_first"] = _parse_bool(args.clear_first)
            if args.submit_key:
                body["submit_key"] = args.submit_key
            result = _request(args.base_url, "POST", "/mcp/web/type", body)
        elif command == "mcp-call":
            body = {
                "name": args.name,
                "arguments": _optional_json(args.arguments_json, default={}),
                "timeout_ms": args.timeout_ms,
            }
            result = _request(args.base_url, "POST", "/mcp/call", body)
        elif command == "request":
            body = _optional_json(args.body_json, default=None)
            result = _request(args.base_url, args.method, args.path, body)
        elif command == "get":
            result = _request(args.base_url, "GET", args.path, None)
        elif command == "post":
            body = _optional_json(args.body_json, default=None)
            result = _request(args.base_url, "POST", args.path, body)
        elif command == "apis":
            guide = _api_guide()
            if args.json:
                result = {"success": True, "count": len(guide), "apis": guide}
            else:
                lines = [f"{item['method']:4} {item['path']:28} {item['recommended_cli']:16} {item['example']}" for item in guide]
                result = {"success": True, "count": len(guide), "lines": lines}
        elif command == "install":
            result = _install_cli(args.base_url, args.machine)
        else:
            parser.error(f"Unknown command: {command}")
            return 2
        _print_result(result)
        return 0
    except Exception as e:
        _print_result({"success": False, "error": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
