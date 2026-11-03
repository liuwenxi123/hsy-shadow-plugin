"""Browser-level regression coverage with synthetic, locally intercepted requests."""
import sys
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "hsy-shadow"))
import bind


def test_popup_ledger_binding():
    first = "https://cloud1.chanjet.com/hsy/tenant1/ledger1/"
    second = "https://cloud1.chanjet.com/hsy/tenant1/ledger2/"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=pw.chromium.executable_path)
        context = browser.new_context()
        context.route("**/*", lambda route: route.fulfill(
            body="<html>fixture</html>", content_type="text/html"))
        root = context.new_page()
        root.goto(bind.SITE)
        unrelated = context.new_page()
        unrelated.goto(first)
        with root.expect_popup() as event:
            root.evaluate("url => window.open(url)", second)
        popup = event.value
        popup.wait_for_load_state()
        assert bind.ledger_pages(root) == [(popup, second)]

        def answer(prompt):
            if "序号" in prompt:
                popup.evaluate("""other => setTimeout(async () => {
                    await fetch(other + 'wrong', {headers:{Authorization:'Bearer wrong'}});
                    await fetch('right', {headers:{Authorization:'Bearer fixture'}});
                }, 500)""", first)
                return "1"
            return ""

        with patch("builtins.input", answer):
            session = bind.capture(root, True)
        assert session["business_url"] == second
        assert session["authorization"] == "Bearer fixture"
        browser.close()


def test_cancel_does_not_post(monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setenv("HSY_PLATFORM_TOKEN", "synthetic")
    monkeypatch.setattr(sys, "argv", ["bind.py", "--existing"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(bind, "sync_playwright", MagicMock())
    monkeypatch.setattr(bind, "existing_page", MagicMock())
    monkeypatch.setattr(bind, "capture", lambda *args: {"business_url": "fixture"})
    post = MagicMock()
    monkeypatch.setattr(bind.requests, "post", post)
    monkeypatch.setattr("builtins.input", lambda _: "")
    import pytest
    with pytest.raises(SystemExit, match="取消"):
        bind.main()
    post.assert_not_called()
