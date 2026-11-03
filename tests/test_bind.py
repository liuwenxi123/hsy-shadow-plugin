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


def test_platform_login_and_revoke_after_import_failure(monkeypatch):
    from unittest.mock import MagicMock
    import pytest
    monkeypatch.setattr(sys, "argv", ["bind.py", "--existing", "--platform-login"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(bind, "sync_playwright", MagicMock())
    monkeypatch.setattr(bind, "existing_page", MagicMock())
    monkeypatch.setattr(bind, "capture", lambda *args: {"business_url": "fixture"})
    answers = iter(["YES", "fixture-user"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(bind.getpass, "getpass", lambda _: "fixture-password")
    responses = [
        MagicMock(status_code=200, json=lambda: {"access_token": "access", "refresh_token": "refresh"}),
        MagicMock(status_code=403),
        MagicMock(status_code=200, json=lambda: {"ok": True}),
    ]
    post = MagicMock(side_effect=responses)
    monkeypatch.setattr(bind.requests, "post", post)
    with pytest.raises(SystemExit, match="HTTP 403"):
        bind.main()
    assert [c.args[0] for c in post.call_args_list] == [
        "https://ivanc.wang/auth/login", bind.DEST, "https://ivanc.wang/auth/logout"]
    assert post.call_args_list[0].kwargs["json"]["audience"] == "data-service"
    assert post.call_args_list[2].kwargs["json"] == {"refresh_token": "refresh"}
    assert all(c.kwargs["allow_redirects"] is False for c in post.call_args_list)


def test_rejected_platform_login(monkeypatch):
    from unittest.mock import MagicMock
    import pytest
    monkeypatch.setattr("builtins.input", lambda _: "fixture")
    monkeypatch.setattr(bind.getpass, "getpass", lambda _: "fixture")
    post = MagicMock(return_value=MagicMock(status_code=401))
    monkeypatch.setattr(bind.requests, "post", post)
    with pytest.raises(SystemExit, match="平台登录失败"):
        bind.platform_login()
    assert post.call_count == 1


def test_auto_submit_is_scoped(monkeypatch):
    import auto_bind
    from unittest.mock import MagicMock
    import pytest
    post = MagicMock(return_value=MagicMock(status_code=200, json=lambda: {
        "status": "ready", "connection_id": "fixture-id", "secret": "must-not-return"}))
    monkeypatch.setattr(auto_bind.requests, "post", post)
    result = auto_bind.submit("fixture-ticket", {"provider": "hsy"})
    assert result == {"status": "ready", "connection_id": "fixture-id"}
    assert post.call_args.args[0] == "https://ivanc.wang/data/v2/shadow/hsy/submit"
    assert post.call_args.kwargs["allow_redirects"] is False
    post.return_value.status_code = 410
    with pytest.raises(auto_bind.BindingStopped, match="ticket_expired"):
        auto_bind.submit("fixture-ticket", {"provider": "hsy"})


def test_auto_real_browser_popup_without_terminal(monkeypatch, capsys):
    import auto_bind
    import requests
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from unittest.mock import patch
    from normal_chromium import normal_chromium_page

    submitted = []
    class Endpoint(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            submitted.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ready","connection_id":"fixture-id"}')
    server = HTTPServer(("127.0.0.1", 0), Endpoint)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    original_post = requests.post
    def local_post(url, **kwargs):
        assert url == "https://ivanc.wang/data/v2/shadow/hsy/submit"
        return original_post(f"http://127.0.0.1:{server.server_port}/", **kwargs)
    monkeypatch.setattr(auto_bind.requests, "post", local_post)
    monkeypatch.setenv("HSY_BIND_TICKET", "fixture-ticket")
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("TTY used")))
    first = "https://cloud1.chanjet.com/hsy/test/ledger1/"
    from contextlib import contextmanager
    @contextmanager
    def browser(pw):
        with normal_chromium_page(pw) as root:
            def route_handler(route):
                if route.request.url == bind.SITE:
                    body = f"<a id=enter target=_blank href='{first}'>进入</a>"
                else:
                    body = """<script>setTimeout(()=>fetch('probe',{headers:{Authorization:'Bearer synthetic'}}),300)</script>"""
                route.fulfill(body=body, content_type="text/html")
            root.context.route("**/*", route_handler)
            root.on("domcontentloaded", lambda: root.locator("#enter").click() if root.url == bind.SITE else None)
            yield root
    monkeypatch.setattr(auto_bind, "normal_chromium_page", browser)
    try:
        auto_bind.main()
        assert json.loads(capsys.readouterr().out) == {"status":"ready","connection_id":"fixture-id"}
        assert len(submitted) == 1
        assert submitted[0]["business_url"] == first
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_auto_network_failure_is_not_retried(monkeypatch):
    import auto_bind
    import requests
    import pytest
    from unittest.mock import MagicMock
    post = MagicMock(side_effect=requests.ConnectionError("synthetic"))
    monkeypatch.setattr(auto_bind.requests, "post", post)
    with pytest.raises(requests.ConnectionError):
        auto_bind.submit("fixture-ticket", {})
    assert post.call_count == 1


def test_existing_auto_keeps_user_page(monkeypatch):
    import auto_bind
    import time
    from normal_chromium import normal_chromium_page
    first = "https://cloud1.chanjet.com/hsy/test/ledger1/"
    with sync_playwright() as pw:
        with normal_chromium_page(pw) as page:
            page.context.route("**/*", lambda route: route.fulfill(body="<title>User page</title>"))
            page.goto(first)
            page.evaluate("""() => setTimeout(()=>fetch('probe', {
                headers:{Authorization:'Bearer fixture'}}), 500)""")
            result = auto_bind.capture_auto(page, time.monotonic()+5, attached=True)
            assert result["business_url"] == first
            assert page.url == first
            assert not page.is_closed()
            assert page.context.browser.is_connected()


def test_missing_ticket_is_structured_failure(monkeypatch, capsys):
    import auto_bind
    import json
    monkeypatch.delenv("HSY_BIND_TICKET", raising=False)
    assert auto_bind.main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "ticket_missing"
