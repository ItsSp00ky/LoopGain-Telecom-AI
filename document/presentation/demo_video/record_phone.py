"""Record the Android half of the demo: the LoopGain app in the emulator, driven through adb.

Controls are found by their text in the accessibility dump (the web pages inside the app are
included), so no tap depends on guessed coordinates. Recorded in two parts with Android's own
screenrecord, around the minute Groq's free plan needs between two copilot questions.
"""

import html
import json
import re
import subprocess
import time
from pathlib import Path

ADB = r"D:\dev-tools\android-sdk\platform-tools\adb.exe"
OUT = Path(__file__).parent / "phone"
APP = "com.loopgain.kpimonitor"
TOWER = "BTWRM1"
QUESTION = f"What is wrong with tower {TOWER}?"
DRAFT = f"Draft a site visit work order for {TOWER}"
SECONDS_BETWEEN_QUESTIONS = 70

marks: list[dict] = []


def adb(*args: str) -> str:
    return subprocess.run([ADB, *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def nodes() -> list[tuple[str, list[int]]]:
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    xml = adb("exec-out", "cat", "/sdcard/ui.xml")
    found = []
    for match in re.finditer(r"<node [^>]*>", xml):
        node = match.group(0)
        text_match, desc_match = re.search(r' text="([^"]*)"', node), re.search(r'content-desc="([^"]*)"', node)
        bounds = re.search(r'bounds="([^"]*)"', node)
        if not bounds:
            continue
        text = (text_match.group(1) if text_match else "") or (desc_match.group(1) if desc_match else "")
        box = [int(n) for n in re.findall(r"\d+", bounds.group(1))]
        if text and box[2] > box[0] and box[3] > box[1]:
            found.append((html.unescape(text), box))
    return found


def find(text: str, exact: bool = False):
    for label, box in nodes():
        if (label == text) if exact else (text in label):
            return box
    return None


def wait_for(text: str, timeout: float = 60, exact: bool = False) -> list[int]:
    end = time.time() + timeout
    while time.time() < end:
        box = find(text, exact)
        if box:
            return box
        time.sleep(0.8)
    raise TimeoutError(f"'{text}' did not appear")


def tap(box: list[int]) -> None:
    adb("shell", "input", "tap", str((box[0] + box[2]) // 2), str((box[1] + box[3]) // 2))


def tap_text(text: str, timeout: float = 60, exact: bool = False) -> None:
    tap(wait_for(text, timeout, exact))


def swipe_up(pixels: int = 700) -> None:
    adb("shell", "input", "swipe", "540", "1700", "540", str(1700 - pixels), "450")


def swipe_down(pixels: int = 700) -> None:
    adb("shell", "input", "swipe", "540", "900", "540", str(900 + pixels), "450")


def type_words(sentence: str) -> None:
    words = sentence.split(" ")
    for number, word in enumerate(words):
        adb("shell", "input", "text", word)
        if number < len(words) - 1:
            adb("shell", "input", "keyevent", "62")


def keyboard_shown() -> bool:
    return bool(re.search(r"mInputShown=true|mIsInputViewShown=true", adb("shell", "dumpsys", "input_method")))


def hide_keyboard() -> None:
    if keyboard_shown():
        adb("shell", "input", "keyevent", "4")
        time.sleep(0.6)


class Recording:
    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        adb("shell", "rm", "-f", f"/sdcard/{self.name}.mp4")
        self.process = subprocess.Popen([ADB, "shell", "screenrecord", "--bit-rate", "16000000", f"/sdcard/{self.name}.mp4"])
        time.sleep(1.0)
        self.start = time.time()
        return self

    def mark(self, label: str) -> None:
        marks.append({"part": self.name, "label": label, "s": round(time.time() - self.start, 3)})
        print(f"{self.name}: {label} at {marks[-1]['s']}s", flush=True)

    def __exit__(self, *exc):
        time.sleep(0.5)
        adb("shell", "pkill", "-INT", "screenrecord")
        self.process.wait(timeout=30)
        time.sleep(1.5)
        adb("pull", f"/sdcard/{self.name}.mp4", str(OUT / f"{self.name}.mp4"))
        return False


def send(sentence: str) -> None:
    wait_for(sentence, 10)
    adb("shell", "input", "tap", "938", "2116")  # the send arrow under the chat box


def part_b():
    with Recording("part_b") as rec:
        rec.mark("start")
        time.sleep(1)
        adb("shell", "input", "tap", "540", "1990")  # the chat box text area, pinned at the bottom
        time.sleep(0.8)
        adb("shell", "input", "keyevent", "123")
        for _ in range(60):
            adb("shell", "input", "keyevent", "67")
        rec.mark("typing")
        type_words(DRAFT)
        time.sleep(0.6)
        hide_keyboard()
        time.sleep(0.6)
        send(DRAFT)
        rec.mark("ask_draft")
        time.sleep(1)
        hide_keyboard()
        wait_for("Work order draft", 120)
        for _ in range(4):
            swipe_up(800)
            time.sleep(0.8)
        rec.mark("draft")
        time.sleep(3)
        tap_text("Confirm", 20, exact=True)
        wait_for("saved", 30)
        rec.mark("confirmed")
        time.sleep(2.5)
        for _ in range(8):
            swipe_down(1100)
            time.sleep(0.4)
        tap_text("Work orders (1)", 20)
        time.sleep(4)
        rec.mark("end")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    adb("shell", "am", "force-stop", APP)
    adb("shell", "monkey", "-p", APP, "-c", "android.intent.category.LAUNCHER", "1")
    wait_for("At a glance", 60)
    wait_for("LYD", 60)
    time.sleep(2)

    with Recording("part_a") as rec:
        rec.mark("overview")
        time.sleep(3)
        swipe_up(520)
        time.sleep(2.5)
        swipe_down(900)
        time.sleep(1)

        tap_text("Ask AI")
        rec.mark("assistants")
        tap_text("Employee copilot", 60)
        tap_text("Open the copilot full screen", 60)
        wait_for("tower alerts on", 60)
        rec.mark("copilot")
        time.sleep(3.5)

        tap_text("keyboard_double_arrow_right", 20)
        time.sleep(1.5)
        # The accessibility dump does not expose this input; it sits at a fixed place in the sidebar.
        adb("shell", "input", "tap", "394", "1014")
        time.sleep(0.8)
        type_words("Taha")
        adb("shell", "input", "keyevent", "66")
        time.sleep(0.8)
        hide_keyboard()
        tap_text("keyboard_double_arrow_left", 20)
        rec.mark("name")
        time.sleep(1.2)

        adb("shell", "input", "tap", "540", "2114")  # the chat box, pinned at the bottom
        time.sleep(0.8)
        type_words(QUESTION)
        time.sleep(0.5)
        adb("shell", "input", "keyevent", "66")
        rec.mark("ask")
        asked = time.time()
        time.sleep(1)
        hide_keyboard()
        wait_for("What I looked up", 120)
        time.sleep(0.5)
        rec.mark("answer")
        swipe_up(900)
        time.sleep(1.5)
        swipe_up(900)
        time.sleep(5)

    wait = SECONDS_BETWEEN_QUESTIONS - (time.time() - asked)
    if wait > 0:
        print(f"waiting {wait:.0f}s for Groq's per-minute limit", flush=True)
        time.sleep(wait)

    with Recording("part_b") as rec:
        rec.mark("start")
        time.sleep(1)
        adb("shell", "input", "tap", "540", "2114")  # the chat box, pinned at the bottom
        time.sleep(0.8)
        type_words(DRAFT)
        time.sleep(0.5)
        adb("shell", "input", "keyevent", "66")
        rec.mark("ask_draft")
        time.sleep(1)
        hide_keyboard()
        wait_for(f"Work order draft: {TOWER}", 120)
        for _ in range(4):
            swipe_up(800)
            time.sleep(0.8)
        rec.mark("draft")
        time.sleep(3)
        tap_text("Confirm", 20, exact=True)
        wait_for(f"Work order for {TOWER} saved", 30)
        rec.mark("confirmed")
        time.sleep(2.5)
        for _ in range(8):
            swipe_down(1100)
            time.sleep(0.4)
        tap_text("Work orders (1)", 20)
        time.sleep(4)
        rec.mark("end")

    (OUT / "marks.json").write_text(json.dumps(marks, indent=1), encoding="utf-8")
    print("done", flush=True)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["part_b"]:
        previous = json.loads((OUT / "marks.json").read_text(encoding="utf-8")) if (OUT / "marks.json").exists() else []
        marks.extend(m for m in previous if m["part"] == "part_a")
        part_b()
        (OUT / "marks.json").write_text(json.dumps(marks, indent=1), encoding="utf-8")
    else:
        main()
