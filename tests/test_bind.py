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


def test_owned_chromium_default_context_cleanup(monkeypatch):
    import os
    import pytest
    import psutil
    import normal_chromium as launcher
    if os.name != "nt":
        pytest.skip("Windows Chromium integration")
    observed = {}
    original = launcher.owned_endpoint
    def inspect_endpoint(process, port):
        args = psutil.Process(process.pid).cmdline()
        profile = Path(next(arg.split("=",1)[1] for arg in args if arg.startswith("--user-data-dir=")))
        assert "--window-size=1280,900" in args
        assert f"--remote-debugging-port={port}" in args and port > 0
        endpoint = original(process, port)
        observed.update(process=process, profile=profile, endpoint=endpoint)
        assert profile.is_dir()
        assert str(profile) in " ".join(psutil.Process(process.pid).cmdline())
        assert endpoint.startswith("http://127.0.0.1:")
        return endpoint
    monkeypatch.setattr(launcher, "owned_endpoint", inspect_endpoint)

    with sync_playwright() as pw:
        with launcher.normal_chromium_page(pw) as page:
            assert page.context == page.context.browser.contexts[0]
            assert page.context.browser.version == "153.0.8010.12"
            assert page.url == "about:blank"
            page.set_content("<title>owned Edge</title>")
            assert page.title() == "owned Edge"
    assert observed["process"].poll() is not None
    assert not observed["profile"].exists()


def test_missing_configured_browser_fails_with_install_help(monkeypatch, tmp_path):
    import pytest
    import normal_chromium as launcher
    monkeypatch.setenv("HSY_BROWSER_EXECUTABLE", str(tmp_path / "absent.exe"))
    monkeypatch.setenv("HSY_BROWSER_VERSION", launcher.BROWSER_VERSION)
    with pytest.raises(SystemExit, match="playwright install chromium"):
        launcher.chromium_executable(None)


def test_wrong_running_browser_rejected(monkeypatch):
    import os
    import pytest
    import normal_chromium as launcher
    if os.name != "nt":
        pytest.skip("Windows Chromium integration")
    with sync_playwright() as pw:
        monkeypatch.setattr(launcher, "BROWSER_VERSION", "0.0.0.0")
        monkeypatch.delenv("HSY_BROWSER_VERSION", raising=False)
        with pytest.raises(SystemExit, match="实际浏览器版本"):
            with launcher.normal_chromium_page(pw):
                pytest.fail("Wrong browser version accepted")
