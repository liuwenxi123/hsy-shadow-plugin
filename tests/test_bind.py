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


def test_owned_edge_default_context_cleanup(monkeypatch):
    import os
    import pytest
    import psutil
    import normal_edge
    if os.name != "nt":
        pytest.skip("Windows Edge integration")
    try:
        normal_edge.edge_executable()
    except RuntimeError:
        pytest.skip("Edge missing")

    observed = {}
    original = normal_edge.owned_endpoint
    def inspect_endpoint(process, profile):
        endpoint = original(process, profile)
        observed.update(process=process, profile=profile, endpoint=endpoint)
        assert profile.is_dir()
        assert str(profile) in " ".join(psutil.Process(process.pid).cmdline())
        assert endpoint.startswith("http://127.0.0.1:")
        return endpoint
    monkeypatch.setattr(normal_edge, "owned_endpoint", inspect_endpoint)

    with sync_playwright() as pw:
        with normal_edge.normal_edge_page(pw) as page:
            assert page.context == page.context.browser.contexts[0]
            assert page.url == "about:blank"
            page.set_content("<title>owned Edge</title>")
            assert page.title() == "owned Edge"
    assert observed["process"].poll() is not None
    assert not observed["profile"].exists()
