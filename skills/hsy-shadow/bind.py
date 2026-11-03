"""Capture a ledger-scoped session in memory and submit to the fixed cloud."""
import argparse
import getpass
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from playwright.sync_api import sync_playwright

DEST = "https://134.175.43.116/data/v2/connections/session"
LEDGER = re.compile(r"(https://cloud[0-9]*\.chanjet\.com/hsy/[A-Za-z0-9]+/[A-Za-z0-9]+/)")
SITE = "https://hsy.chanjet.com/"


def existing_page(pw):
    for vendor in ("Microsoft/Edge", "Google/Chrome"):
        root = Path(os.environ["LOCALAPPDATA"]) / vendor / "User Data"
        try:
            port = int((root / "DevToolsActivePort").read_text().splitlines()[0])
            if not 1 <= port <= 65535:
                continue
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=3000)
        except Exception:
            continue
        pages = [p for ctx in browser.contexts for p in ctx.pages
                 if p.url.startswith(SITE) or LEDGER.match(p.url)]
        if len(pages) == 1:
            return pages[0]
    raise SystemExit("未发现唯一可接入的好生意页面。请使用独立登录模式。")


def capture(page, attached):
    session = {}
    def observe(req):
        match = LEDGER.match(req.url)
        if not match or req.resource_type not in ("fetch", "xhr"):
            return
        # Limit capture to the visible ledger or its same-site embedded frame.
        frame = req.frame
        if not frame or frame.page != page or not (LEDGER.match(page.url) or page.url.startswith(SITE)):
            return
        if not (frame.url.startswith(match[1]) or page.url.startswith(match[1])):
            return
        headers = req.all_headers()
        auth = headers.get("authorization", "")
        if auth.startswith("Bearer "):
            session.update(business_url=match[1], authorization=auth, cookie=headers.get("cookie", ""))
    page.on("request", observe)
    try:
        if not attached:
            page.goto(SITE, wait_until="domcontentloaded")
        print("请在此页面进入目标账套并打开商品分类等只读页面。")
        deadline = time.monotonic() + 300
        while not session and not page.is_closed() and time.monotonic() < deadline:
            page.wait_for_timeout(250)
        if not session:
            raise SystemExit("未捕获目标账套的业务授权。")
        return session
    finally:
        page.remove_listener("request", observe)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--existing", action="store_true")
    parser.add_argument("--connection-id")
    args = parser.parse_args()
    token = os.getenv("HSY_PLATFORM_TOKEN") or getpass.getpass("本人云平台访问密钥: ")
    with sync_playwright() as pw:
        page = existing_page(pw) if args.existing else pw.chromium.launch(channel="msedge", headless=False).new_page()
        payload = capture(page, args.existing)
    print("账套:", payload["business_url"], "目的地:", DEST, "连接:", args.connection_id or "新建")
    if input("允许云端保存本次会话并代查此账套？输入 YES 确认: ").strip() != "YES":
        raise SystemExit("已取消，未上传。")
    payload.update(provider="hsy", label="好生意影子连接")
    if args.connection_id:
        payload["connection_id"] = args.connection_id
    response = requests.post(DEST, headers={"Authorization": "Bearer " + token},
                             json=payload, timeout=45, allow_redirects=False)
    if response.status_code != 200:
        raise SystemExit(f"导入未确认成功，HTTP {response.status_code}。请先检查本人连接状态。")
    result = response.json()
    if result.get("status") != "ready" or not result.get("connection_id"):
        raise SystemExit("云端未确认连接就绪。")
    print("ready", result["connection_id"])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit("绑定未完成。请检查网络、浏览器、账套及平台权限。")
