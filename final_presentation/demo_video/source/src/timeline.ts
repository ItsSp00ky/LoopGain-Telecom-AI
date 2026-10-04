// The demo's 45 seconds at 30 fps. Each step shows the same moment on both devices:
// `desktop` and `phone` are [start, end] in seconds of each recording, played inside the
// step's slot (sped up or slowed down to fit), so the two screens stay in step.

export const FPS = 30;
export const INTRO_SECONDS = 4;
export const OUTRO_SECONDS = 4;
export const TOTAL_SECONDS = 45;

export type Step = {
  id: string;
  seconds: number;
  caption: string;
  detail: string;
  desktop: [number, number];
  phone: [string, number, number] | null;
};

export const STEPS: Step[] = [
  {
    id: "overview",
    seconds: 7,
    caption: "One morning briefing",
    detail: "Network health, congestion, new sites and customers at risk, live from every module",
    desktop: [0.4, 5.9],
    phone: ["part_a.mp4", 0.3, 8.0],
  },
  {
    id: "alerts",
    seconds: 7,
    caption: "The copilot flags towers in trouble",
    detail: "15 critical and 34 major tower alerts, found by rules before anyone asks",
    desktop: [6.1, 15.4],
    phone: ["part_a.mp4", 21.0, 40.0],
  },
  {
    id: "ask",
    seconds: 9,
    caption: "Ask in plain words",
    detail: "Every figure in the answer comes from the tower data, with what it looked up",
    desktop: [15.5, 31.0],
    phone: ["part_a.mp4", 41.0, 63.5],
  },
  {
    id: "draft",
    seconds: 7,
    caption: "The AI drafts the work order",
    detail: "Nothing is saved or sent until a person confirms",
    desktop: [89.8, 99.9],
    phone: ["part_b.mp4", 7.0, 24.0],
  },
  {
    id: "confirm",
    seconds: 7,
    caption: "A named employee decides",
    detail: "Confirmed by Taha and logged: the copilot never acts alone",
    desktop: [99.9, 107.8],
    phone: ["part_c.mp4", 1.5, 27.5],
  },
];

export const stepStarts = (() => {
  let at = INTRO_SECONDS;
  return STEPS.map((step) => {
    const start = at;
    at += step.seconds;
    return start;
  });
})();
