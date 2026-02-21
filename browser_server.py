import asyncio
import base64
import os
import json
import urllib.request
import logging
import time
import uuid
import re
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
DEFAULT_CHANNEL = os.getenv("BROWSER_CHANNEL") or "chrome"
DEFAULT_DOWNLOAD_DIR = os.getenv("BROWSER_DOWNLOAD_DIR", os.path.abspath("downloads"))
LOG_LEVEL = os.getenv("BROWSER_LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("BROWSER_LOG_FILE", os.path.abspath(os.path.join("logs", "app.log")))
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
        entry = {
            "id": entry_id,
            "request_object_id": request_object_id,
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
            "headers": dict(request.headers),
            "post_data": request.post_data,
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
    async def start(self, headless: Optional[bool] = None, user_data_dir: Optional[str] = None, user_agent: Optional[str] = None, channel: Optional[str] = None):
        if self.context:
            return {"success": True, "message": "Browser already running"}

        self.playwright = await async_playwright().start()

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
        self.context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)

        await self.context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});"
        )

        self.user_data_dir = launch_user_data_dir
        self.headless = launch_headless
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        os.makedirs(self.download_dir, exist_ok=True)
        self._attach_page_listeners(self.page)
        self.context.on("page", lambda p: self._attach_page_listeners(p))
        self.context.on("request", lambda r: asyncio.create_task(self._handle_request(r)))
        self.context.on("response", lambda r: asyncio.create_task(self._handle_response(r)))
        logger.info("Browser started headless=%s user_data_dir=%s channel=%s", self.headless, self.user_data_dir, launch_channel)
        return {"success": True, "message": "Browser started", "headless": self.headless, "user_data_dir": self.user_data_dir}

    async def stop(self):
        if not self.context:
            return {"success": True, "message": "Browser not running"}

        try:
            await self.context.close()
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
            return {"running": False, "url": None, "title": None, "headless": None, "user_data_dir": None}
        if self.page:
            await self._ensure_page()
        title = await self.page.title() if self.page else None
        return {
            "running": True,
            "url": self.page.url if self.page else None,
            "title": title,
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


browser_mgr = BrowserManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Service startup")
    if AUTO_START:
        await browser_mgr.start()
    yield
    logger.info("Service shutdown")
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
    bypass_queue = path in {"/", "/health", "/queue/status", "/docs/raw", "/downloads", "/downloads/last", "/debug/info", "/network/requests"} or path.startswith("/network/request/")
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
    return await browser_mgr.start(headless=req.headless, user_data_dir=req.user_data_dir, user_agent=req.user_agent, channel=req.channel)


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
