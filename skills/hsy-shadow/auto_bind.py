"""Automatic ticket-scoped binding; business credentials stay in the browser."""
from contextlib import nullcontext
import json
import os
import sys
import time
from urllib.parse import quote

import requests
from playwright.sync_api import sync_playwright

from bind import LEDGER, SITE, existing_page
from normal_chromium import normal_chromium_page


class BindingStopped(Exception):
    pass


def capture_auto(root, deadline, attached=False):
    context = root.context
    selected = None
    captured = {}

    def observe(request):
        nonlocal selected
        if captured or request.resource_type not in ("xhr", "fetch"):
            return
        match = LEDGER.match(request.url)
        if not match:
            return
        try:
            frame = request.frame
            page = frame.page
            ancestor = page
            while ancestor is not None and ancestor != root:
                ancestor = ancestor.opener()
            if ancestor != root or not frame.url.startswith(match[1]):
                return
            if not (page.url.startswith(SITE) or page.url.startswith(match[1])):
                return
            if selected is None:
                selected = match[1]
            if selected != match[1]:
                return
            headers = request.all_headers()
            bearer = headers.get("authorization", "")
            if bearer.startswith("Bearer ") and bearer[7:].strip():
                captured.update(business_url=selected, authorization=bearer,
                                cookie=headers.get("cookie", ""), provider="hsy",
                                label="好生意影子连接")
        except Exception:
            return

    def navigated(frame):
        nonlocal selected
        match = LEDGER.match(frame.url)
        if selected is None and match:
            ancestor = frame.page
            while ancestor is not None and ancestor != root:
                ancestor = ancestor.opener()
            if ancestor == root:
                selected = match[1]

    watched = []
    def watch(page):
        watched.append(page)
        page.on("framenavigated", navigated)
    watch(root)
    context.on("page", watch)
    context.on("request", observe)
    try:
        if attached:
            for frame in root.frames:
                navigated(frame)
            root.bring_to_front()
        else:
            root.goto(SITE, wait_until="domcontentloaded")
        while not captured:
            if time.monotonic() >= deadline:
                raise BindingStopped("timeout")
            pages = []
            for page in context.pages:
                ancestor = page
                while ancestor is not None and ancestor != root:
                    ancestor = ancestor.opener()
                if ancestor == root and not page.is_closed():
                    pages.append(page)
            if not pages:
                raise BindingStopped("cancelled")
            try:
                pages[0].wait_for_timeout(150)
            except Exception:
                if not context.browser.is_connected() or not context.pages:
                    raise BindingStopped("cancelled")
                raise
        return captured
    finally:
        context.remove_listener("request", observe)
        context.remove_listener("page", watch)
        for page in watched:
            page.remove_listener("framenavigated", navigated)


def submit(ticket, payload):
    response = requests.post("https://ivanc.wang/data/v2/shadow/hsy/submit",
                             headers={"Authorization": "Bearer " + ticket},
                             json=payload, timeout=45, allow_redirects=False)
    if response.status_code != 200:
        raise BindingStopped("ticket_expired" if response.status_code == 410 else "submit_failed")
    result = response.json()
    if result.get("status") != "ready" or not isinstance(result.get("connection_id"), str) or not result["connection_id"].strip():
        raise BindingStopped("submit_failed")
    return {"status": "ready", "connection_id": result["connection_id"]}


def result_page(context, status):
    message = "绑定完成，可以返回 Agent。" if status == "ready" else "绑定未完成，请返回 Agent 查看结果。"
    page = context.new_page()
    page.goto("data:text/html;charset=utf-8," + quote(
        "<!doctype html><html lang=zh><meta charset=utf-8><title>好生意绑定</title>"
        "<body style='font:24px sans-serif;padding:64px'><h1>" + message +
        "</h1><p>此窗口将在几秒后关闭。</p></body></html>"))
    page.wait_for_timeout(4000)
    page.close()


def main(existing=False):
    ticket = os.environ.pop("HSY_BIND_TICKET", "")
    if not ticket or len(ticket) > 8192:
        print(json.dumps({"status": "ticket_missing"}), flush=True)
        return 1
    with sync_playwright() as pw:
        pages = nullcontext(existing_page(pw, interactive=False)) if existing else normal_chromium_page(pw)
        with pages as root:
            result = {"status": "failed"}
            try:
                payload = capture_auto(root, time.monotonic() + 600, attached=existing)
                result = submit(ticket, payload)
            except BindingStopped as error:
                result = {"status": str(error)}
            except Exception:
                result = {"status": "failed"}
            print(json.dumps(result, ensure_ascii=True), flush=True)
            if root.context.browser.is_connected():
                try:
                    result_page(root.context, result["status"])
                except Exception:
                    pass
            return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    try:
        result = main()
    except (Exception, SystemExit):
        print(json.dumps({"status": "failed"}), flush=True)
        sys.exit(1)
    sys.exit(result)
