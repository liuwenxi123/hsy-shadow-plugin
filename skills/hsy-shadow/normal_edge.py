"""Own a temporary Windows Edge instance and attach to its default context."""
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import psutil


def edge_executable():
    for name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        location = os.environ.get(name)
        if location:
            candidate = Path(location) / "Microsoft/Edge/Application/msedge.exe"
            if candidate.is_file():
                return candidate
    raise RuntimeError("Edge is not installed")


def owned_endpoint(process, profile):
    owner = psutil.Process(process.pid)
    deadline = time.monotonic() + 30
    while process.poll() is None and time.monotonic() < deadline:
        try:
            port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
            listeners = [c.laddr.ip for c in owner.connections(kind="tcp")
                         if c.status == psutil.CONN_LISTEN and c.laddr.port == port]
            if listeners and set(listeners) == {"127.0.0.1"}:
                return f"http://127.0.0.1:{port}"
        except (FileNotFoundError, ValueError, IndexError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Edge did not start its own loopback listener")


@contextmanager
def normal_edge_page(pw):
    with tempfile.TemporaryDirectory(prefix="hsy-shadow-edge-") as directory:
        profile = Path(directory)
        process = subprocess.Popen([
            str(edge_executable()), f"--user-data-dir={profile}", "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1", "--no-first-run",
            "--no-default-browser-check", "--disable-background-mode", "about:blank",
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = None
        try:
            endpoint = owned_endpoint(process, profile)
            browser = pw.chromium.connect_over_cdp(endpoint, timeout=10000)
            contexts = browser.contexts
            if len(contexts) != 1:
                raise RuntimeError("Expected Edge default context")
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
