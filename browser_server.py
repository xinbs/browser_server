import asyncio
import base64
import importlib
import os
import json
import urllib.request
import logging
import time
import uuid
import re
import shutil
import site
import sys
from collections import deque
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, Page, BrowserContext, Browser

HOST = os.getenv("BROWSER_HOST", "0.0.0.0")
PORT = int(os.getenv("BROWSER_PORT", "3456"))
DEFAULT_USER_DATA_DIR = os.getenv("BROWSER_USER_DATA_DIR", os.path.abspath("user_data"))
DEFAULT_HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() in {"1", "true", "yes", "y"}
AUTO_START = os.getenv("BROWSER_AUTO_START", "true").lower() in {"1", "true", "yes", "y"}
DEFAULT_ENGINE = (os.getenv("BROWSER_ENGINE") or "playwright").strip().lower()
if DEFAULT_ENGINE not in {"playwright", "patchright"}:
    DEFAULT_ENGINE = "playwright"
DEFAULT_CHANNEL = os.getenv("BROWSER_CHANNEL") or "chrome"
DEFAULT_DOWNLOAD_DIR = os.getenv("BROWSER_DOWNLOAD_DIR", os.path.abspath("downloads"))
LOG_LEVEL = os.getenv("BROWSER_LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("BROWSER_LOG_FILE", os.path.abspath(os.path.join("logs", "app.log")))
MCP_CONFIG_PATH = os.path.abspath("mcp_config.json")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
_formatter = logging.Formatter(fmt="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S %z")
_formatter.converter = time.localtime
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setLevel(LOG_LEVEL)
_file_handler.setFormatter(_formatter)
_stream_handler = logging.StreamHandler()
_stream_handler.setLevel(LOG_LEVEL)
_stream_handler.setFormatter(_formatter)
logging.basicConfig(level=LOG_LEVEL, handlers=[_file_handler, _stream_handler])
logger = logging.getLogger("browser_server")
request_queue = deque()
queue_condition = asyncio.Condition()


class StartRequest(BaseModel):
    headless: Optional[bool] = Field(None)
    user_data_dir: Optional[str] = Field(None)
    user_agent: Optional[str] = Field(None)
    channel: Optional[str] = Field(None)
    engine: Optional[str] = Field(None)


class MCPStartRequest(BaseModel):
    command: Optional[str] = Field("npx")
    args: Optional[list[str]] = Field(None)
    timeout_ms: int = Field(15000)


class MCPCallRequest(BaseModel):
    name: str = Field(...)
    arguments: Optional[dict] = Field(default_factory=dict)
    timeout_ms: int = Field(30000)


class MCPToolInvokeRequest(BaseModel):
    arguments: Optional[dict] = Field(default_factory=dict)
    timeout_ms: int = Field(30000)


class MCPBatchCallItem(BaseModel):
    name: str = Field(...)
    arguments: Optional[dict] = Field(default_factory=dict)


class MCPBatchCallRequest(BaseModel):
    calls: list[MCPBatchCallItem] = Field(...)
    timeout_ms: int = Field(30000)
    stop_on_error: bool = Field(True)


class MCPNavigateRequest(BaseModel):
    url: str = Field(...)
    timeout_ms: int = Field(30000)


class MCPReadRequest(BaseModel):
    selector: Optional[str] = Field(None)
    timeout_ms: int = Field(30000)


class MCPWebWaitRequest(BaseModel):
    selector: Optional[str] = Field(None)
    text: Optional[str] = Field(None)
    timeout_ms: int = Field(30000)
    poll_interval_ms: int = Field(300)


class MCPWebClickRequest(BaseModel):
    selector: str = Field(...)
    index: int = Field(0)
    timeout_ms: int = Field(30000)
    poll_interval_ms: int = Field(300)


class MCPWebTypeRequest(BaseModel):
    selector: str = Field(...)
    text: str = Field(...)
    clear_first: bool = Field(True)
    submit_key: Optional[str] = Field(None)
    timeout_ms: int = Field(30000)


class MCPWebScrollRequest(BaseModel):
    x: int = Field(0)
    y: int = Field(600)
    behavior: str = Field("auto")
    timeout_ms: int = Field(30000)


class MCPWebHtmlRequest(BaseModel):
    selector: Optional[str] = Field(None)
    timeout_ms: int = Field(30000)


class NavigateRequest(BaseModel):
    url: str = Field(...)
    wait_until: str = Field("networkidle")
    timeout: int = Field(60000)
    extra_wait_ms: int = Field(3000)
    wait_for_selector: Optional[str] = Field(None)
    wait_for_text: Optional[str] = Field(None)


class EvaluateRequest(BaseModel):
    script: str = Field(...)
    args: Optional[list] = Field(None)
    timeout: int = Field(30000)


class ScreenshotRequest(BaseModel):
    full_page: bool = Field(True)
    selector: Optional[str] = Field(None)
    timeout: int = Field(60000)


class WaitRequest(BaseModel):
    selector: Optional[str] = Field(None)
    text: Optional[str] = Field(None)
    timeout: int = Field(30000)


class ClickRequest(BaseModel):
    selector: str = Field(...)
    timeout: int = Field(10000)
    text_contains: Optional[str] = Field(None)
    index: Optional[int] = Field(None)


class TypeRequest(BaseModel):
    selector: str = Field(...)
    text: str = Field(...)
    timeout: int = Field(10000)
    clear_first: bool = Field(True)

class FillRequest(BaseModel):
    selector: str = Field(...)
    value: str = Field(...)
    timeout: int = Field(10000)

class PressRequest(BaseModel):
    key: str = Field(...)
    modifiers: Optional[list[str]] = Field(None)
    timeout: int = Field(10000)

class DragRequest(BaseModel):
    source: str = Field(...)
    target: str = Field(...)
    timeout: int = Field(10000)


class ScrollRequest(BaseModel):
    direction: str = Field("down")
    to_bottom: bool = Field(False)
    amount: Optional[int] = Field(None)


class StorageExportRequest(BaseModel):
    path: Optional[str] = Field(None)
    include_json: bool = Field(False)

class StorageImportRequest(BaseModel):
    cookies: Optional[list] = Field(None)
    local_storage: Optional[dict] = Field(None)
    url: Optional[str] = Field(None)
    timeout: int = Field(30000)

class NewPageRequest(BaseModel):
    url: Optional[str] = Field(None)
    wait_until: str = Field("networkidle")
    timeout: int = Field(60000)
    extra_wait_ms: int = Field(3000)
    wait_for_selector: Optional[str] = Field(None)
    wait_for_text: Optional[str] = Field(None)

class SwitchPageRequest(BaseModel):
    id: int = Field(...)

class CdpSendRequest(BaseModel):
    method: str = Field(...)
    params: Optional[dict] = Field(None)
    timeout: int = Field(30000)

class CdpDomRequest(BaseModel):
    selector: str = Field(...)
    timeout: int = Field(30000)

class UploadRequest(BaseModel):
    selector: str = Field(...)
    paths: list[str] = Field(...)
    timeout: int = Field(30000)

class DownloadDirRequest(BaseModel):
    path: Optional[str] = Field(None)

class DialogWaitRequest(BaseModel):
    timeout: int = Field(30000)
    action: Optional[str] = Field(None)
    prompt_text: Optional[str] = Field(None)

class DialogActionRequest(BaseModel):
    prompt_text: Optional[str] = Field(None)

class ElementBoxRequest(BaseModel):
    selector: str = Field(...)
    timeout: int = Field(30000)

class ClickPointRequest(BaseModel):
    x: float = Field(...)
    y: float = Field(...)
    button: str = Field("left")
    clicks: int = Field(1)
    delay: int = Field(0)

class DownloadWaitRequest(BaseModel):
    timeout: int = Field(30000)

class DownloadRequest(BaseModel):
    url: str = Field(...)
    path: Optional[str] = Field(None)
    timeout: int = Field(60000)


class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.user_data_dir: Optional[str] = None
        self.headless: Optional[bool] = None
        self.engine: Optional[str] = None
        self.download_dir: str = DEFAULT_DOWNLOAD_DIR
        self.downloads: list[dict] = []
        self.last_download: Optional[dict] = None
        self.dialog = None
        self.dialog_future: Optional[asyncio.Future] = None
        self.download_future: Optional[asyncio.Future] = None
        self.network_requests = deque()
        self.network_request_map: dict[str, dict] = {}
        self.network_request_id_map: dict[int, str] = {}
        self.network_limit = 2000

    async def _ensure_page(self):
        if not self.context:
            raise HTTPException(400, "Browser not started")
        if not self.page:
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            self._attach_page_listeners(self.page)
            return
        try:
            await self.page.title()
        except Exception:
            pages = list(self.context.pages)
            if pages:
                self.page = pages[0]
            else:
                self.page = await self.context.new_page()
            self._attach_page_listeners(self.page)

    async def _retry_if_context_destroyed(self, func):
        try:
            return await func()
        except Exception as e:
            message = str(e)
            if "Execution context was destroyed" in message:
                await self._ensure_page()
                await asyncio.sleep(0.2)
                return await func()
            if "Target page, context or browser has been closed" in message:
                await self.stop()
                raise HTTPException(400, "Browser not started")
            raise

    async def _handle_download(self, download):
        info = None
        try:
            os.makedirs(self.download_dir, exist_ok=True)
            path = os.path.join(self.download_dir, download.suggested_filename)
            await download.save_as(path)
            info = {"url": download.url, "path": path, "filename": download.suggested_filename}
        except Exception as e:
            info = {"url": download.url, "path": None, "filename": download.suggested_filename, "error": str(e)}
        self.last_download = info
        self.downloads.append(info)
        if self.download_future and not self.download_future.done():
            self.download_future.set_result(info)

    def _attach_page_listeners(self, page: Page):
        page.on("download", lambda download: asyncio.create_task(self._handle_download(download)))

    def _store_network_entry(self, entry_id: str, entry: dict):
        self.network_requests.append(entry_id)
        self.network_request_map[entry_id] = entry
        if len(self.network_requests) > self.network_limit:
            old_id = self.network_requests.popleft()
            old_entry = self.network_request_map.pop(old_id, None)
            if old_entry and "request_object_id" in old_entry:
                self.network_request_id_map.pop(old_entry["request_object_id"], None)

    async def _handle_request(self, request):
        entry_id = uuid.uuid4().hex
        request_object_id = id(request)
        self.network_request_id_map[request_object_id] = entry_id
        headers = dict(request.headers)
        content_type = headers.get("content-type", "")
        should_capture_post = any(token in content_type for token in ["text", "json", "x-www-form-urlencoded", "xml"])
        post_data = None
        post_data_error = None
        if should_capture_post:
            try:
                post_data = request.post_data
            except Exception as e:
                post_data_error = str(e)
        entry = {
            "id": entry_id,
            "request_object_id": request_object_id,
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
            "headers": headers,
            "post_data": post_data,
            "post_data_error": post_data_error,
            "timestamp": time.time(),
            "response_status": None,
            "response_headers": None,
            "response_body": None,
        }
        self._store_network_entry(entry_id, entry)

    async def _handle_response(self, response):
        request_object_id = id(response.request)
        req_id = self.network_request_id_map.get(request_object_id)
        if not req_id:
            return
        entry = self.network_request_map.get(req_id)
        if not entry:
            return
        entry["response_status"] = response.status
        entry["response_headers"] = dict(response.headers)
        content_type = response.headers.get("content-type", "")
        should_read = any(token in content_type for token in ["text", "json", "javascript", "xml", "html"])
        if should_read:
            try:
                text = await response.text()
                entry["response_body"] = text[:10000]
            except Exception:
                entry["response_body"] = None
        self.network_request_id_map.pop(request_object_id, None)
    async def _create_playwright_runtime(self, engine: str):
        if engine == "playwright":
            return await async_playwright().start()
        try:
            module = importlib.import_module("patchright.async_api")
            factory = getattr(module, "async_playwright")
            return await factory().start()
        except ModuleNotFoundError:
            user_site_paths: list[str] = []
            try:
                candidate = site.getusersitepackages()
                if isinstance(candidate, str):
                    user_site_paths = [candidate]
                elif isinstance(candidate, list):
                    user_site_paths = [p for p in candidate if isinstance(p, str)]
            except Exception:
                user_site_paths = []
            for path in user_site_paths:
                if path and os.path.isdir(path) and path not in sys.path:
                    sys.path.append(path)
            try:
                module = importlib.import_module("patchright.async_api")
                factory = getattr(module, "async_playwright")
                return await factory().start()
            except Exception as e:
                raise HTTPException(400, f"Patchright unavailable in current Python runtime ({sys.executable}): {str(e)}")
        except Exception as e:
            raise HTTPException(400, f"Patchright runtime init failed: {str(e)}")

    async def start(self, headless: Optional[bool] = None, user_data_dir: Optional[str] = None, user_agent: Optional[str] = None, channel: Optional[str] = None, engine: Optional[str] = None):
        if self.context:
            return {"success": True, "message": "Browser already running"}
        launch_engine = (engine or DEFAULT_ENGINE).strip().lower()
        if launch_engine not in {"playwright", "patchright"}:
            raise HTTPException(400, "Invalid engine, expected one of: playwright, patchright")

        self.playwright = await self._create_playwright_runtime(launch_engine)

        launch_headless = DEFAULT_HEADLESS if headless is None else headless
        launch_user_data_dir = os.path.abspath(user_data_dir or DEFAULT_USER_DATA_DIR)
        os.makedirs(launch_user_data_dir, exist_ok=True)

        args = [
            "--remote-debugging-port=9222",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--window-size=1920,1080",
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ]

        launch_user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.7559.110 Safari/537.36"
        launch_channel = channel or DEFAULT_CHANNEL
        launch_kwargs = {
            "user_data_dir": launch_user_data_dir,
            "headless": launch_headless,
            "args": args,
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": launch_user_agent,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "accept_downloads": True,
            "downloads_path": os.path.abspath(self.download_dir),
        }
        if launch_channel:
            launch_kwargs["channel"] = launch_channel
        try:
            self.context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as e:
            if launch_engine == "patchright" and "channel" in launch_kwargs:
                retry_kwargs = dict(launch_kwargs)
                retry_kwargs.pop("channel", None)
                try:
                    logger.warning("Patchright launch with channel failed, retrying without channel: %s", e)
                    self.context = await self.playwright.chromium.launch_persistent_context(**retry_kwargs)
                    launch_channel = None
                except Exception as retry_error:
                    if self.playwright:
                        try:
                            await self.playwright.stop()
                        except Exception:
                            pass
                    self.playwright = None
                    raise HTTPException(500, f"Browser launch failed (patchright): {str(retry_error)}")
            else:
                if self.playwright:
                    try:
                        await self.playwright.stop()
                    except Exception:
                        pass
                self.playwright = None
                raise HTTPException(500, f"Browser launch failed: {str(e)}")

        await self.context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});"
        )

        self.user_data_dir = launch_user_data_dir
        self.headless = launch_headless
        self.engine = launch_engine
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        os.makedirs(self.download_dir, exist_ok=True)
        self._attach_page_listeners(self.page)
        self.context.on("page", lambda p: self._attach_page_listeners(p))
        self.context.on("request", lambda r: asyncio.create_task(self._handle_request(r)))
        self.context.on("response", lambda r: asyncio.create_task(self._handle_response(r)))
        logger.info("Browser started engine=%s headless=%s user_data_dir=%s channel=%s", self.engine, self.headless, self.user_data_dir, launch_channel)
        return {"success": True, "message": "Browser started", "engine": self.engine, "headless": self.headless, "user_data_dir": self.user_data_dir}

    async def stop(self):
        if not self.context:
            return {"success": True, "message": "Browser not running"}

        try:
            await self.context.close()
        except Exception:
            pass
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass

        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        self.user_data_dir = None
        self.headless = None
        self.engine = None
        self.dialog = None
        self.dialog_future = None
        self.download_future = None
        self.network_requests.clear()
        self.network_request_map.clear()
        self.network_request_id_map.clear()

        logger.info("Browser stopped")
        return {"success": True, "message": "Browser stopped"}

    async def navigate(self, url: str, wait_until: str = "networkidle", timeout: int = 60000, extra_wait_ms: int = 3000, wait_for_selector: Optional[str] = None, wait_for_text: Optional[str] = None):
        if not self.page:
            raise HTTPException(400, "Browser not started. Call POST /start first.")

        try:
            await self._ensure_page()
            logger.info("Navigate requested url=%s wait_until=%s timeout=%s", url, wait_until, timeout)
            await self.page.goto(url, wait_until=wait_until, timeout=timeout)
            if wait_for_selector:
                await self.page.locator(wait_for_selector).wait_for(state="visible", timeout=timeout)
            if wait_for_text:
                await self.page.get_by_text(wait_for_text).wait_for(timeout=timeout)
            if extra_wait_ms > 0:
                await asyncio.sleep(extra_wait_ms / 1000)
            logger.info("Navigate completed url=%s title=%s", self.page.url, await self.page.title())
            return {"success": True, "url": self.page.url, "title": await self.page.title()}
        except Exception as e:
            raise HTTPException(500, f"Navigation failed: {str(e)}")

    async def evaluate(self, script: str, args: Optional[list] = None, timeout: int = 30000):
        if not self.page:
            raise HTTPException(400, "Browser not started")

        try:
            await self._ensure_page()
            result = await self._retry_if_context_destroyed(lambda: self.page.evaluate(script, args))
            return {"success": True, "result": result if result is not None else None}
        except Exception as e:
            raise HTTPException(500, f"Script execution failed: {str(e)}")

    async def get_text(self, selector: Optional[str] = None, timeout: int = 30000):
        if not self.page:
            raise HTTPException(400, "Browser not started")

        try:
            await self._ensure_page()
            if selector:
                await self.page.wait_for_selector(selector, timeout=timeout)
                element = self.page.locator(selector).first
                text = await element.text_content()
            else:
                text = await self._retry_if_context_destroyed(lambda: self.page.evaluate("() => document.body.innerText"))
            return {"success": True, "text": text or "", "length": len(text or "")}
        except Exception as e:
            raise HTTPException(500, f"Get text failed: {str(e)}")

    async def get_current(self, include_html: bool = False, include_text: bool = False, selector: Optional[str] = None, timeout: int = 30000):
        if not self.page:
            raise HTTPException(400, "Browser not started")

        try:
            await self._ensure_page()
            title = await self.page.title()
            result = {
                "success": True,
                "url": self.page.url,
                "title": title,
            }
            if include_html:
                html = await self.page.content()
                result["html"] = html
                result["html_length"] = len(html or "")
            if include_text:
                if selector:
                    await self.page.wait_for_selector(selector, timeout=timeout)
                    element = self.page.locator(selector).first
                    text = await element.text_content()
                else:
                    text = await self._retry_if_context_destroyed(lambda: self.page.evaluate("() => document.body.innerText"))
                result["text"] = text or ""
                result["text_length"] = len(text or "")
            return result
        except Exception as e:
            raise HTTPException(500, f"Get current failed: {str(e)}")

    async def find(self, selector: str, text: Optional[str] = None, limit: int = 20, timeout: int = 30000):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        try:
            await self._ensure_page()
            locator = self.page.locator(selector)
            if text:
                locator = locator.filter(has_text=text)
            await locator.first.wait_for(state="attached", timeout=timeout)
            count = await locator.count()
            size = min(max(limit, 1), count)
            items = []
            for i in range(size):
                item = locator.nth(i)
                text_value = await item.text_content()
                href = await item.get_attribute("href")
                items.append({"index": i, "text": text_value or "", "href": href})
            return {"success": True, "count": count, "items": items}
        except Exception as e:
            raise HTTPException(500, f"Find failed: {str(e)}")

    async def screenshot(self, full_page: bool = True, selector: Optional[str] = None, timeout: int = 60000):
        if not self.page:
            raise HTTPException(400, "Browser not started")

        try:
            await self._ensure_page()
            if selector:
                element = self.page.locator(selector)
                buffer = await element.screenshot(timeout=timeout)
            else:
                buffer = await self.page.screenshot(full_page=full_page, timeout=timeout)
            image_b64 = base64.b64encode(buffer).decode("utf-8")
            return {"success": True, "image_base64": image_b64, "mime_type": "image/png", "size": len(buffer)}
        except Exception as e:
            raise HTTPException(500, f"Screenshot failed: {str(e)}")

    async def wait_for(self, selector: Optional[str] = None, text: Optional[str] = None, timeout: int = 30000):
        if not self.page:
            raise HTTPException(400, "Browser not started")

        try:
            await self._ensure_page()
            if selector:
                await self.page.locator(selector).wait_for(state="visible", timeout=timeout)
            if text:
                await self.page.get_by_text(text).wait_for(timeout=timeout)
            return {"success": True, "message": "Wait condition satisfied"}
        except Exception as e:
            raise HTTPException(500, f"Wait failed: {str(e)}")

    async def click(self, selector: str, timeout: int = 10000, text_contains: Optional[str] = None, index: Optional[int] = None):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        locator = self.page.locator(selector)
        if text_contains:
            locator = locator.filter(has_text=text_contains)
        if index is not None:
            locator = locator.nth(index)
        else:
            locator = locator.first
        await locator.click(timeout=timeout)
        return {"success": True}

    async def type(self, selector: str, text: str, timeout: int = 10000, clear_first: bool = True):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        locator = self.page.locator(selector)
        if clear_first:
            await locator.fill(text, timeout=timeout)
        else:
            await locator.press_sequentially(text, timeout=timeout)
        return {"success": True}

    async def fill(self, selector: str, value: str, timeout: int = 10000):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        await self.page.locator(selector).fill(value, timeout=timeout)
        return {"success": True}

    async def press(self, key: str, modifiers: Optional[list[str]] = None, timeout: int = 10000):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        combo = "+".join([*(modifiers or []), key])
        await self.page.keyboard.press(combo, timeout=timeout)
        return {"success": True}

    async def drag(self, source: str, target: str, timeout: int = 10000):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        await self.page.drag_and_drop(source, target, timeout=timeout)
        return {"success": True}

    async def scroll(self, direction: str = "down", to_bottom: bool = False, amount: Optional[int] = None):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        if to_bottom:
            await self._retry_if_context_destroyed(lambda: self.page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)"))
        elif amount:
            delta = amount if direction == "down" else -amount
            await self._retry_if_context_destroyed(lambda: self.page.evaluate(f"() => window.scrollBy(0, {delta})"))
        else:
            delta = "window.innerHeight" if direction == "down" else "-window.innerHeight"
            await self._retry_if_context_destroyed(lambda: self.page.evaluate(f"() => window.scrollBy(0, {delta})"))
        return {"success": True}

    async def click_point(self, x: float, y: float, button: str = "left", clicks: int = 1, delay: int = 0):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        await self.page.mouse.click(x, y, button=button, click_count=clicks, delay=delay)
        return {"success": True}

    async def element_box(self, selector: str, timeout: int = 30000):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        await self.page.wait_for_selector(selector, timeout=timeout)
        box = await self.page.locator(selector).first.bounding_box()
        if not box:
            raise HTTPException(404, "Element not visible")
        return {"success": True, "box": box}

    async def upload_files(self, selector: str, paths: list[str], timeout: int = 30000):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        if not paths:
            raise HTTPException(400, "No files provided")
        resolved = [os.path.abspath(p) for p in paths]
        for p in resolved:
            if not os.path.exists(p):
                raise HTTPException(400, f"File not found: {p}")
        locator = self.page.locator(selector)
        await locator.set_input_files(resolved, timeout=timeout)
        return {"success": True, "count": len(resolved)}

    async def set_download_dir(self, path: Optional[str] = None):
        self.download_dir = os.path.abspath(path or DEFAULT_DOWNLOAD_DIR)
        os.makedirs(self.download_dir, exist_ok=True)
        return {"success": True, "download_dir": self.download_dir}

    async def get_downloads(self):
        return {"success": True, "downloads": self.downloads}

    async def get_last_download(self):
        return {"success": True, "download": self.last_download}

    async def wait_download(self, timeout: int = 30000):
        if not self.context:
            raise HTTPException(400, "Browser not started")
        loop = asyncio.get_running_loop()
        self.download_future = loop.create_future()
        wait_seconds = max(timeout, 1) / 1000
        try:
            info = await asyncio.wait_for(self.download_future, timeout=wait_seconds)
            return {"success": True, "download": info}
        except Exception:
            raise HTTPException(408, "Download wait timeout")

    async def wait_dialog(self, timeout: int = 30000, action: Optional[str] = None, prompt_text: Optional[str] = None):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        if self.dialog_future and not self.dialog_future.done():
            raise HTTPException(409, "Dialog wait already in progress")
        loop = asyncio.get_running_loop()
        self.dialog_future = loop.create_future()
        def handler(d):
            if self.dialog_future and not self.dialog_future.done():
                self.dialog = d
                self.dialog_future.set_result(d)
        self.page.once("dialog", handler)
        wait_seconds = max(timeout, 1) / 1000
        try:
            dialog = await asyncio.wait_for(self.dialog_future, timeout=wait_seconds)
            if action == "accept":
                await dialog.accept(prompt_text or "")
                self.dialog = None
                return {"success": True, "handled": "accept", "type": dialog.type, "message": dialog.message, "default_value": dialog.default_value}
            if action == "dismiss":
                await dialog.dismiss()
                self.dialog = None
                return {"success": True, "handled": "dismiss", "type": dialog.type, "message": dialog.message, "default_value": dialog.default_value}
            return {"success": True, "type": dialog.type, "message": dialog.message, "default_value": dialog.default_value}
        except Exception:
            raise HTTPException(408, "Dialog wait timeout")

    async def dialog_accept(self, prompt_text: Optional[str] = None):
        if not self.dialog:
            raise HTTPException(404, "No dialog available")
        await self.dialog.accept(prompt_text or "")
        self.dialog = None
        return {"success": True}

    async def dialog_dismiss(self):
        if not self.dialog:
            raise HTTPException(404, "No dialog available")
        await self.dialog.dismiss()
        self.dialog = None
        return {"success": True}

    async def close_page(self):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        try:
            context = self.context
            if not context:
                raise HTTPException(400, "Browser not started")
            pages = list(context.pages)
            if len(pages) <= 1:
                await self.page.goto("about:blank")
                logger.info("Close page requested, single page remains")
                return {"success": True, "remaining_pages": 1}
            await self.page.close()
            remaining_pages = list(context.pages)
            self.page = remaining_pages[0] if remaining_pages else await context.new_page()
            logger.info("Close page requested, remaining_pages=%s", len(remaining_pages))
            return {"success": True, "remaining_pages": len(remaining_pages)}
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                await self.stop()
                raise HTTPException(400, "Browser not started")
            raise HTTPException(500, f"Close page failed: {str(e)}")

    async def export_storage(self, path: Optional[str] = None, include_json: bool = False):
        if not self.context:
            raise HTTPException(400, "Browser not started")
        target_path = os.path.abspath(path or os.path.join(self.user_data_dir or DEFAULT_USER_DATA_DIR, "storage_state.json"))
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        storage_state = await self.context.storage_state(path=target_path)
        if include_json:
            return {"success": True, "path": target_path, "storage_state": storage_state}
        return {"success": True, "path": target_path}

    async def import_storage(self, cookies: Optional[list] = None, local_storage: Optional[dict] = None, url: Optional[str] = None, timeout: int = 30000):
        if not self.context or not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        if cookies:
            await self.context.add_cookies(cookies)
        if local_storage:
            if url:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            await self.page.evaluate(
                "(items) => { for (const [k, v] of Object.entries(items)) { localStorage.setItem(k, v); } }",
                local_storage,
            )
        return {"success": True}

    async def download_url(self, url: str, path: Optional[str] = None, timeout: int = 60000):
        if not self.context or not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        wait_seconds = max(timeout, 1) / 1000
        try:
            async with self.page.expect_download(timeout=timeout) as download_info:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            download = await download_info.value
            os.makedirs(self.download_dir, exist_ok=True)
            target_path = os.path.abspath(path or os.path.join(self.download_dir, download.suggested_filename))
            await asyncio.wait_for(download.save_as(target_path), timeout=wait_seconds)
            info = {"url": download.url, "path": target_path, "filename": download.suggested_filename}
            self.last_download = info
            self.downloads.append(info)
            return {"success": True, "download": info}
        except Exception as e:
            raise HTTPException(500, f"Download failed: {str(e)}")

    async def list_network_requests(self, pattern: Optional[str] = None, limit: int = 100, include_body: bool = False):
        entries = []
        regex = None
        if pattern:
            try:
                regex = re.compile(pattern)
            except re.error:
                regex = None
        for req_id in list(self.network_requests):
            entry = self.network_request_map.get(req_id)
            if not entry:
                continue
            if pattern:
                url = entry.get("url", "")
                if regex:
                    if not regex.search(url):
                        continue
                else:
                    if pattern not in url:
                        continue
            item = dict(entry)
            item.pop("request_object_id", None)
            if not include_body:
                item["response_body"] = None
            entries.append(item)
        limited = entries[-max(limit, 1):]
        return {"success": True, "count": len(entries), "items": limited}

    async def get_network_request(self, request_id: str, include_body: bool = False):
        entry = self.network_request_map.get(request_id)
        if not entry:
            raise HTTPException(404, "Request not found")
        item = dict(entry)
        item.pop("request_object_id", None)
        if not include_body:
            item["response_body"] = None
        return {"success": True, "request": item}

    async def debug_info(self):
        status = await self.get_status()
        pages = []
        if self.context:
            for idx, p in enumerate(self.context.pages):
                t = ""
                try:
                    t = await p.title()
                except Exception:
                    t = ""
                pages.append({"id": idx, "url": p.url, "title": t, "current": p is self.page})
        return {"success": True, "status": status, "pages": pages, "downloads": len(self.downloads)}

    async def debug_snapshot(self, timeout: int = 30000):
        if not self.page:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        await self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
        html = await self.page.content()
        text = await self._retry_if_context_destroyed(lambda: self.page.evaluate("() => document.body.innerText"))
        return {"success": True, "url": self.page.url, "title": await self.page.title(), "html": html, "text": text or "", "timeout": timeout}

    async def get_status(self):
        if not self.context:
            return {"running": False, "url": None, "title": None, "engine": None, "headless": None, "user_data_dir": None}
        if self.page:
            await self._ensure_page()
        title = await self.page.title() if self.page else None
        return {
            "running": True,
            "url": self.page.url if self.page else None,
            "title": title,
            "engine": self.engine,
            "headless": self.headless,
            "user_data_dir": self.user_data_dir,
        }

    async def list_pages(self):
        if not self.context:
            raise HTTPException(400, "Browser not started")
        await self._ensure_page()
        pages = []
        for idx, p in enumerate(self.context.pages):
            t = ""
            try:
                t = await p.title()
            except Exception:
                t = ""
            pages.append({"id": idx, "url": p.url, "title": t, "current": p is self.page})
        return {"success": True, "pages": pages}

    async def new_page(self, url: Optional[str] = None, wait_until: str = "networkidle", timeout: int = 60000, extra_wait_ms: int = 3000, wait_for_selector: Optional[str] = None, wait_for_text: Optional[str] = None):
        if not self.context:
            raise HTTPException(400, "Browser not started")
        try:
            p = await self.context.new_page()
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                await self.stop()
                raise HTTPException(400, "Browser not started")
            raise
        self.page = p
        logger.info("New page requested url=%s", url)
        if url:
            try:
                await p.goto(url, wait_until=wait_until, timeout=timeout)
                if wait_for_selector:
                    await p.locator(wait_for_selector).wait_for(state="visible", timeout=timeout)
                if wait_for_text:
                    await p.get_by_text(wait_for_text).wait_for(timeout=timeout)
                if extra_wait_ms > 0:
                    await asyncio.sleep(extra_wait_ms / 1000)
            except Exception as e:
                raise HTTPException(500, f"Open new page failed: {str(e)}")
        try:
            title = await p.title()
        except Exception:
            title = ""
        return {"success": True, "id": self.context.pages.index(p), "url": p.url, "title": title}

    async def switch_page(self, id: int):
        if not self.context:
            raise HTTPException(400, "Browser not started")
        pages = self.context.pages
        if id < 0 or id >= len(pages):
            raise HTTPException(404, "Page not found")
        self.page = pages[id]
        return {"success": True, "current_id": id, "url": self.page.url, "title": await self.page.title()}

    async def close_others(self):
        if not self.context or not self.page:
            raise HTTPException(400, "Browser not started")
        try:
            current = self.page
            for p in list(self.context.pages):
                if p is not current:
                    try:
                        await p.close()
                    except Exception:
                        pass
            remaining_pages = len(self.context.pages)
            if remaining_pages == 0:
                self.page = await self.context.new_page()
                remaining_pages = 1
            logger.info("Close other pages requested, remaining_pages=%s", remaining_pages)
            return {"success": True, "remaining_pages": remaining_pages}
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                await self.stop()
                raise HTTPException(400, "Browser not started")
            raise

    async def cdp_send(self, method: str, params: Optional[dict] = None, timeout: int = 30000):
        if not self.context or not self.page:
            raise HTTPException(400, "Browser not started")
        try:
            session = await self.context.new_cdp_session(self.page)
            wait_seconds = max(timeout, 1) / 1000
            result = await asyncio.wait_for(session.send(method, params or {}), timeout=wait_seconds)
            await session.detach()
            return {"success": True, "result": result}
        except Exception as e:
            raise HTTPException(500, f"CDP send failed: {str(e)}")

    async def cdp_version(self):
        if not self.context or not self.page:
            raise HTTPException(400, "Browser not started")
        try:
            session = await self.context.new_cdp_session(self.page)
            v = await session.send("Browser.getVersion", {})
            await session.detach()
            return {"success": True, "version": v}
        except Exception:
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return {"success": True, "version": data}
            except Exception as e:
                raise HTTPException(500, f"CDP version failed: {str(e)}")

    async def cdp_dom_text(self, selector: str, timeout: int = 30000):
        if not self.context or not self.page:
            raise HTTPException(400, "Browser not started")
        try:
            await self._ensure_page()
            await self.page.wait_for_selector(selector, timeout=timeout)
            async def run():
                session = await self.context.new_cdp_session(self.page)
                expression = f"document.querySelector({json.dumps(selector)})?.textContent || ''"
                wait_seconds = max(timeout, 1) / 1000
                result = await asyncio.wait_for(session.send("Runtime.evaluate", {"expression": expression, "returnByValue": True}), timeout=wait_seconds)
                await session.detach()
                return result
            result = await self._retry_if_context_destroyed(run)
            text = ""
            if result and isinstance(result, dict):
                value = result.get("result", {}).get("value")
                text = value if isinstance(value, str) else ""
            return {"success": True, "text": text, "length": len(text)}
        except Exception as e:
            raise HTTPException(500, f"CDP DOM text failed: {str(e)}")

    async def cdp_dom_html(self, selector: str, timeout: int = 30000):
        if not self.context or not self.page:
            raise HTTPException(400, "Browser not started")
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            session = await self.context.new_cdp_session(self.page)
            document = await session.send("DOM.getDocument", {"depth": 1})
            node_id = await session.send("DOM.querySelector", {"nodeId": document["root"]["nodeId"], "selector": selector})
            html = await session.send("DOM.getOuterHTML", {"nodeId": node_id["nodeId"]})
            await session.detach()
            value = html.get("outerHTML", "") if isinstance(html, dict) else ""
            return {"success": True, "html": value, "length": len(value)}
        except Exception as e:
            raise HTTPException(500, f"CDP DOM html failed: {str(e)}")

    async def cdp_dom_attributes(self, selector: str, timeout: int = 30000):
        if not self.context or not self.page:
            raise HTTPException(400, "Browser not started")
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            session = await self.context.new_cdp_session(self.page)
            document = await session.send("DOM.getDocument", {"depth": 1})
            node_id = await session.send("DOM.querySelector", {"nodeId": document["root"]["nodeId"], "selector": selector})
            attrs = await session.send("DOM.getAttributes", {"nodeId": node_id["nodeId"]})
            await session.detach()
            pairs = attrs.get("attributes", []) if isinstance(attrs, dict) else []
            result = {}
            for i in range(0, len(pairs), 2):
                if i + 1 < len(pairs):
                    result[pairs[i]] = pairs[i + 1]
            return {"success": True, "attributes": result}
        except Exception as e:
            raise HTTPException(500, f"CDP DOM attributes failed: {str(e)}")


