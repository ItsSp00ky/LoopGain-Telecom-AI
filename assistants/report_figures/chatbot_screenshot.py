"""Figure 8 of the final report: the chatbot screen after two real questions.

With the prepaid service and the chatbot running, run (one line):
    uv run --no-project --python 3.12 --with websocket-client
        python chatbot_screenshot.py chatbot_screen.png
Then crop to the conversation panel, as the report's screenshots show the main area only.

Drives a headless Edge through the DevTools protocol: signs in as subscriber 70016, asks a
package question in English and an offer question in Arabic, then captures the page.
"""

import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9555
APP = "http://127.0.0.1:8501"
QUESTIONS = ["What are the 3 cheapest monthly packages?", "في عرض ليا اليوم؟"]

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

    send(
        "Emulation.setDeviceMetricsOverride",
        width=1280,
        height=1000,
        deviceScaleFactor=2,
        mobile=False,
    )
    send("Page.navigate", url=APP)
    assert wait_for("!!document.querySelector('input[aria-label=\"Subscriber ID\"]')", 30), (
        "no sign-in box"
    )
    time.sleep(1.5)
    js("document.querySelector('input[aria-label=\"Subscriber ID\"]').focus()")
    send("Input.insertText", text="70016")
    enter()
    time.sleep(2.5)

    for number, question in enumerate(QUESTIONS, start=1):
        assert wait_for("!!document.querySelector('textarea')", 20), "no chat box"
        js("document.querySelector('textarea').focus()")
        send("Input.insertText", text=question)
        enter()
        expected = 2 * number
        messages = "document.querySelectorAll('[data-testid=\"stChatMessage\"]').length"
        spinner = "document.querySelector('[data-testid=\"stSpinner\"]')"
        done = f"{messages} >= {expected} && !{spinner}"
        assert wait_for(done, 120), f"no answer to question {number}"
        time.sleep(2)

    height = js(
        "Math.ceil(document.querySelector('[data-testid=\"stMain\"]')?.scrollHeight"
        " || document.body.scrollHeight)"
    )
    height = max(1000, min(int(height or 1000) + 40, 2200))
    send(
        "Emulation.setDeviceMetricsOverride",
        width=1280,
        height=height,
        deviceScaleFactor=2,
        mobile=False,
    )
    time.sleep(2)
    shot = send("Page.captureScreenshot", format="png", captureBeyondViewport=True)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "figure8_chatbot.png")
    out.write_bytes(base64.b64decode(shot["data"]))
    print("saved", out, "height", height)
    ws.close()
finally:
    edge.terminate()
