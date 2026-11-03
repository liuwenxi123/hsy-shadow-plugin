"""Capture a ledger-scoped session in memory and submit to the fixed cloud."""
import argparse
from contextlib import nullcontext
import getpass
import os
import re
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import Error as PlaywrightError, sync_playwright

from normal_edge import normal_edge_page

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
        if pages:
            for index, page in enumerate(pages, 1):
                match = LEDGER.match(page.url)
                print(index, match[1] if match else SITE)
            choice = input("请选择好生意标签页序号，直接回车取消：").strip()
            if choice not in {str(i) for i in range(1, len(pages) + 1)}:
                raise SystemExit("已取消，未上传。")
            return pages[int(choice) - 1]
    raise SystemExit("未发现可接入的好生意页面。请使用独立登录模式。")


def ledger_pages(root):
    """Consider only the chosen tab and windows transitively opened by it."""
    choices = []
    for page in root.context.pages:
        ancestor = page
        while ancestor is not None and ancestor != root:
            ancestor = ancestor.opener()
        if ancestor != root or page.is_closed():
            continue
        if not (page.url.startswith(SITE) or LEDGER.match(page.url)):
            continue
        ledgers = set()
        for frame in page.frames:
            match = LEDGER.match(frame.url)
            if match:
                ledgers.add(match[1])
        choices.extend((page, ledger) for ledger in sorted(ledgers))
    return choices


def capture(root, attached):
    if not attached:
        root.goto(SITE, wait_until="domcontentloaded")
    input("请在该窗口或它打开的子窗口进入目标账套，然后在此按回车选择。")
    # Synchronous stdin paused Playwright dispatch while the user opened the ledger.
    try:
        root.wait_for_timeout(100)
    except PlaywrightError:
        if not root.is_closed():
            raise
    choices = ledger_pages(root)
    if not choices:
        raise SystemExit("未发现可绑定的账套页面，请先进入目标账套。")
    for index, (_, ledger) in enumerate(choices, 1):
        print(index, ledger)
    selection = input("输入要绑定的账套序号，直接回车取消：").strip()
    if selection not in {str(i) for i in range(1, len(choices) + 1)}:
        raise SystemExit("已取消，未上传。")
    page, selected = choices[int(selection) - 1]
    page.bring_to_front()
    session = {}

    def observe(req):
        if session or not req.url.startswith(selected) or req.resource_type not in ("fetch", "xhr"):
            return
        if not (page.url.startswith(SITE) or page.url.startswith(selected)):
            return
        try:
            frame = req.frame
            if frame.page != page or not frame.url.startswith(selected):
                return
            headers = req.all_headers()
        except Exception:
            return
        auth = headers.get("authorization", "")
        if auth.startswith("Bearer ") and auth[7:].strip():
            session.update(business_url=selected, authorization=auth, cookie=headers.get("cookie", ""))

    page.on("request", observe)
    try:
        print("请在所选账套打开商品分类等只读页面。")
        deadline = time.monotonic() + 300
        while not session and not page.is_closed() and time.monotonic() < deadline:
            page.wait_for_timeout(250)
        if not session:
            raise SystemExit("未捕获所选账套的业务授权。")
        return session
    finally:
        page.remove_listener("request", observe)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--existing", action="store_true")
    parser.add_argument("--connection-id")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        raise SystemExit("需要用户在本地交互终端选择账套并确认。")

    with sync_playwright() as pw:
        pages = nullcontext(existing_page(pw)) if args.existing else normal_edge_page(pw)
        with pages as page:
            payload = capture(page, args.existing)
    print("账套:", payload["business_url"], "目的地:", DEST, "连接:", args.connection_id or "新建")
    if input("允许云端保存本次会话并代查此账套？输入 YES 确认: ").strip() != "YES":
        raise SystemExit("已取消，未上传。")
    token = os.getenv("HSY_PLATFORM_TOKEN") or getpass.getpass("本人云平台访问密钥: ")
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
    if args.connection_id and args.connection_id != result["connection_id"]:
        raise SystemExit("云端返回了不同的连接 ID，请检查本人连接状态。")
    print("ready", result["connection_id"])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit("绑定未完成。请检查网络、浏览器、账套及平台权限。")
