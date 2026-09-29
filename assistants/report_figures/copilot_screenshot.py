"""Figure 10 of the final report: the copilot screen after a real question.

With the prepaid service and the copilot running, run (one line):
    uv run --no-project --python 3.12 --with websocket-client --with pillow
        python copilot_screenshot.py copilot_screen.png

Drives a headless Edge through the DevTools protocol: types an employee's name, asks what is
wrong with a tower and for a work order, waits for the draft under the reply, then captures
the main column from the alert banner to the draft, as the report's other screenshots
show the main area only.
"""

import base64
import io
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket
from PIL import Image

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9556
APP = "http://127.0.0.1:8502"
NAME = "Taha"
QUESTION = "What is wrong with DAS18M1? Draft a remote check for it."
SCALE = 2

profile = tempfile.mkdtemp(prefix="edge-shot-")
edge = subprocess.Popen(
    [
        EDGE,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={profile}",
        "--window-size=1280,1000",
        "--no-first-run",
        "--disable-extensions",
        "about:blank",
    ]
)
try:
    for _ in range(50):
        try:
            targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
            page = next(t for t in targets if t["type"] == "page")
            break
        except Exception:
            time.sleep(0.2)
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
    counter = iter(range(1, 10_000))

    def send(method, **params):
        message_id = next(counter)
        ws.send(json.dumps({"id": message_id, "method": method, "params": params}))
        while True:
            reply = json.loads(ws.recv())
            if reply.get("id") == message_id:
                return reply.get("result", {})

    def js(expression):
        return send("Runtime.evaluate", expression=expression, returnByValue=True)["result"].get(
            "value"
        )

    def wait_for(expression, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if js(expression):
                return True
            time.sleep(0.5)
        return False

    def enter():
        for kind in ("keyDown", "keyUp"):
            send(
                "Input.dispatchKeyEvent",
                type=kind,
                key="Enter",
                code="Enter",
                windowsVirtualKeyCode=13,
                nativeVirtualKeyCode=13,
                text="\r" if kind == "keyDown" else "",
            )

    def metrics(height):
        send(
            "Emulation.setDeviceMetricsOverride",
            width=1280,
            height=height,
            deviceScaleFactor=SCALE,
            mobile=False,
        )

    metrics(1000)
    send("Page.navigate", url=APP)
    name_box = "document.querySelector('input[aria-label=\"Your name\"]')"
    assert wait_for(f"!!{name_box}", 30), "no name box"
    time.sleep(1.5)
    js(f"{name_box}.focus()")
    send("Input.insertText", text=NAME)
    enter()
    time.sleep(2.5)

    assert wait_for("!!document.querySelector('textarea')", 20), "no chat box"
    js("document.querySelector('textarea').focus()")
    send("Input.insertText", text=QUESTION)
    enter()
    messages = "document.querySelectorAll('[data-testid=\"stChatMessage\"]').length"
    spinner = "document.querySelector('[data-testid=\"stSpinner\"]')"
    confirm = "[...document.querySelectorAll('button')].some(b => b.innerText.includes('Confirm'))"
    assert wait_for(f"{messages} >= 2 && !{spinner} && {confirm}", 150), "no draft"
    # Let the critical-towers pop-up fade, so it does not cover the page.
    time.sleep(6)

    # A page taller than its content never scrolls, so everything is on screen at once;
    # the crop runs from the alert banner to the bottom of the draft.
    metrics(2600)
    time.sleep(3)
    left, top, right, bottom = js(
        """(() => {
          const column = document.querySelector('[data-testid="stMainBlockContainer"]')
            .getBoundingClientRect();
          const banner = document.querySelector('[data-testid="stAlert"]').getBoundingClientRect();
          const drafts = [...document.querySelectorAll('[data-testid="stVerticalBlock"]')]
            .filter(b => b.innerText.startsWith('Work order draft'));
          const draft = drafts[drafts.length - 1].getBoundingClientRect();
          return [column.left, banner.top, column.right, draft.bottom];
        })()"""
    )
    shot = send("Page.captureScreenshot", format="png", captureBeyondViewport=True)
    image = Image.open(io.BytesIO(base64.b64decode(shot["data"])))
    margin = 12
    box = (
        int(left * SCALE),
        int((top - margin / 1.5) * SCALE),
        int(right * SCALE),
        int((bottom + 2 * margin) * SCALE),
    )
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "copilot_screen.png")
    image.crop(box).save(out)
    print("saved", out, image.crop(box).size)
    ws.close()
finally:
    edge.terminate()
