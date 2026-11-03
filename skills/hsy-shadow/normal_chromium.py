"""Own a temporary headed Chromium instance and attach to its default context."""
import os
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import psutil


BROWSER_VERSION = "153.0.8010.12"
INSTALL_HELP = ('安装指定浏览器：python -m pip install playwright==1.63.0；'
                'python -m playwright install chromium；也可将 HSY_BROWSER_EXECUTABLE 指向同版本可执行文件。')


def chromium_executable(pw):
    version = os.environ.get("HSY_BROWSER_VERSION") or BROWSER_VERSION
    if version != BROWSER_VERSION:
        raise SystemExit(f"本版本要求 Chromium {BROWSER_VERSION}。{INSTALL_HELP}")
    candidate = Path(os.environ.get("HSY_BROWSER_EXECUTABLE") or pw.chromium.executable_path)
    if not candidate.is_file():
        raise SystemExit(INSTALL_HELP)
    return candidate


def owned_endpoint(process, port):
    owner = psutil.Process(process.pid)
    deadline = time.monotonic() + 30
    while process.poll() is None and time.monotonic() < deadline:
        try:
            listeners = [c.laddr.ip for c in owner.connections(kind="tcp")
                         if c.status == psutil.CONN_LISTEN and c.laddr.port == port]
            if listeners and set(listeners) == {"127.0.0.1"}:
                return f"http://127.0.0.1:{port}"
        except (FileNotFoundError, ValueError, IndexError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Chromium did not start its own loopback listener")


@contextmanager
def normal_chromium_page(pw):
    with tempfile.TemporaryDirectory(prefix="hsy-shadow-chromium-") as directory:
        profile = Path(directory)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        process = subprocess.Popen([
            str(chromium_executable(pw)), f"--user-data-dir={profile}", "--no-first-run",
            "--window-size=1280,900", "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={port}", "about:blank",
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = None
        try:
            endpoint = owned_endpoint(process, port)
            browser = pw.chromium.connect_over_cdp(endpoint, timeout=10000)
            if browser.version != BROWSER_VERSION:
                raise SystemExit(f"实际浏览器版本 {browser.version}，要求 {BROWSER_VERSION}。{INSTALL_HELP}")
            contexts = browser.contexts
            if len(contexts) != 1:
                raise RuntimeError("Expected Chromium default context")
            pages = contexts[0].pages
            yield pages[0] if pages else contexts[0].new_page()
        finally:
            if browser is not None and browser.is_connected():
                try:
                    browser.new_browser_cdp_session().send("Browser.close")
                except Exception:
                    pass  # CDP may disconnect before the close response.
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                children = psutil.Process(process.pid).children(recursive=True)
                process.kill()
                for child in children:
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                process.wait(timeout=5)
                psutil.wait_procs(children, timeout=5)
