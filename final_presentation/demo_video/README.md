# How the demo video was made

[`../LoopGain_demo_45s.mp4`](../LoopGain_demo_45s.mp4) is a 45-second, 1920x1080 demo for the final presentation.
A laptop on the left and an Android phone on the right run the same copilot flow at the same moment, on a blue and white background.
Both screens are real recordings of the running platform on 2026-10-03, not mock-ups.

## The five steps

1. One morning briefing: the Overview and the Android dashboard.
2. The copilot flags towers in trouble: 15 critical and 34 major alerts.
3. Ask in plain words: "What is wrong with tower BTWRM1?", answered from the tower data.
4. The AI drafts the work order: nothing is saved yet.
5. A named employee decides: Taha confirms it and it is logged.

## Rebuilding it

- `record_desktop.py` drives Edge with Playwright against the platform shell on port 8510 and saves full-quality screencast frames with the time each step starts.
- `record_phone.py` drives the Android app in an emulator through adb, finding controls by their text, and records the screen with Android's `screenrecord`.
  The app points at a second platform shell on port 8512 whose `PLATFORM_*_PUBLIC_URL` settings use `10.0.2.2`, the emulator's address for the laptop.
- `source/` is the Remotion project that lays the two recordings out side by side.
  `src/timeline.ts` holds the captions and, for each step, which seconds of each recording to show; change it and run `npx remotion render src/index.ts LoopGainDemo out/loopgain_demo.mp4`.
  Put the recordings in `source/public/` (`desktop.mp4`, `part_a.mp4`, `part_b.mp4`, `part_c.mp4`) after `npm install`; they are not committed because of their size.

The copilot uses Groq's free plan, so the recorders wait about a minute between the two questions; the wait is cut out of the video.