class MCPManager:
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self._stdout_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._pending: dict[int, asyncio.Future] = {}
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._tools_cache: Optional[list] = None
        self._initialized = False
        self._last_start: dict = {}
        self._last_keepalive_tool_at = 0.0

    def status(self):
        running = self.process is not None and self.process.returncode is None
        return {"success": True, "running": running, "initialized": self._initialized, "mode": self._last_start.get("mode"), "wsEndpoint": self._last_start.get("wsEndpoint")}

    async def start(self, command: Optional[str], args: Optional[list[str]], timeout_ms: int = 15000):
        if self.process and self.process.returncode is None:
            return {"success": True, "message": "MCP already running"}
        if not command:
            raise HTTPException(400, "MCP command is required")
        arg_list = args or []
        self._last_start = self._extract_start_info(command, arg_list)
        logger.info("MCP starting command=%s mode=%s timeout_ms=%s", command, self._last_start.get("mode"), timeout_ms)
        resolved = shutil.which(command) or command
        exec_cmd = [resolved]
        if os.name == "nt":
            lowered = resolved.lower()
            if lowered.endswith(".ps1"):
                exec_cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", resolved]
            elif lowered.endswith(".cmd") or lowered.endswith(".bat"):
                exec_cmd = ["cmd", "/c", resolved]
        self.process = await asyncio.create_subprocess_exec(
            *exec_cmd,
            *arg_list,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._pending = {}
        self._request_id = 0
        self._tools_cache = None
        self._initialized = False
        self._last_keepalive_tool_at = 0.0
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        init_result = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "browser_server", "version": "1.0.0"},
            },
            timeout_ms=timeout_ms,
        )
        await self._send_notification("initialized", {})
        self._initialized = True
        if self._keepalive_task:
            self._keepalive_task.cancel()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        logger.info("MCP started pid=%s mode=%s wsEndpoint=%s", self.process.pid if self.process else None, self._last_start.get("mode"), self._last_start.get("wsEndpoint"))
        return {"success": True, "message": "MCP started", "initialize": init_result}

    async def ensure_started(self, command: Optional[str] = None, args: Optional[list[str]] = None, timeout_ms: int = 15000):
        async with self._start_lock:
            if self.process and self.process.returncode is None and self._initialized:
                return {"success": True, "message": "MCP already running"}
            if self.process and self.process.returncode is None and not self._initialized:
                await self.stop()
            config = self._load_mcp_config()
            require_ws = bool(config.get("require_ws"))
            config_command = config.get("command")
            command_value = command or (config_command if isinstance(config_command, str) else None) or os.getenv("MCP_COMMAND") or "npx"
            args_value = args
            if args_value is None:
                config_args = config.get("args")
                if isinstance(config_args, list):
                    args_value = config_args
            if args_value is None and require_ws:
                ws = self._resolve_local_ws_endpoint()
                if not ws:
                    raise HTTPException(400, "DevTools wsEndpoint not found. Enable Chrome remote debugging port to avoid consent prompts.")
                args_value = ["chrome-devtools-mcp@latest", "--wsEndpoint", ws, "--no-usage-statistics"]
            if args_value is None:
                channel_override = config.get("channel")
                args_value = self._default_args(channel_override=channel_override if isinstance(channel_override, str) else None)
            return await self.start(command_value, args_value, timeout_ms=timeout_ms)

    async def stop(self):
        if not self.process:
            return {"success": True, "message": "MCP not running"}
        logger.info("MCP stopping pid=%s", self.process.pid if self.process else None)
        if self._stdout_task:
            self._stdout_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()
        if self._keepalive_task:
            self._keepalive_task.cancel()
        exit_code = None
        try:
            self.process.terminate()
            await asyncio.wait_for(self.process.wait(), timeout=5)
            exit_code = self.process.returncode
        except Exception:
            try:
                self.process.kill()
                await self.process.wait()
                exit_code = self.process.returncode
            except Exception:
                pass
        self.process = None
        self._pending = {}
        self._tools_cache = None
        self._initialized = False
        self._last_keepalive_tool_at = 0.0
        logger.info("MCP stopped exit_code=%s", exit_code)
        return {"success": True, "message": "MCP stopped"}

    async def _keepalive_loop(self):
        while True:
            try:
                await asyncio.sleep(20)
                if not self.process or self.process.returncode is not None or not self._initialized:
                    continue
                ping_ok = True
                try:
                    await self._send_request("ping", {}, timeout_ms=8000)
                except Exception:
                    ping_ok = False
                now = time.time()
                should_check_tool = (now - self._last_keepalive_tool_at) >= 60
                if should_check_tool:
                    self._last_keepalive_tool_at = now
                    try:
                        await self._send_request("tools/list", {}, timeout_ms=10000)
                    except Exception:
                        ping_ok = False
                if not ping_ok:
                    logger.warning("MCP keepalive failed, reconnecting")
                    await self.reconnect(timeout_ms=15000)
            except asyncio.CancelledError:
                break
            except Exception:
                try:
                    logger.exception("MCP keepalive loop error, reconnecting")
                    await self.reconnect(timeout_ms=15000)
                except Exception:
                    logger.exception("MCP reconnect failed in keepalive loop")
                    pass

    def _extract_start_info(self, command: Optional[str], args: list[str]) -> dict:
        ws_endpoint = None
        mode = "custom"
        for i, item in enumerate(args):
            if item == "--wsEndpoint" and i + 1 < len(args):
                ws_endpoint = args[i + 1]
                mode = "wsEndpoint"
                break
            if item.startswith("--wsEndpoint="):
                ws_endpoint = item.split("=", 1)[1]
                mode = "wsEndpoint"
                break
        if mode != "wsEndpoint":
            for item in args:
                if item in ("--auto-connect", "--autoConnect"):
                    mode = "autoConnect"
                    break
        return {"command": command, "args": list(args), "mode": mode, "wsEndpoint": ws_endpoint}

    async def reconnect(self, timeout_ms: int = 15000):
        logger.warning("MCP reconnect requested timeout_ms=%s", timeout_ms)
        if self.process and self.process.returncode is None:
            await self.stop()
        result = await self.ensure_started(timeout_ms=timeout_ms)
        logger.info("MCP reconnect completed success=%s", result.get("success"))
        return result

    async def list_tools(self, timeout_ms: int = 30000):
        result = await self._send_request("tools/list", {}, timeout_ms=timeout_ms)
        tools = []
        if isinstance(result, dict):
            tools = result.get("tools") or []
        elif isinstance(result, list):
            tools = result
        self._tools_cache = tools
        return {"success": True, "tools": tools}

    async def call_tool(self, name: str, arguments: Optional[dict] = None, timeout_ms: int = 30000):
        result = await self._send_request("tools/call", {"name": name, "arguments": arguments or {}}, timeout_ms=timeout_ms)
        return {"success": True, "result": result}

    async def navigate(self, url: str, timeout_ms: int = 30000):
        tools_response = await self.list_tools(timeout_ms=timeout_ms)
        tools = tools_response.get("tools") or []
        names = [t.get("name", "") for t in tools if isinstance(t, dict)]
        tool_name = None
        if "navigate_page" in names:
            tool_name = "navigate_page"
        else:
            for name in names:
                if "navigate" in name:
                    tool_name = name
                    break
        if not tool_name:
            raise HTTPException(400, "navigate tool not found in MCP server")
        args = {"type": "url", "url": url} if tool_name == "navigate_page" else {"url": url}
        return await self.call_tool(tool_name, args, timeout_ms=timeout_ms)

    async def read_text(self, selector: Optional[str] = None, timeout_ms: int = 30000):
        tools_response = await self.list_tools(timeout_ms=timeout_ms)
        tools = tools_response.get("tools") or []
        names = [t.get("name", "") for t in tools if isinstance(t, dict)]
        primary_result = None
        text_value = ""
        if "evaluate_script" in names:
            function = "(sel) => { const el = sel ? document.querySelector(sel) : document.body; return el ? el.innerText : \"\"; }"
            args = [selector] if selector is not None else []
            primary_result = await self.call_tool("evaluate_script", {"function": function, "args": args}, timeout_ms=timeout_ms)
            if not self._result_has_error(primary_result):
                text_value = self._extract_text_from_eval_result(primary_result)
        fallback_result = None
        if (not text_value) and "take_snapshot" in names:
            fallback_result = await self.call_tool("take_snapshot", {}, timeout_ms=timeout_ms)
            if not self._result_has_error(fallback_result):
                text_value = self._extract_text_from_eval_result(fallback_result)
        if text_value:
            return {"success": True, "text": text_value, "length": len(text_value), "raw": {"primary": primary_result, "fallback": fallback_result}}
        if primary_result is None and fallback_result is None:
            raise HTTPException(400, "read_text requires evaluate_script or take_snapshot tool")
        return {"success": True, "text": "", "length": 0, "raw": {"primary": primary_result, "fallback": fallback_result}}

    def _extract_text_from_eval_result(self, result: dict) -> str:
        if not isinstance(result, dict):
            return ""
        target = result
        if "content" not in target and isinstance(target.get("result"), dict):
            target = target["result"]
        content = target.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parsed = self._extract_json_block(item.get("text", ""))
                    if parsed is None:
                        return item.get("text", "")
                    if isinstance(parsed, str):
                        return parsed
                    if parsed is not None:
                        return json.dumps(parsed, ensure_ascii=False)
        return ""

    def _extract_json_block(self, text: str):
        if not text:
            return None
        match = re.search(r"```json\\s*(.*?)\\s*```", text, re.S)
        if not match:
            match = re.search(r"```\\s*(.*?)\\s*```", text, re.S)
        if not match:
            return None
        payload = match.group(1).strip()
        try:
            return json.loads(payload)
        except Exception:
            return payload

    def _result_has_error(self, result: Optional[dict]) -> bool:
        if not isinstance(result, dict):
            return False
        target = result
        if isinstance(target.get("result"), dict):
            target = target["result"]
        return bool(target.get("isError"))

    def _default_args(self, channel_override: Optional[str] = None) -> list[str]:
        env_args = os.getenv("MCP_ARGS")
        if env_args:
            try:
                parsed = json.loads(env_args)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        ws = self._resolve_local_ws_endpoint()
        if ws:
            return ["chrome-devtools-mcp@latest", "--wsEndpoint", ws, "--no-usage-statistics"]
        channel = channel_override or os.getenv("MCP_CHANNEL", "stable")
        return ["chrome-devtools-mcp@latest", "--auto-connect", f"--channel={channel}", "--no-usage-statistics"]

    def _load_mcp_config(self) -> dict:
        if not os.path.exists(MCP_CONFIG_PATH):
            return {}
        try:
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _resolve_local_ws_endpoint(self) -> Optional[str]:
        info = self._read_devtools_active_port()
        if not info:
            return None
        port, path = info
        for host in ["127.0.0.1", "[::1]"]:
            ws = self._get_cdp_ws_endpoint(host, port)
            if ws:
                return ws
        return f"ws://127.0.0.1:{port}{path}"

    def _get_cdp_ws_endpoint(self, host: str, port: int) -> Optional[str]:
        url = f"http://{host}:{port}/json/version"
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, dict):
                return None
            ws = data.get("webSocketDebuggerUrl")
            if isinstance(ws, str) and ws.startswith("ws://"):
                return ws
            browser = data.get("Browser")
            if isinstance(browser, str) and browser:
                return f"ws://{host}:{port}/devtools/browser"
            return None
        except Exception:
            return None

    def _is_cdp_http_reachable(self, host: str, port: int) -> bool:
        return self._get_cdp_ws_endpoint(host, port) is not None

    def _read_devtools_active_port(self) -> Optional[tuple[int, str]]:
        candidates: list[str] = []
        configured_dir = os.getenv("BROWSER_USER_DATA_DIR") or DEFAULT_USER_DATA_DIR
        if configured_dir:
            candidates.append(os.path.join(configured_dir, "DevToolsActivePort"))
        base = os.getenv("LOCALAPPDATA")
        if base:
            candidates.append(os.path.join(base, "Google", "Chrome", "User Data", "DevToolsActivePort"))
        seen = set()
        for path in candidates:
            norm = os.path.normcase(os.path.abspath(path))
            if norm in seen:
                continue
            seen.add(norm)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                if len(lines) < 2:
                    continue
                port = int(lines[0])
                ws_path = lines[1]
                if not ws_path.startswith("/"):
                    ws_path = "/" + ws_path
                return port, ws_path
            except Exception:
                continue
        return None

    async def _send_notification(self, method: str, params: dict):
        if not self.process or not self.process.stdin:
            raise HTTPException(400, "MCP not running")
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        data = json.dumps(payload, ensure_ascii=False) + "\n"
        self.process.stdin.write(data.encode("utf-8"))
        await self.process.stdin.drain()

    async def _send_request(self, method: str, params: dict, timeout_ms: int = 30000):
        if not self.process or not self.process.stdin:
            raise HTTPException(400, "MCP not running")
        async with self._lock:
            self._request_id += 1
            req_id = self._request_id
            future = asyncio.get_running_loop().create_future()
            self._pending[req_id] = future
            payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            data = json.dumps(payload, ensure_ascii=False) + "\n"
            self.process.stdin.write(data.encode("utf-8"))
            await self.process.stdin.drain()
        try:
            return await asyncio.wait_for(future, timeout=timeout_ms / 1000)
        except Exception as e:
            self._pending.pop(req_id, None)
            logger.warning("MCP request failed method=%s id=%s timeout_ms=%s error=%s", method, req_id, timeout_ms, str(e))
            raise HTTPException(500, f"MCP request failed: {str(e)}")

    async def _read_stdout(self):
        if not self.process or not self.process.stdout:
            return
        while True:
            line = await self.process.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="ignore").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except Exception:
                continue
            msg_id = msg.get("id")
            if msg_id is None:
                continue
            future = self._pending.pop(msg_id, None)
            if not future:
                continue
            if "error" in msg:
                future.set_exception(RuntimeError(json.dumps(msg["error"], ensure_ascii=False)))
            else:
                future.set_result(msg.get("result"))
        logger.warning("MCP stdout closed pid=%s returncode=%s", self.process.pid if self.process else None, self.process.returncode if self.process else None)

    async def _read_stderr(self):
        if not self.process or not self.process.stderr:
            return
        while True:
            line = await self.process.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="ignore").strip()
            if text:
                logger.warning("MCP stderr: %s", text)
        logger.warning("MCP stderr closed pid=%s returncode=%s", self.process.pid if self.process else None, self.process.returncode if self.process else None)


