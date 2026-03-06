from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from playwright.sync_api import BrowserContext, Page, sync_playwright

from app.config import settings


class XhsError(Exception):
    pass


@dataclass
class QRLoginState:
    qr_image: str = ""
    timeout: str = "4m0s"
    is_logged_in: bool = False
    error: str = ""
    started_at: float = field(default_factory=time.time)
    ready: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)


class XhsAutomation:
    def __init__(self) -> None:
        self.storage_state_path = settings.storage_state_path
        self.download_dir = settings.download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._op_lock = threading.Lock()
        self._qr_lock = threading.Lock()
        self._qr_state: QRLoginState | None = None

    @contextmanager
    def _new_page(self, headless_override: bool | None = None) -> tuple[BrowserContext, Page]:
        with sync_playwright() as pw:
            headless = settings.HEADLESS if headless_override is None else bool(headless_override)
            browser = pw.chromium.launch(
                headless=headless,
                slow_mo=max(settings.BROWSER_SLOW_MO, 0),
            )
            context_kwargs: dict[str, Any] = {}
            if self.storage_state_path.exists():
                context_kwargs["storage_state"] = str(self.storage_state_path)
            if settings.USER_AGENT.strip():
                context_kwargs["user_agent"] = settings.USER_AGENT.strip()
            context = browser.new_context(**context_kwargs)
            context.set_default_timeout(settings.BROWSER_TIMEOUT_MS)
            page = context.new_page()
            try:
                yield context, page
            finally:
                context.close()
                browser.close()

    def _save_state(self, context: BrowserContext) -> None:
        context.storage_state(path=str(self.storage_state_path))

    def _goto(self, page: Page, url: str) -> None:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        self._raise_if_security_limited(page)

    @staticmethod
    def _raise_if_security_limited(page: Page) -> None:
        url = (page.url or "").lower()
        if "website-login/error" not in url:
            return
        body = ""
        try:
            body = (page.text_content("body") or "").strip()
        except Exception:
            body = ""
        hint = "小红书风控拦截(HTTP 461 / IP存在风险)。请切换稳定网络后重试。"
        if "ip存在风险" in body.lower():
            raise XhsError(hint)
        if body:
            raise XhsError(f"{hint} 页面提示: {body[:120]}")
        raise XhsError(hint)

    @staticmethod
    def _is_logged_in(page: Page) -> bool:
        return page.query_selector(".main-container .user .link-wrapper .channel") is not None

    @staticmethod
    def _strip_data_uri(value: str) -> str:
        if "," in value and value.startswith("data:image"):
            return value.split(",", 1)[1]
        return value

    def delete_cookies(self) -> dict[str, Any]:
        if self.storage_state_path.exists():
            self.storage_state_path.unlink()
        return {"success": True, "message": f"cookies deleted: {self.storage_state_path}"}

    def check_login_status(self) -> dict[str, Any]:
        with self._op_lock:
            with self._new_page() as (context, page):
                self._goto(page, "https://www.xiaohongshu.com/explore")
                logged_in = self._is_logged_in(page)
                username = ""
                if logged_in:
                    node = page.query_selector(".main-container .user .link-wrapper .channel")
                    if node:
                        username = (node.inner_text() or "").strip()
                    self._save_state(context)
                return {
                    "success": True,
                    "is_logged_in": logged_in,
                    "status": "logged_in" if logged_in else "not_logged_in",
                    "username": username,
                }

    def get_login_qrcode(self) -> dict[str, Any]:
        with self._qr_lock:
            if self._qr_state and not self._qr_state.done.is_set():
                state = self._qr_state
            else:
                state = QRLoginState()
                self._qr_state = state
                t = threading.Thread(target=self._run_qr_login_worker, args=(state,), daemon=True)
                t.start()

        state.ready.wait(timeout=20)
        if state.error:
            raise XhsError(state.error)
        if state.is_logged_in:
            return {"is_logged_in": True, "timeout": "0s", "img": ""}
        if not state.qr_image:
            raise XhsError("failed to obtain login qrcode")
        return {"is_logged_in": False, "timeout": state.timeout, "img": state.qr_image}

    def _run_qr_login_worker(self, state: QRLoginState) -> None:
        deadline = time.time() + 240
        try:
            # Login QR extraction is more reliable in headed mode.
            with self._new_page(headless_override=False) as (context, page):
                self._goto(page, "https://www.xiaohongshu.com/explore")
                if self._is_logged_in(page):
                    state.is_logged_in = True
                    state.timeout = "0s"
                    self._save_state(context)
                    state.ready.set()
                    return

                self._open_login_dialog_if_needed(page)
                src = self._find_qrcode_src(page)
                if not src:
                    raise XhsError("qrcode image not found")
                state.qr_image = self._strip_data_uri(src)
                state.ready.set()

                while time.time() < deadline:
                    if self._is_logged_in(page):
                        state.is_logged_in = True
                        self._save_state(context)
                        return
                    time.sleep(1.0)
        except Exception as exc:
            state.error = str(exc)
            state.ready.set()
        finally:
            state.done.set()

    @staticmethod
    def _open_login_dialog_if_needed(page: Page) -> None:
        if XhsAutomation._find_qrcode_src(page):
            return
        selectors = [
            "button.login-btn",
            ".login-btn",
            "button[class*='login']",
            "div[class*='login'] button",
            ".reds-button-primary",
            "a[href*='login']",
        ]
        for selector in selectors:
            try:
                node = page.query_selector(selector)
                if node and node.is_visible():
                    node.click()
                    page.wait_for_timeout(800)
                    if XhsAutomation._find_qrcode_src(page):
                        return
            except Exception:
                continue

    @staticmethod
    def _find_qrcode_src(page: Page) -> str:
        selectors = [
            ".login-container .qrcode-img",
            "img.qrcode-img",
            ".qrcode img",
            "img[src^='data:image']",
        ]
        for selector in selectors:
            try:
                src = page.get_attribute(selector, "src") or ""
                if src.strip():
                    return src.strip()
            except Exception:
                continue
        return ""

    def list_feeds(self) -> dict[str, Any]:
        with self._op_lock:
            with self._new_page() as (_, page):
                self._goto(page, "https://www.xiaohongshu.com")
                raw = page.evaluate(
                    """
                    () => {
                      if (window.__INITIAL_STATE__ &&
                          window.__INITIAL_STATE__.feed &&
                          window.__INITIAL_STATE__.feed.feeds) {
                        const feeds = window.__INITIAL_STATE__.feed.feeds;
                        const data = feeds.value !== undefined ? feeds.value : feeds._value;
                        if (data) return JSON.stringify(data);
                      }
                      return "";
                    }
                    """
                ) or ""
                if not raw:
                    raise XhsError("no feeds found in __INITIAL_STATE__")
                feeds = json.loads(raw)
                return {"feeds": feeds, "count": len(feeds)}

    def search_feeds(self, keyword: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        if not keyword.strip():
            raise XhsError("keyword is required")
        with self._op_lock:
            with self._new_page() as (_, page):
                query = urlencode({"keyword": keyword, "source": "web_explore_feed"})
                self._goto(page, f"https://www.xiaohongshu.com/search_result?{query}")
                page.wait_for_timeout(1200)
                self._apply_search_filters(page, filters or {})
                raw = page.evaluate(
                    """
                    () => {
                      if (window.__INITIAL_STATE__ &&
                          window.__INITIAL_STATE__.search &&
                          window.__INITIAL_STATE__.search.feeds) {
                        const feeds = window.__INITIAL_STATE__.search.feeds;
                        const data = feeds.value !== undefined ? feeds.value : feeds._value;
                        if (data) return JSON.stringify(data);
                      }
                      return "";
                    }
                    """
                ) or ""
                if not raw:
                    raise XhsError("no search feeds found in __INITIAL_STATE__")
                feeds = json.loads(raw)
                return {"feeds": feeds, "count": len(feeds)}

    def _apply_search_filters(self, page: Page, filters: dict[str, Any]) -> None:
        if not filters:
            return
        options = {
            "sort_by": {"综合": (1, 1), "最新": (1, 2), "最多点赞": (1, 3), "最多评论": (1, 4), "最多收藏": (1, 5)},
            "note_type": {"不限": (2, 1), "视频": (2, 2), "图文": (2, 3)},
            "publish_time": {"不限": (3, 1), "一天内": (3, 2), "一周内": (3, 3), "半年内": (3, 4)},
            "search_scope": {"不限": (4, 1), "已看过": (4, 2), "未看过": (4, 3), "已关注": (4, 4)},
            "location": {"不限": (5, 1), "同城": (5, 2), "附近": (5, 3)},
        }
        page.hover("div.filter")
        page.wait_for_selector("div.filter-panel", timeout=6000)
        page.wait_for_timeout(400)
        for key in ["sort_by", "note_type", "publish_time", "search_scope", "location"]:
            value = (filters.get(key) or "").strip()
            if not value or value not in options[key]:
                continue
            fidx, tidx = options[key][value]
            selector = f"div.filter-panel div.filters:nth-child({fidx}) div.tags:nth-child({tidx})"
            node = page.query_selector(selector)
            if node:
                node.click()
                page.wait_for_timeout(300)
        page.wait_for_timeout(1000)

    def get_feed_detail(self, feed_id: str, xsec_token: str, load_all_comments: bool = False, config: dict[str, Any] | None = None) -> dict[str, Any]:
        if not feed_id.strip() or not xsec_token.strip():
            raise XhsError("feed_id and xsec_token are required")
        with self._op_lock:
            with self._new_page() as (_, page):
                url = f"https://www.xiaohongshu.com/explore/{feed_id}?xsec_token={xsec_token}&xsec_source=pc_feed"
                self._goto(page, url)
                self._check_page_accessible(page)
                if load_all_comments:
                    self._load_comments(page, config or {})
                raw = page.evaluate(
                    """
                    () => {
                      if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.note && window.__INITIAL_STATE__.note.noteDetailMap) {
                        return JSON.stringify(window.__INITIAL_STATE__.note.noteDetailMap);
                      }
                      return "";
                    }
                    """
                ) or ""
                if not raw:
                    raise XhsError("no note detail map found")
                detail_map = json.loads(raw)
                data = detail_map.get(feed_id)
                if data is None:
                    for key, value in detail_map.items():
                        if feed_id in key:
                            data = value
                            break
                if data is None:
                    raise XhsError(f"feed {feed_id} not found in noteDetailMap")
                return data

    def _load_comments(self, page: Page, config: dict[str, Any]) -> None:
        max_comment_items = int(config.get("max_comment_items") or 0)
        click_more_replies = bool(config.get("click_more_replies") or False)
        max_replies_threshold = int(config.get("max_replies_threshold") or 10)
        no_comment = page.query_selector(".no-comments-text")
        if no_comment and "这是一片荒地" in (no_comment.inner_text() or ""):
            return
        attempts = max(40, max_comment_items * 3) if max_comment_items > 0 else 140
        stagnant = 0
        last_count = -1
        for _ in range(min(attempts, 500)):
            if click_more_replies:
                self._click_show_more_buttons(page, max_replies_threshold)
            count = len(page.query_selector_all(".parent-comment"))
            if max_comment_items > 0 and count >= max_comment_items:
                return
            if count == last_count:
                stagnant += 1
            else:
                stagnant = 0
                last_count = count
            if page.query_selector(".end-container"):
                return
            if stagnant > 15:
                page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(500)
                stagnant = 0
            else:
                page.evaluate("() => window.scrollBy(0, window.innerHeight * 0.8)")
                page.wait_for_timeout(300)

    def _click_show_more_buttons(self, page: Page, threshold: int) -> None:
        buttons = page.query_selector_all(".show-more")
        clicked = 0
        for btn in buttons:
            if clicked >= 4:
                break
            text = (btn.inner_text() or "").strip()
            if threshold > 0 and "展开" in text and "条回复" in text:
                digits = "".join([c for c in text if c.isdigit()])
                if digits and int(digits) > threshold:
                    continue
            try:
                btn.scroll_into_view_if_needed()
                btn.click()
                clicked += 1
                page.wait_for_timeout(250)
            except Exception:
                continue

    @staticmethod
    def _check_page_accessible(page: Page) -> None:
        node = page.query_selector(".access-wrapper, .error-wrapper, .not-found-wrapper, .blocked-wrapper")
        if not node:
            return
        text = (node.inner_text() or "").strip()
        if not text:
            return
        keywords = [
            "当前笔记暂时无法浏览", "该内容因违规已被删除", "该笔记已被删除", "内容不存在",
            "笔记不存在", "已失效", "私密笔记", "仅作者可见", "因用户设置，你无法查看", "因违规无法查看",
        ]
        for kw in keywords:
            if kw in text:
                raise XhsError(f"feed inaccessible: {kw}")
        raise XhsError(f"feed inaccessible: {text}")

    def user_profile(self, user_id: str, xsec_token: str) -> dict[str, Any]:
        if not user_id.strip() or not xsec_token.strip():
            raise XhsError("user_id and xsec_token are required")
        with self._op_lock:
            with self._new_page() as (_, page):
                url = f"https://www.xiaohongshu.com/user/profile/{user_id}?xsec_token={xsec_token}&xsec_source=pc_note"
                self._goto(page, url)
                page.wait_for_timeout(1200)
                user_raw = page.evaluate(
                    """
                    () => {
                      if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user && window.__INITIAL_STATE__.user.userPageData) {
                        const node = window.__INITIAL_STATE__.user.userPageData;
                        const data = node.value !== undefined ? node.value : node._value;
                        if (data) return JSON.stringify(data);
                      }
                      return "";
                    }
                    """
                ) or ""
                notes_raw = page.evaluate(
                    """
                    () => {
                      if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user && window.__INITIAL_STATE__.user.notes) {
                        const node = window.__INITIAL_STATE__.user.notes;
                        const data = node.value !== undefined ? node.value : node._value;
                        if (data) return JSON.stringify(data);
                      }
                      return "";
                    }
                    """
                ) or ""
                if not user_raw or not notes_raw:
                    raise XhsError("user profile data not found in __INITIAL_STATE__")
                user_data = json.loads(user_raw)
                notes_data = json.loads(notes_raw)
                flattened: list[dict[str, Any]] = []
                if isinstance(notes_data, list):
                    for chunk in notes_data:
                        if isinstance(chunk, list):
                            flattened.extend([x for x in chunk if isinstance(x, dict)])
                return {
                    "userBasicInfo": user_data.get("basicInfo", {}),
                    "interactions": user_data.get("interactions", []),
                    "feeds": flattened,
                }

    def post_comment(self, feed_id: str, xsec_token: str, content: str) -> dict[str, Any]:
        if not feed_id.strip() or not xsec_token.strip() or not content.strip():
            raise XhsError("feed_id, xsec_token and content are required")
        with self._op_lock:
            with self._new_page() as (_, page):
                url = f"https://www.xiaohongshu.com/explore/{feed_id}?xsec_token={xsec_token}&xsec_source=pc_feed"
                self._goto(page, url)
                self._check_page_accessible(page)
                box = page.query_selector("div.input-box div.content-edit span")
                if not box:
                    raise XhsError("comment input box not found")
                box.click()
                field = page.query_selector("div.input-box div.content-edit p.content-input")
                if not field:
                    raise XhsError("comment input field not found")
                field.fill(content)
                page.wait_for_timeout(500)
                submit = page.query_selector("div.bottom button.submit")
                if not submit:
                    raise XhsError("comment submit button not found")
                submit.click()
                page.wait_for_timeout(1000)
                return {"success": True, "feed_id": feed_id}

    def reply_comment(self, feed_id: str, xsec_token: str, content: str, comment_id: str = "", user_id: str = "") -> dict[str, Any]:
        if not feed_id.strip() or not xsec_token.strip() or not content.strip():
            raise XhsError("feed_id, xsec_token and content are required")
        if not comment_id.strip() and not user_id.strip():
            raise XhsError("comment_id or user_id is required")
        with self._op_lock:
            with self._new_page() as (_, page):
                url = f"https://www.xiaohongshu.com/explore/{feed_id}?xsec_token={xsec_token}&xsec_source=pc_feed"
                self._goto(page, url)
                self._check_page_accessible(page)
                page.wait_for_timeout(1200)
                comment_el = self._find_comment_element(page, comment_id, user_id)
                if not comment_el:
                    raise XhsError("target comment not found")
                reply_btn = comment_el.query_selector(".right .interactions .reply")
                if not reply_btn:
                    raise XhsError("reply button not found")
                reply_btn.click()
                page.wait_for_timeout(500)
                field = page.query_selector("div.input-box div.content-edit p.content-input")
                if not field:
                    raise XhsError("reply input field not found")
                field.fill(content)
                page.wait_for_timeout(400)
                submit = page.query_selector("div.bottom button.submit")
                if not submit:
                    raise XhsError("reply submit button not found")
                submit.click()
                page.wait_for_timeout(1200)
                return {"success": True, "feed_id": feed_id, "comment_id": comment_id, "user_id": user_id}

    def _find_comment_element(self, page: Page, comment_id: str, user_id: str) -> Any:
        for _ in range(100):
            if comment_id.strip():
                direct = page.query_selector(f"#comment-{comment_id.strip()}")
                if direct:
                    return direct
            if user_id.strip():
                user_node = page.query_selector(f'[data-user-id="{user_id.strip()}"]')
                if user_node:
                    handle = user_node.evaluate_handle("el => el.closest('.comment-item, .comment, .parent-comment')")
                    if handle:
                        as_el = handle.as_element()
                        if as_el:
                            return as_el
            if page.query_selector(".end-container"):
                return None
            page.evaluate("() => window.scrollBy(0, window.innerHeight * 0.8)")
            page.wait_for_timeout(450)
        return None

    def like_feed(self, feed_id: str, xsec_token: str, unlike: bool = False) -> dict[str, Any]:
        return self._toggle_interact(feed_id, xsec_token, action="like", cancel=unlike)

    def favorite_feed(self, feed_id: str, xsec_token: str, unfavorite: bool = False) -> dict[str, Any]:
        return self._toggle_interact(feed_id, xsec_token, action="favorite", cancel=unfavorite)

    def _toggle_interact(self, feed_id: str, xsec_token: str, action: str, cancel: bool) -> dict[str, Any]:
        if not feed_id.strip() or not xsec_token.strip():
            raise XhsError("feed_id and xsec_token are required")
        if action not in {"like", "favorite"}:
            raise XhsError(f"unsupported action: {action}")
        with self._op_lock:
            with self._new_page() as (_, page):
                url = f"https://www.xiaohongshu.com/explore/{feed_id}?xsec_token={xsec_token}&xsec_source=pc_feed"
                self._goto(page, url)
                self._check_page_accessible(page)
                page.wait_for_timeout(900)
                liked, collected = self._get_interact_state(page, feed_id)
                if action == "like":
                    if cancel:
                        if not liked:
                            return {"success": True, "feed_id": feed_id, "message": "already unliked"}
                        self._click_with_retry(page, ".interact-container .left .like-lottie")
                        return {"success": True, "feed_id": feed_id, "message": "unliked"}
                    if liked:
                        return {"success": True, "feed_id": feed_id, "message": "already liked"}
                    self._click_with_retry(page, ".interact-container .left .like-lottie")
                    return {"success": True, "feed_id": feed_id, "message": "liked"}

                if cancel:
                    if not collected:
                        return {"success": True, "feed_id": feed_id, "message": "already unfavorited"}
                    self._click_with_retry(page, ".interact-container .left .reds-icon.collect-icon")
                    return {"success": True, "feed_id": feed_id, "message": "unfavorited"}
                if collected:
                    return {"success": True, "feed_id": feed_id, "message": "already favorited"}
                self._click_with_retry(page, ".interact-container .left .reds-icon.collect-icon")
                return {"success": True, "feed_id": feed_id, "message": "favorited"}

    @staticmethod
    def _click_with_retry(page: Page, selector: str) -> None:
        for _ in range(2):
            node = page.query_selector(selector)
            if node:
                node.click()
                page.wait_for_timeout(900)

    @staticmethod
    def _get_interact_state(page: Page, feed_id: str) -> tuple[bool, bool]:
        raw = page.evaluate(
            """
            () => {
              if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.note && window.__INITIAL_STATE__.note.noteDetailMap) {
                return JSON.stringify(window.__INITIAL_STATE__.note.noteDetailMap);
              }
              return "";
            }
            """
        ) or ""
        if not raw:
            raise XhsError("no note detail map found")
        data = json.loads(raw)
        item = data.get(feed_id)
        if not item:
            raise XhsError(f"feed {feed_id} not found in noteDetailMap")
        interact = (item.get("note") or {}).get("interactInfo") or {}
        return bool(interact.get("liked")), bool(interact.get("collected"))

    def publish_content(self, title: str, content: str, images: list[str], tags: list[str] | None = None, schedule_at: str = "") -> dict[str, Any]:
        if not title.strip() or not content.strip() or not images:
            raise XhsError("title/content/images are required")
        image_paths = self._resolve_images(images)
        with self._op_lock:
            with self._new_page(headless_override=settings.PUBLISH_HEADLESS) as (_, page):
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                self._goto(page, "https://creator.xiaohongshu.com/publish/publish?source=official")
                page.wait_for_timeout(1600)
                self._enter_publish_editor(page, mode="image")
                self._click_publish_tab(page, "上传图文")
                self._ensure_publish_page_ready(page, mode="image")
                self._upload_images(page, image_paths)
                self._fill_publish_form(page, title, content, tags or [], schedule_at)
                click_start_ms = self._get_perf_now(page)
                submit = self._wait_publish_button(page, timeout_ms=180_000)
                if not self._safe_click(page, submit):
                    snap = self._debug_snapshot(page, "publish_button_click_failed")
                    raise XhsError(f"publish button click failed; url={page.url}; debug_screenshot={snap}")
                result = self._confirm_publish_result(page, click_start_ms=click_start_ms)
                return {"success": True, "images": len(image_paths), **result}

    def publish_with_video(self, title: str, content: str, video: str, tags: list[str] | None = None, schedule_at: str = "") -> dict[str, Any]:
        if not title.strip() or not content.strip() or not video.strip():
            raise XhsError("title/content/video are required")
        video_path = Path(video).expanduser().resolve()
        if not video_path.exists():
            raise XhsError(f"video not found: {video_path}")
        with self._op_lock:
            with self._new_page(headless_override=settings.PUBLISH_HEADLESS) as (_, page):
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                self._goto(page, "https://creator.xiaohongshu.com/publish/publish?source=official")
                page.wait_for_timeout(1600)
                self._enter_publish_editor(page, mode="video")
                self._click_publish_tab(page, "上传视频")
                self._ensure_publish_page_ready(page, mode="video")
                self._upload_video(page, str(video_path))
                self._fill_publish_form(page, title, content, tags or [], schedule_at)
                click_start_ms = self._get_perf_now(page)
                submit = self._wait_publish_button(page, timeout_ms=600_000)
                if not self._safe_click(page, submit):
                    snap = self._debug_snapshot(page, "publish_button_click_failed")
                    raise XhsError(f"publish button click failed; url={page.url}; debug_screenshot={snap}")
                result = self._confirm_publish_result(page, click_start_ms=click_start_ms)
                return {"success": True, "video": str(video_path), **result}

    @staticmethod
    def _confirm_publish_result(page: Page, timeout_ms: int = 35_000, click_start_ms: float = 0.0) -> dict[str, Any]:
        success_keywords = ("发布成功", "发布完成")
        pending_keywords = ("发布中", "审核中", "提交成功", "已提交", "处理中")
        validation_fail_keywords = (
            "请先上传图片",
            "请填写标题",
            "请填写正文",
            "标题不能为空",
            "正文不能为空",
            "内容不能为空",
            "发布失败",
        )
        risk_keywords = (
            "ip存在风险",
            "账号存在风险",
            "环境存在风险",
            "环境异常",
            "异常行为",
            "操作过于频繁",
            "请进行验证",
            "请先完成验证",
            "验证码",
            "安全验证",
            "发布受限",
            "无法发布",
        )
        last_url = page.url or ""
        reclick_count = 0
        saw_publish_signal = False
        last_signal_url = ""
        last_ui_hints: list[str] = []
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            try:
                XhsAutomation._wait_loading_mask(page, timeout_ms=4_000)
            except Exception:
                page.wait_for_timeout(500)

            current_url = page.url or ""
            body_text = ""
            try:
                body_text = (page.text_content("body") or "").strip()
            except Exception:
                body_text = ""
            normalized = body_text.replace(" ", "").replace("\n", "")

            if any(keyword in normalized for keyword in risk_keywords):
                snap = XhsAutomation._debug_snapshot(page, "publish_blocked_by_risk")
                raise XhsError(f"publish blocked by risk control; url={current_url}; debug_screenshot={snap}")

            if any(keyword in normalized for keyword in success_keywords):
                return {"status": "published", "message": "publish confirmed by ui", "url": current_url}

            if any(keyword in normalized for keyword in pending_keywords):
                return {"status": "submitted", "message": "publish submitted and pending review", "url": current_url}

            ui_hints = XhsAutomation._collect_ui_hints(page)
            if ui_hints:
                last_ui_hints = ui_hints
                hint_text = " | ".join(ui_hints).lower()
                if any(
                    k in hint_text
                    for k in ("失败", "错误", "异常", "不能为空", "超出", "含有", "违规", "限制", "请先", "禁止发笔记", "社区规范")
                ):
                    snap = XhsAutomation._debug_snapshot(page, "publish_ui_hint_failed")
                    raise XhsError(
                        f"publish blocked by ui hint: {ui_hints}; url={current_url}; debug_screenshot={snap}"
                    )

            for keyword in validation_fail_keywords:
                if keyword in normalized:
                    snap = XhsAutomation._debug_snapshot(page, "publish_validation_failed")
                    raise XhsError(
                        f"publish validation failed: {keyword}; url={current_url}; debug_screenshot={snap}"
                    )

            # Some publish flows show a second confirmation dialog.
            if XhsAutomation._click_button_by_text(page, ("确认发布", "继续发布", "确定发布")):
                page.wait_for_timeout(900)
                continue
            if XhsAutomation._click_button_by_text(page, ("我知道了", "确定", "继续")):
                page.wait_for_timeout(700)
                continue

            signal_urls = XhsAutomation._collect_publish_request_signals(page, click_start_ms=click_start_ms)
            if signal_urls:
                saw_publish_signal = True
                last_signal_url = signal_urls[-1]

            lowered = current_url.lower()
            if (
                "creator.xiaohongshu.com" in lowered
                and "/publish/publish" not in lowered
                and "login" not in lowered
            ):
                return {"status": "submitted", "message": "publish flow left editor page", "url": current_url}

            # If still on publish editor after several seconds, retry click once or twice.
            elapsed_ms = int((time.time() - start) * 1000)
            if "/publish/publish" in lowered and elapsed_ms > 8000 and reclick_count < 2:
                btn = page.query_selector(".publish-page-publish-btn button.bg-red")
                if btn:
                    try:
                        if btn.is_visible():
                            text = (btn.inner_text() or "").strip()
                            disabled = btn.get_attribute("disabled")
                            cls = btn.get_attribute("class") or ""
                            if "发布中" in text:
                                return {"status": "submitted", "message": "publish in progress", "url": current_url}
                            if disabled is None and "disabled" not in cls:
                                if XhsAutomation._safe_click(page, btn):
                                    reclick_count += 1
                                    page.wait_for_timeout(1200)
                                    continue
                    except Exception:
                        pass

            if current_url != last_url:
                last_url = current_url
            page.wait_for_timeout(700)

        if saw_publish_signal:
            return {
                "status": "submitted",
                "message": "publish request observed, waiting platform review",
                "url": page.url,
                "signal_url": last_signal_url,
            }

        btn_state = XhsAutomation._get_publish_button_state(page)
        snap = XhsAutomation._debug_snapshot(page, "publish_not_confirmed")
        raise XhsError(
            f"publish submitted but not confirmed; url={page.url}; btn_state={btn_state}; "
            f"ui_hints={last_ui_hints}; debug_screenshot={snap}"
        )

    @staticmethod
    def _get_perf_now(page: Page) -> float:
        try:
            value = page.evaluate("() => Number(window.performance && performance.now ? performance.now() : 0)")
            return float(value or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _collect_publish_request_signals(page: Page, click_start_ms: float = 0.0) -> list[str]:
        try:
            entries = page.evaluate(
                """
                (startAt) => {
                  const start = Number(startAt || 0);
                  const rows = performance.getEntriesByType('resource') || [];
                  return rows
                    .filter((e) => (e.initiatorType === 'fetch' || e.initiatorType === 'xmlhttprequest'))
                    .filter((e) => Number(e.startTime || 0) >= Math.max(0, start - 100))
                    .map((e) => String(e.name || ''))
                    .slice(-120);
                }
                """,
                click_start_ms,
            )
        except Exception:
            return []
        urls = [str(x) for x in (entries or []) if x]
        signals: list[str] = []
        for url in urls:
            u = url.lower()
            if "publish/publish?source=official" in u:
                continue
            if any(k in u for k in ("draft", "autosave", "/save", "upload")):
                continue
            looks_publish = (
                ("publish" in u and ("api" in u or "web_api" in u or "sns" in u))
                or ("/note/" in u and ("create" in u or "publish" in u or "submit" in u))
            )
            if looks_publish:
                signals.append(url)
        return signals

    @staticmethod
    def _collect_ui_hints(page: Page) -> list[str]:
        selectors = [
            ".ant-message .ant-message-notice-content",
            ".ant-notification-notice-message",
            ".ant-notification-notice-description",
            ".toast",
            ".message",
            "[role='alert']",
            "[aria-live='polite']",
            "[aria-live='assertive']",
            ".error",
            ".warning",
        ]
        seen: set[str] = set()
        hints: list[str] = []
        for selector in selectors:
            try:
                nodes = page.query_selector_all(selector)
            except Exception:
                continue
            for node in nodes[:8]:
                try:
                    if not node.is_visible():
                        continue
                    text = (node.inner_text() or "").strip()
                    if not text:
                        continue
                    short = text[:120]
                    if short in seen:
                        continue
                    seen.add(short)
                    hints.append(short)
                except Exception:
                    continue
        return hints[:6]

    @staticmethod
    def _get_publish_button_state(page: Page) -> dict[str, Any]:
        state: dict[str, Any] = {"found": False}
        try:
            btn = page.query_selector(".publish-page-publish-btn button.bg-red")
            if not btn:
                return state
            state["found"] = True
            state["visible"] = bool(btn.is_visible())
            state["text"] = (btn.inner_text() or "").strip()
            state["disabled"] = btn.get_attribute("disabled")
            state["class"] = btn.get_attribute("class") or ""
        except Exception as exc:
            state["error"] = str(exc)
        return state

    def _resolve_images(self, images: list[str]) -> list[str]:
        resolved: list[str] = []
        for raw in images:
            value = (raw or "").strip()
            if not value:
                continue
            if value.lower().startswith(("http://", "https://")):
                resolved.append(self._download_image(value))
            else:
                path = Path(value).expanduser().resolve()
                if not path.exists():
                    raise XhsError(f"image not found: {path}")
                resolved.append(str(path))
        if not resolved:
            raise XhsError("no valid images after resolving inputs")
        return resolved

    def _download_image(self, url: str) -> str:
        suffix = Path(url.split("?")[0]).suffix or ".jpg"
        out = self.download_dir / f"{uuid.uuid4().hex}{suffix}"
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            out.write_bytes(resp.content)
        return str(out)

    @staticmethod
    def _click_publish_tab(page: Page, tab_text: str) -> None:
        def click_with_retry(el: Any) -> bool:
            for _ in range(6):
                try:
                    XhsAutomation._wait_loading_mask(page, timeout_ms=10_000)
                except Exception:
                    page.wait_for_timeout(500)
                try:
                    el.scroll_into_view_if_needed()
                except Exception:
                    pass
                try:
                    if XhsAutomation._safe_click(page, el):
                        page.wait_for_timeout(600)
                        return True
                except Exception:
                    page.wait_for_timeout(500)
                    continue
            return False

        tabs = (
            page.query_selector_all("div.creator-tab")
            or page.query_selector_all(".tabs .tab")
            or page.query_selector_all("[role='tab']")
            or page.query_selector_all("button")
        )
        normalized_expect = (tab_text or "").strip()
        keyword_groups = {
            "上传图文": ("图文", "上传图文", "发布图文"),
            "上传视频": ("视频", "上传视频", "发布视频"),
        }
        expected_keywords = keyword_groups.get(normalized_expect, (normalized_expect,))

        # 1) exact match
        for tab in tabs:
            text = (tab.inner_text() or "").strip()
            if text == normalized_expect:
                if click_with_retry(tab):
                    return

        # 2) fuzzy keyword match
        for tab in tabs:
            text = (tab.inner_text() or "").strip()
            if any(keyword and keyword in text for keyword in expected_keywords):
                if click_with_retry(tab):
                    return

        # Some pages default to one mode and do not expose a reliable tab switch.
        return

    @staticmethod
    def _wait_loading_mask(page: Page, timeout_ms: int = 10_000) -> None:
        selectors = [
            "[data-testid='loading']",
            ".css-1pfcknm",
            ".loading",
            "[class*='loading']",
            "[class*='skeleton']",
            ".ant-spin-spinning",
        ]
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            blocking = False
            try:
                for selector in selectors:
                    node = page.query_selector(selector)
                    if node and node.is_visible():
                        blocking = True
                        break
            except Exception:
                # Page may be navigating; wait and retry.
                page.wait_for_timeout(300)
                continue
            if not blocking:
                return
            page.wait_for_timeout(300)

    @staticmethod
    def _safe_click(page: Page, node: Any) -> bool:
        for _ in range(5):
            try:
                XhsAutomation._wait_loading_mask(page, timeout_ms=8_000)
            except Exception:
                page.wait_for_timeout(350)
            try:
                node.scroll_into_view_if_needed()
            except Exception:
                pass
            try:
                node.click(timeout=2500)
                return True
            except Exception:
                pass
            try:
                node.click(timeout=2500, force=True)
                return True
            except Exception:
                pass
            try:
                node.evaluate("el => el.click()")
                return True
            except Exception:
                pass
            try:
                box = node.bounding_box()
                if box:
                    x = box["x"] + box["width"] / 2
                    y = box["y"] + box["height"] / 2
                    page.mouse.move(x, y)
                    page.mouse.click(x, y, delay=120)
                    return True
            except Exception:
                pass
            page.wait_for_timeout(450)
            continue
        return False

    @staticmethod
    def _ensure_publish_page_ready(page: Page, mode: str = "image") -> None:
        url = (page.url or "").lower()
        if "creator.xiaohongshu.com" not in url:
            raise XhsError(f"unexpected publish url: {page.url}")
        if "login" in url and not XhsAutomation._is_publish_editor(page):
            raise XhsError("creator center not logged in")
        XhsAutomation._wait_loading_mask(page, timeout_ms=12_000)
        if not XhsAutomation._is_publish_editor(page):
            XhsAutomation._enter_publish_editor(page, mode=mode)
        if not XhsAutomation._is_publish_editor(page):
            snap = XhsAutomation._debug_snapshot(page, "publish_editor_not_ready")
            raise XhsError(f"publish editor not ready; url={page.url}; debug_screenshot={snap}")

    @staticmethod
    def _is_publish_editor(page: Page) -> bool:
        url = (page.url or "").lower()
        if "creator.xiaohongshu.com" not in url:
            return False
        has_upload = False
        for selector in (".upload-input", "input[type='file']", "input[accept*='image']", "input[accept*='video']"):
            try:
                node = page.query_selector(selector)
                if node:
                    has_upload = True
                    break
            except Exception:
                continue
        if not has_upload:
            return False
        if "/publish/publish" in url:
            return True
        body_text = ""
        try:
            body_text = (page.text_content("body") or "").strip()
        except Exception:
            body_text = ""
        return "发布笔记" in body_text or "上传图文" in body_text or "上传视频" in body_text

    @staticmethod
    def _enter_publish_editor(page: Page, mode: str = "image") -> None:
        if XhsAutomation._is_publish_editor(page):
            return
        for attempt in range(4):
            XhsAutomation._wait_creator_shell_ready(page, timeout_ms=15_000)
            if XhsAutomation._is_publish_editor(page):
                return

            XhsAutomation._click_publish_entry(page, mode=mode)
            if XhsAutomation._wait_publish_editor(page, timeout_ms=12_000):
                return

            # Fallback routes: creator home -> publish page -> refresh.
            if attempt == 0:
                try:
                    page.goto("https://creator.xiaohongshu.com/", wait_until="domcontentloaded")
                except Exception:
                    pass
            elif attempt == 1:
                try:
                    page.goto("https://creator.xiaohongshu.com/publish/publish?source=official", wait_until="domcontentloaded")
                except Exception:
                    pass
            else:
                try:
                    page.reload(wait_until="domcontentloaded")
                except Exception:
                    pass
            page.wait_for_timeout(1400)

    @staticmethod
    def _wait_publish_editor(page: Page, timeout_ms: int = 12_000) -> bool:
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            if XhsAutomation._is_publish_editor(page):
                return True
            page.wait_for_timeout(350)
        return False

    @staticmethod
    def _wait_creator_shell_ready(page: Page, timeout_ms: int = 15_000) -> None:
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            if XhsAutomation._is_publish_editor(page):
                return
            if XhsAutomation._has_publish_trigger(page):
                return
            if "login" in (page.url or "").lower():
                return
            page.wait_for_timeout(400)

    @staticmethod
    def _has_publish_trigger(page: Page) -> bool:
        if XhsAutomation._has_button_text(page, ("发布笔记", "去发布", "发布")):
            return True
        for selector in (".publish-button", "button[class*='publish']", "a[href*='/publish/']"):
            try:
                node = page.query_selector(selector)
                if node and node.is_visible():
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _click_publish_entry(page: Page, mode: str = "image") -> None:
        XhsAutomation._click_button_by_text(page, ("发布笔记", "去发布", "发布"))
        page.wait_for_timeout(450)
        if mode == "video":
            option = ("上传视频", "发布视频", "视频笔记", "视频")
        else:
            option = ("上传图文", "发布图文", "图文笔记", "图文")
        XhsAutomation._click_button_by_text(page, option)
        page.wait_for_timeout(900)

    @staticmethod
    def _has_button_text(page: Page, texts: tuple[str, ...]) -> bool:
        try:
            nodes = page.query_selector_all("button, a, [role='button'], div")
        except Exception:
            return False
        for node in nodes[:240]:
            try:
                if not node.is_visible():
                    continue
                text = (node.inner_text() or "").strip()
                if any(key and key in text for key in texts):
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _click_button_by_text(page: Page, texts: tuple[str, ...]) -> bool:
        try:
            nodes = page.query_selector_all("button, a, [role='button'], div")
        except Exception:
            return False
        for node in nodes[:320]:
            try:
                if not node.is_visible():
                    continue
                text = (node.inner_text() or "").strip()
                if not any(key and key in text for key in texts):
                    continue
                try:
                    node.scroll_into_view_if_needed()
                except Exception:
                    pass
                node.click(timeout=2500)
                return True
            except Exception:
                continue
        return False

    @staticmethod
    def _upload_images(page: Page, image_paths: list[str]) -> None:
        for idx, path in enumerate(image_paths):
            selectors = [
                ".upload-input",
                "input[type='file']",
                "input[accept*='image']",
                "input[multiple]",
            ]
            def try_upload() -> bool:
                for selector in selectors:
                    nodes = page.query_selector_all(selector)
                    if not nodes:
                        continue
                    for node in nodes:
                        try:
                            node.set_input_files(path)
                            return True
                        except Exception:
                            continue
                return False

            uploaded = try_upload()
            if not uploaded:
                # If page got stuck on "上传视频", force switch to image tab then retry.
                XhsAutomation._click_publish_tab(page, "上传图文")
                page.wait_for_timeout(900)
                uploaded = try_upload()
            if not uploaded:
                # Fallback: trigger native file chooser via visible upload button.
                uploaded = XhsAutomation._upload_via_file_chooser(page, path)
            if not uploaded:
                snap = XhsAutomation._debug_snapshot(page, "upload_input_not_found")
                raise XhsError(
                    f"upload input not found for image {idx + 1}; "
                    f"url={page.url}; debug_screenshot={snap}"
                )

            ok = XhsAutomation._wait_image_count(page, idx + 1, timeout_ms=90_000)
            if not ok:
                # Retry one more time via upload button when no preview appears.
                XhsAutomation._upload_via_file_chooser(page, path)
                ok = XhsAutomation._wait_image_count(page, idx + 1, timeout_ms=40_000)
            if not ok:
                snap = XhsAutomation._debug_snapshot(page, "image_upload_timeout")
                raise XhsError(
                    f"image upload timeout for image {idx + 1}; "
                    f"url={page.url}; debug_screenshot={snap}"
                )

        # Some layouts show title/content only after at least one image is fully processed.
        if not XhsAutomation._wait_title_editor_ready(page, timeout_ms=20_000):
            snap = XhsAutomation._debug_snapshot(page, "title_input_not_found")
            raise XhsError(f"title input not found after upload; url={page.url}; debug_screenshot={snap}")

    @staticmethod
    def _upload_via_file_chooser(page: Page, image_path: str) -> bool:
        trigger_selectors = [
            "button:has-text('上传图片')",
            "text=上传图片",
            "text=点击上传",
            ".upload-btn",
            ".upload-trigger",
        ]
        for selector in trigger_selectors:
            try:
                node = page.query_selector(selector)
                if not node or not node.is_visible():
                    continue
                with page.expect_file_chooser(timeout=3500) as fc_info:
                    if not XhsAutomation._safe_click(page, node):
                        continue
                chooser = fc_info.value
                chooser.set_files(image_path)
                page.wait_for_timeout(800)
                return True
            except Exception:
                continue
        return False

    @staticmethod
    def _wait_title_editor_ready(page: Page, timeout_ms: int = 20_000) -> bool:
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            node = XhsAutomation._first_visible(
                page,
                [
                    "div.d-input input",
                    "input[placeholder*='标题']",
                    "input[placeholder*='输入标题']",
                    "input[maxlength]",
                ],
            )
            if node:
                return True
            page.wait_for_timeout(400)
        return False

    @staticmethod
    def _wait_image_count(page: Page, expected: int, timeout_ms: int) -> bool:
        start = time.time()
        preview_selectors = [
            ".img-preview-area .pr",
            ".img-preview-area img",
            ".upload-list img",
            "[class*='preview'] img",
            ".img-container img",
            ".upload-picture-card img",
            "img[src^='blob:']",
            "img[src^='data:image']",
        ]
        while (time.time() - start) * 1000 < timeout_ms:
            count = 0
            for selector in preview_selectors:
                try:
                    count = max(count, len(page.query_selector_all(selector)))
                except Exception:
                    continue
            if count >= expected:
                return True
            page.wait_for_timeout(400)
        return False

    @staticmethod
    def _fill_publish_form(page: Page, title: str, content: str, tags: list[str], schedule_at: str) -> None:
        XhsAutomation._wait_loading_mask(page, timeout_ms=10_000)
        title_el = XhsAutomation._first_visible(
            page,
            [
                "div.d-input input",
                "input[placeholder*='标题']",
                "input[placeholder*='输入标题']",
                "input[maxlength]",
                "input[type='text']",
            ],
        )
        if not title_el:
            snap = XhsAutomation._debug_snapshot(page, "title_input_not_found")
            raise XhsError(f"title input not found; url={page.url}; debug_screenshot={snap}")
        try:
            title_el.fill(title)
        except Exception:
            title_el.click()
            page.keyboard.press("Control+A")
            page.keyboard.type(title, delay=20)
        page.wait_for_timeout(300)

        content_el = XhsAutomation._first_visible(
            page,
            [
                "div.ql-editor",
                "[role='textbox']",
                "[contenteditable='true']",
                "textarea[placeholder*='正文']",
                "textarea",
            ],
        )
        if not content_el:
            snap = XhsAutomation._debug_snapshot(page, "content_input_not_found")
            raise XhsError(f"content input not found; url={page.url}; debug_screenshot={snap}")
        try:
            content_el.fill(content)
        except Exception:
            content_el.click()
            page.keyboard.type(content, delay=12)
        page.wait_for_timeout(200)

        for tag in tags[:10]:
            clean = tag.lstrip("#").strip()
            if not clean:
                continue
            content_el.type(f" #{clean}")
            page.wait_for_timeout(80)

        if schedule_at.strip():
            XhsAutomation._set_schedule_publish(page, schedule_at.strip())

    @staticmethod
    def _first_visible(page: Page, selectors: list[str]):
        for selector in selectors:
            nodes = page.query_selector_all(selector)
            for node in nodes:
                try:
                    if node.is_visible():
                        return node
                except Exception:
                    continue
        return None

    @staticmethod
    def _debug_snapshot(page: Page, prefix: str) -> str:
        try:
            debug_dir = settings.download_dir / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            out = debug_dir / f"{prefix}_{uuid.uuid4().hex[:8]}.png"
            page.screenshot(path=str(out), full_page=True)
            return str(out)
        except Exception:
            return ""

    @staticmethod
    def _set_schedule_publish(page: Page, schedule_at: str) -> None:
        sw = page.query_selector(".post-time-wrapper .d-switch")
        if not sw:
            raise XhsError("schedule switch not found")
        sw.click()
        page.wait_for_timeout(300)

        inp = page.query_selector(".date-picker-container input")
        if not inp:
            raise XhsError("schedule datetime input not found")
        value = schedule_at.replace("T", " ")
        if "+" in value:
            value = value.split("+", 1)[0]
        if value.endswith("Z"):
            value = value[:-1]
        if len(value) >= 16:
            value = value[:16]
        inp.fill(value)
        page.wait_for_timeout(300)

    @staticmethod
    def _upload_video(page: Page, video_path: str) -> None:
        node = page.query_selector(".upload-input") or page.query_selector("input[type='file']")
        if not node:
            raise XhsError("video upload input not found")
        node.set_input_files(video_path)
        XhsAutomation._wait_publish_button(page, timeout_ms=600_000)

    @staticmethod
    def _wait_publish_button(page: Page, timeout_ms: int):
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            btn = page.query_selector(".publish-page-publish-btn button.bg-red")
            if btn:
                disabled = btn.get_attribute("disabled")
                cls = btn.get_attribute("class") or ""
                visible = btn.is_visible()
                if visible and disabled is None and "disabled" not in cls:
                    return btn
            page.wait_for_timeout(700)
        raise XhsError("publish button not clickable before timeout")
