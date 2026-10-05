"""Record the desktop half of the demo: Edge driven by Playwright, captured as full-quality frames.

Frames come from the browser's screencast (sharper than Playwright's built-in video) with their
own timestamps; marks.json records when each storyboard step starts, so the video editor can
line the laptop up with the phone.
"""

import asyncio
import base64
import json
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(__file__).parent / "desktop"
SHELL = "http://127.0.0.1:8510"
TOWER = "BTWRM1"
QUESTION = f"What is wrong with tower {TOWER}?"
DRAFT = f"Draft a site visit work order for {TOWER}"
# Groq's free plan allows about one copilot question a minute.
SECONDS_BETWEEN_QUESTIONS = 70

frames: list[tuple[float, bytes]] = []
marks: list[tuple[str, float]] = []


def mark(label: str) -> None:
    marks.append((label, time.time()))
    print(f"{label} at {time.strftime('%H:%M:%S')}", flush=True)


async def capture(page):
    cdp = await page.context.new_cdp_session(page)

    async def on_frame(params):
        frames.append((params["metadata"]["timestamp"], base64.b64decode(params["data"])))
        try:
            await cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:
            pass

    cdp.on("Page.screencastFrame", lambda params: asyncio.ensure_future(on_frame(params)))
    await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "everyNthFrame": 1})
    return cdp


async def hold(seconds: float):
    await asyncio.sleep(seconds)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900}, device_scale_factor=4 / 3
        )
        page = await context.new_page()
        await page.goto(SHELL, wait_until="networkidle")
        await page.get_by_text("Revenue at risk").first.wait_for(timeout=120_000)
        await page.get_by_text("LYD", exact=False).first.wait_for(timeout=120_000)
        await hold(2)
        await capture(page)
        mark("overview")
        await hold(3)
        await page.mouse.wheel(0, 380)
        await hold(3)

        await page.get_by_role("link", name="AI Assistants").click()
        await page.get_by_role("tab", name="Employee copilot").wait_for(timeout=60_000)
        mark("assistants")
        await hold(1.5)
        await page.get_by_role("tab", name="Employee copilot").click()
        await page.get_by_role("link", name="Open the copilot full screen").wait_for(timeout=60_000)
        await hold(3)

        async with context.expect_page() as popup:
            await page.get_by_role("link", name="Open the copilot full screen").click()
        copilot = await popup.value
        await capture(copilot)
        await copilot.get_by_text("tower alerts on").first.wait_for(timeout=60_000)
        mark("copilot")
        await hold(4)

        name = copilot.get_by_placeholder("for example Taha")
        await name.click()
        await name.press_sequentially("Taha", delay=90)
        await name.press("Enter")
        mark("name")
        await hold(1.5)

        chat = copilot.get_by_placeholder("Ask about towers, sites or customers")
        await chat.click()
        await chat.press_sequentially(QUESTION, delay=45)
        await hold(0.6)
        await chat.press("Enter")
        mark("ask")
        asked = time.time()
        await copilot.get_by_text("What I looked up").first.wait_for(timeout=120_000)
        await hold(0.5)
        mark("answer")
        await copilot.mouse.move(900, 500)
        await copilot.mouse.wheel(0, 2000)
        await hold(6)

        wait = SECONDS_BETWEEN_QUESTIONS - (time.time() - asked)
        if wait > 0:
            print(f"waiting {wait:.0f}s for Groq's per-minute limit", flush=True)
            await hold(wait)
        await chat.click()
        await chat.press_sequentially(DRAFT, delay=45)
        await hold(0.6)
        await chat.press("Enter")
        mark("ask_draft")
        await copilot.get_by_text(f"Work order draft: {TOWER}").first.wait_for(timeout=120_000)
        await hold(0.5)
        await copilot.mouse.wheel(0, 3000)
        mark("draft")
        await hold(4)

        await copilot.get_by_role("button", name="Confirm").click()
        await copilot.get_by_text(f"Work order for {TOWER} saved").first.wait_for(timeout=30_000)
        mark("confirmed")
        await hold(2.5)
        await copilot.mouse.wheel(0, -6000)
        await hold(1)
        await copilot.get_by_text("Work orders (1)").first.click()
        await hold(4)
        mark("end")
        await browser.close()

    frames.sort(key=lambda frame: frame[0])
    index = []
    for number, (stamp, data) in enumerate(frames):
        name = f"f{number:05d}.jpg"
        (OUT / name).write_bytes(data)
        index.append({"file": name, "t": stamp})
    (OUT / "frames.json").write_text(json.dumps(index), encoding="utf-8")
    (OUT / "marks.json").write_text(json.dumps([{"label": l, "t": t} for l, t in marks]), encoding="utf-8")
    print(f"{len(frames)} frames, {frames[-1][0] - frames[0][0]:.1f}s", flush=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