browser_mgr = BrowserManager()
mcp_mgr = MCPManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Service startup")
    if AUTO_START:
        await browser_mgr.start()
    yield
    logger.info("Service shutdown")
    await mcp_mgr.stop()
    await browser_mgr.stop()


app = FastAPI(
    title="Browser Server",
    description="Playwright-based browser automation for OpenClawd",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    client = request.client.host if request.client else "-"
    url = str(request.url)
    status_code = 500
    path = request.url.path
    bypass_queue = path in {"/", "/health", "/queue/status", "/docs/raw", "/downloads", "/downloads/last", "/debug/info", "/network/requests"} or path.startswith("/network/request/") or path.startswith("/mcp/")
    request_id = uuid.uuid4().hex
    enqueue_time = time.time()
    if not bypass_queue:
        async with queue_condition:
            request_queue.append(request_id)
            start_position = len(request_queue)
            queue_condition.notify_all()
        async with queue_condition:
            while request_queue[0] != request_id:
                await queue_condition.wait()
    else:
        start_position = 0
    start_time = time.time()
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Queue-Request-Id"] = request_id
        response.headers["X-Queue-Start-Position"] = str(start_position)
        response.headers["X-Queue-Wait-Ms"] = str(int((start_time - enqueue_time) * 1000))
        return response
    except Exception as exc:
        logger.exception("HTTP %s %s %s 500 error=%s", client, request.method, url, exc)
        response = JSONResponse(status_code=500, content={"success": False, "error": "Internal Server Error"})
        response.headers["X-Queue-Request-Id"] = request_id
        response.headers["X-Queue-Start-Position"] = str(start_position)
        response.headers["X-Queue-Wait-Ms"] = str(int((start_time - enqueue_time) * 1000))
        return response
    finally:
        if not bypass_queue:
            async with queue_condition:
                if request_queue and request_queue[0] == request_id:
                    request_queue.popleft()
                elif request_id in request_queue:
                    request_queue.remove(request_id)
                queue_condition.notify_all()
        elapsed_ms = int((time.time() - start) * 1000)
        logger.info("HTTP %s %s %s %s %dms", client, request.method, url, status_code, elapsed_ms)


@app.get("/")
async def root():
    return {
        "service": "Browser Server",
        "version": "1.1.0",
        "status": "running",
        "browser": await browser_mgr.get_status(),
    }


@app.get("/health")
async def health():
    return await browser_mgr.get_status()


@app.get("/queue/status")
async def queue_status():
    async with queue_condition:
        current = request_queue[0] if request_queue else None
        total = len(request_queue)
        waiting = total - 1 if total > 0 else 0
    return {"success": True, "current_request_id": current, "queue_length": total, "waiting": waiting}


@app.get("/docs/raw")
async def docs_raw():
    path = os.path.abspath("API.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return PlainTextResponse(content)
    except Exception as e:
        raise HTTPException(500, f"Read docs failed: {str(e)}")


@app.post("/start")
async def start_browser(req: StartRequest = StartRequest()):
    return await browser_mgr.start(headless=req.headless, user_data_dir=req.user_data_dir, user_agent=req.user_agent, channel=req.channel, engine=req.engine)


@app.post("/mcp/start")
async def mcp_start(req: MCPStartRequest = MCPStartRequest()):
    return await mcp_mgr.ensure_started(command=req.command, args=req.args, timeout_ms=req.timeout_ms)

@app.post("/mcp/reconnect")
async def mcp_reconnect(req: MCPStartRequest = MCPStartRequest()):
    return await mcp_mgr.reconnect(timeout_ms=req.timeout_ms)


@app.post("/mcp/stop")
async def mcp_stop():
    return await mcp_mgr.stop()


@app.get("/mcp/status")
async def mcp_status():
    return mcp_mgr.status()


@app.get("/mcp/tools")
async def mcp_tools(timeout_ms: int = Query(30000)):
    return await mcp_mgr.list_tools(timeout_ms=timeout_ms)


async def _mcp_call_with_reconnect(name: str, arguments: Optional[dict] = None, timeout_ms: int = 30000):
    await mcp_mgr.ensure_started(timeout_ms=timeout_ms)
    try:
        return await mcp_mgr.call_tool(name=name, arguments=arguments, timeout_ms=timeout_ms)
    except HTTPException as e:
        if e.status_code == 500 and isinstance(e.detail, str) and "MCP request failed" in e.detail:
            await mcp_mgr.reconnect(timeout_ms=timeout_ms)
            return await mcp_mgr.call_tool(name=name, arguments=arguments, timeout_ms=timeout_ms)
        raise


def _mcp_extract_content_text(result: Optional[dict]) -> str:
    if not isinstance(result, dict):
        return ""
    payload = result.get("result")
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        return text
    return ""


def _mcp_extract_value(result: Optional[dict]):
    text = _mcp_extract_content_text(result)
    if not text:
        return None
    match = re.search(r"```json\s*(.*?)\s*```", text, re.S)
    if not match:
        match = re.search(r"```\s*(.*?)\s*```", text, re.S)
    if match:
        payload = match.group(1).strip()
        try:
            return json.loads(payload)
        except Exception:
            return payload
    try:
        return json.loads(text)
    except Exception:
        return text


async def _mcp_eval(function: str, args: Optional[list] = None, timeout_ms: int = 30000):
    return await _mcp_call_with_reconnect(
        name="evaluate_script",
        arguments={"function": function, "args": args or []},
        timeout_ms=timeout_ms,
    )


@app.post("/mcp/call")
async def mcp_call(req: MCPCallRequest):
    return await _mcp_call_with_reconnect(name=req.name, arguments=req.arguments, timeout_ms=req.timeout_ms)


@app.post("/mcp/tool/{tool_name}")
async def mcp_call_tool_by_path(tool_name: str, req: MCPToolInvokeRequest = MCPToolInvokeRequest()):
    return await _mcp_call_with_reconnect(name=tool_name, arguments=req.arguments, timeout_ms=req.timeout_ms)


@app.post("/mcp/call/batch")
async def mcp_call_batch(req: MCPBatchCallRequest):
    if not req.calls:
        raise HTTPException(400, "calls is required")
    await mcp_mgr.ensure_started(timeout_ms=req.timeout_ms)
    results = []
    for idx, item in enumerate(req.calls):
        try:
            result = await _mcp_call_with_reconnect(name=item.name, arguments=item.arguments, timeout_ms=req.timeout_ms)
            results.append({"index": idx, "name": item.name, "success": True, "result": result.get("result")})
        except HTTPException as e:
            results.append({"index": idx, "name": item.name, "success": False, "error": e.detail})
            if req.stop_on_error:
                break
    return {"success": all(x.get("success") for x in results), "results": results}


@app.post("/mcp/navigate")
async def mcp_navigate(req: MCPNavigateRequest):
    return await mcp_mgr.navigate(url=req.url, timeout_ms=req.timeout_ms)


@app.post("/mcp/open")
async def mcp_open(req: MCPNavigateRequest):
    await mcp_mgr.ensure_started(timeout_ms=req.timeout_ms)
    try:
        return await mcp_mgr.navigate(url=req.url, timeout_ms=req.timeout_ms)
    except HTTPException as e:
        if e.status_code == 500 and isinstance(e.detail, str) and "MCP request failed" in e.detail:
            await mcp_mgr.reconnect(timeout_ms=req.timeout_ms)
            return await mcp_mgr.navigate(url=req.url, timeout_ms=req.timeout_ms)
        raise


@app.post("/mcp/read")
async def mcp_read(req: MCPReadRequest):
    return await mcp_mgr.read_text(selector=req.selector, timeout_ms=req.timeout_ms)


@app.get("/mcp/network/requests")
async def mcp_network_requests(page_size: Optional[int] = Query(None), page_idx: Optional[int] = Query(None), timeout_ms: int = Query(30000)):
    arguments = {}
    if page_size is not None:
        arguments["pageSize"] = page_size
    if page_idx is not None:
        arguments["pageIdx"] = page_idx
    return await _mcp_call_with_reconnect(name="list_network_requests", arguments=arguments, timeout_ms=timeout_ms)


@app.get("/mcp/network/request")
async def mcp_network_request(reqid: Optional[int] = Query(None), timeout_ms: int = Query(30000)):
    arguments = {}
    if reqid is not None:
        arguments["reqid"] = reqid
    return await _mcp_call_with_reconnect(name="get_network_request", arguments=arguments, timeout_ms=timeout_ms)


@app.get("/mcp/console/messages")
async def mcp_console_messages(page_size: Optional[int] = Query(None), page_idx: Optional[int] = Query(None), timeout_ms: int = Query(30000)):
    arguments = {}
    if page_size is not None:
        arguments["pageSize"] = page_size
    if page_idx is not None:
        arguments["pageIdx"] = page_idx
    return await _mcp_call_with_reconnect(name="list_console_messages", arguments=arguments, timeout_ms=timeout_ms)


@app.post("/mcp/web/wait")
async def mcp_web_wait(req: MCPWebWaitRequest):
    deadline = time.time() + max(req.timeout_ms, 1) / 1000
    interval = max(req.poll_interval_ms, 50) / 1000
    selector_js = json.dumps(req.selector or "")
    text_js = json.dumps(req.text or "")
    script = f"() => {{ const sel = {selector_js}; const txt = {text_js}; if (sel) {{ const el = document.querySelector(sel); if (!el) return false; if (!txt) return true; const v = (el.innerText || el.textContent || '').trim(); return v.includes(txt); }} if (txt) {{ const body = (document.body && (document.body.innerText || document.body.textContent)) || ''; return body.includes(txt); }} return document.readyState === 'complete'; }}"
    while time.time() < deadline:
        try:
            result = await _mcp_eval(script, timeout_ms=min(req.timeout_ms, 10000))
        except HTTPException as e:
            if e.status_code == 500 and isinstance(e.detail, str) and "MCP request failed" in e.detail:
                await asyncio.sleep(interval)
                continue
            raise
        value = _mcp_extract_value(result)
        normalized = value.strip().lower() if isinstance(value, str) else None
        if req.selector or req.text:
            matched = value is True or normalized == "true"
        else:
            matched = value is True or normalized in {"true", "complete", "interactive"}
        if matched:
            return {"success": True, "selector": req.selector, "text": req.text, "matched": True}
        await asyncio.sleep(interval)
    return {"success": False, "selector": req.selector, "text": req.text, "matched": False}


@app.post("/mcp/web/click")
async def mcp_web_click(req: MCPWebClickRequest):
    wait_result = await mcp_web_wait(MCPWebWaitRequest(selector=req.selector, timeout_ms=req.timeout_ms, poll_interval_ms=req.poll_interval_ms))
    if not wait_result.get("matched"):
        raise HTTPException(408, f"Element not found: {req.selector}")
    selector_js = json.dumps(req.selector)
    script = f"() => {{ const sel = {selector_js}; const idx = {int(req.index)}; const nodes = document.querySelectorAll(sel); if (!nodes || nodes.length <= idx) return {{ ok:false, reason:'not_found', count:nodes ? nodes.length : 0 }}; const el = nodes[idx]; el.scrollIntoView({{block:'center', inline:'center'}}); el.click(); return {{ ok:true, count:nodes.length }}; }}"
    result = await _mcp_eval(script, timeout_ms=req.timeout_ms)
    value = _mcp_extract_value(result)
    if isinstance(value, dict) and value.get("ok"):
        return {"success": True, "selector": req.selector, "index": req.index, "raw": value}
    raise HTTPException(500, f"MCP click failed for selector: {req.selector}")


@app.post("/mcp/web/type")
async def mcp_web_type(req: MCPWebTypeRequest):
    wait_result = await mcp_web_wait(MCPWebWaitRequest(selector=req.selector, timeout_ms=req.timeout_ms))
    if not wait_result.get("matched"):
        raise HTTPException(408, f"Element not found: {req.selector}")
    selector_js = json.dumps(req.selector)
    text_js = json.dumps(req.text)
    clear_js = "true" if req.clear_first else "false"
    script = f"() => {{ const sel = {selector_js}; const val = {text_js}; const clearFirst = {clear_js}; const el = document.querySelector(sel); if (!el) return {{ ok:false, reason:'not_found' }}; const prev = (el.value ?? ''); const next = clearFirst ? val : (String(prev) + String(val)); el.focus(); el.value = next; el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); return {{ ok:true, length: String(next).length }}; }}"
    result = await _mcp_eval(script, timeout_ms=req.timeout_ms)
    value = _mcp_extract_value(result)
    if not (isinstance(value, dict) and value.get("ok")):
        raise HTTPException(500, f"MCP type failed for selector: {req.selector}")
    if req.submit_key:
        await _mcp_call_with_reconnect(name="press_key", arguments={"key": req.submit_key}, timeout_ms=req.timeout_ms)
    return {"success": True, "selector": req.selector, "length": value.get("length"), "submitted": bool(req.submit_key)}


@app.post("/mcp/web/scroll")
async def mcp_web_scroll(req: MCPWebScrollRequest):
    behavior_js = json.dumps(req.behavior or "auto")
    script = f"() => {{ window.scrollBy({{ left: {int(req.x)}, top: {int(req.y)}, behavior: {behavior_js} || 'auto' }}); return {{ ok:true, x: window.scrollX, y: window.scrollY }}; }}"
    result = await _mcp_eval(script, timeout_ms=req.timeout_ms)
    value = _mcp_extract_value(result)
    return {"success": True, "result": value}


@app.post("/mcp/web/html")
async def mcp_web_html(req: MCPWebHtmlRequest):
    selector_js = json.dumps(req.selector or "")
    script = f"() => {{ const sel = {selector_js}; const el = sel ? document.querySelector(sel) : document.documentElement; return el ? el.outerHTML : ''; }}"
    result = await _mcp_eval(script, timeout_ms=req.timeout_ms)
    value = _mcp_extract_value(result)
    text = value if isinstance(value, str) else ""
    return {"success": True, "html": text, "length": len(text), "selector": req.selector}


@app.post("/stop")
async def stop_browser():
    return await browser_mgr.stop()


@app.post("/navigate")
async def navigate(req: NavigateRequest):
    return await browser_mgr.navigate(url=req.url, wait_until=req.wait_until, timeout=req.timeout, extra_wait_ms=req.extra_wait_ms, wait_for_selector=req.wait_for_selector, wait_for_text=req.wait_for_text)


@app.post("/evaluate")
async def evaluate(req: EvaluateRequest):
    return await browser_mgr.evaluate(script=req.script, args=req.args, timeout=req.timeout)


@app.get("/text")
async def get_text(selector: Optional[str] = Query(None), timeout: int = Query(30000)):
    return await browser_mgr.get_text(selector, timeout)

@app.get("/current")
async def get_current(include_html: bool = Query(False), include_text: bool = Query(False), selector: Optional[str] = Query(None), timeout: int = Query(30000)):
    return await browser_mgr.get_current(include_html=include_html, include_text=include_text, selector=selector, timeout=timeout)

@app.get("/find")
async def find(selector: str = Query(...), text: Optional[str] = Query(None), limit: int = Query(20), timeout: int = Query(30000)):
    return await browser_mgr.find(selector=selector, text=text, limit=limit, timeout=timeout)


@app.post("/screenshot")
async def screenshot(req: ScreenshotRequest):
    return await browser_mgr.screenshot(full_page=req.full_page, selector=req.selector, timeout=req.timeout)


@app.post("/wait")
async def wait_for(req: WaitRequest):
    return await browser_mgr.wait_for(selector=req.selector, text=req.text, timeout=req.timeout)


@app.post("/click")
async def click(req: ClickRequest):
    return await browser_mgr.click(req.selector, req.timeout, text_contains=req.text_contains, index=req.index)


@app.post("/type")
async def type_text(req: TypeRequest):
    return await browser_mgr.type(selector=req.selector, text=req.text, timeout=req.timeout, clear_first=req.clear_first)

@app.post("/fill")
async def fill_text(req: FillRequest):
    return await browser_mgr.fill(selector=req.selector, value=req.value, timeout=req.timeout)

@app.post("/press")
async def press_key(req: PressRequest):
    return await browser_mgr.press(key=req.key, modifiers=req.modifiers, timeout=req.timeout)

@app.post("/drag")
async def drag(req: DragRequest):
    return await browser_mgr.drag(source=req.source, target=req.target, timeout=req.timeout)


@app.post("/scroll")
async def scroll(req: ScrollRequest):
    return await browser_mgr.scroll(direction=req.direction, to_bottom=req.to_bottom, amount=req.amount)

@app.post("/click/point")
async def click_point(req: ClickPointRequest):
    return await browser_mgr.click_point(x=req.x, y=req.y, button=req.button, clicks=req.clicks, delay=req.delay)

@app.post("/element/box")
async def element_box(req: ElementBoxRequest):
    return await browser_mgr.element_box(selector=req.selector, timeout=req.timeout)

@app.post("/upload")
async def upload(req: UploadRequest):
    return await browser_mgr.upload_files(selector=req.selector, paths=req.paths, timeout=req.timeout)

@app.post("/download/dir")
async def set_download_dir(req: DownloadDirRequest = DownloadDirRequest()):
    return await browser_mgr.set_download_dir(path=req.path)

@app.get("/downloads")
async def get_downloads():
    return await browser_mgr.get_downloads()

@app.get("/downloads/last")
async def get_last_download():
    return await browser_mgr.get_last_download()

@app.post("/download/await")
async def wait_download(req: DownloadWaitRequest = DownloadWaitRequest()):
    return await browser_mgr.wait_download(timeout=req.timeout)

@app.post("/download")
async def download(req: DownloadRequest):
    return await browser_mgr.download_url(url=req.url, path=req.path, timeout=req.timeout)

@app.post("/dialog/await")
async def wait_dialog(req: DialogWaitRequest = DialogWaitRequest()):
    return await browser_mgr.wait_dialog(timeout=req.timeout, action=req.action, prompt_text=req.prompt_text)

@app.post("/dialog/accept")
async def dialog_accept(req: DialogActionRequest = DialogActionRequest()):
    return await browser_mgr.dialog_accept(prompt_text=req.prompt_text)

@app.post("/dialog/dismiss")
async def dialog_dismiss():
    return await browser_mgr.dialog_dismiss()

@app.post("/page/close")
async def close_page():
    return await browser_mgr.close_page()

@app.post("/cdp/send")
async def cdp_send(req: CdpSendRequest):
    return await browser_mgr.cdp_send(method=req.method, params=req.params, timeout=req.timeout)

@app.get("/cdp/version")
async def cdp_version():
    return await browser_mgr.cdp_version()

@app.post("/cdp/dom/text")
async def cdp_dom_text(req: CdpDomRequest):
    return await browser_mgr.cdp_dom_text(selector=req.selector, timeout=req.timeout)

@app.post("/cdp/dom/html")
async def cdp_dom_html(req: CdpDomRequest):
    return await browser_mgr.cdp_dom_html(selector=req.selector, timeout=req.timeout)

@app.post("/cdp/dom/attributes")
async def cdp_dom_attributes(req: CdpDomRequest):
    return await browser_mgr.cdp_dom_attributes(selector=req.selector, timeout=req.timeout)

@app.get("/pages")
async def list_pages():
    return await browser_mgr.list_pages()

@app.post("/page/new")
async def new_page(req: NewPageRequest = NewPageRequest()):
    return await browser_mgr.new_page(url=req.url, wait_until=req.wait_until, timeout=req.timeout, extra_wait_ms=req.extra_wait_ms, wait_for_selector=req.wait_for_selector, wait_for_text=req.wait_for_text)

@app.post("/page/switch")
async def switch_page(req: SwitchPageRequest):
    return await browser_mgr.switch_page(id=req.id)

@app.post("/page/close_others")
async def close_others():
    return await browser_mgr.close_others()


@app.post("/storage/export")
async def export_storage(req: StorageExportRequest = StorageExportRequest()):
    return await browser_mgr.export_storage(path=req.path, include_json=req.include_json)

@app.post("/storage/import")
async def import_storage(req: StorageImportRequest = StorageImportRequest()):
    return await browser_mgr.import_storage(cookies=req.cookies, local_storage=req.local_storage, url=req.url, timeout=req.timeout)

@app.get("/network/requests")
async def network_requests(pattern: Optional[str] = Query(None), limit: int = Query(100), include_body: bool = Query(False)):
    return await browser_mgr.list_network_requests(pattern=pattern, limit=limit, include_body=include_body)

@app.get("/network/request/{request_id}")
async def network_request(request_id: str, include_body: bool = Query(False)):
    return await browser_mgr.get_network_request(request_id=request_id, include_body=include_body)

@app.get("/debug/info")
async def debug_info():
    return await browser_mgr.debug_info()

@app.get("/debug/snapshot")
async def debug_snapshot(timeout: int = Query(30000)):
    return await browser_mgr.debug_snapshot(timeout=timeout)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
