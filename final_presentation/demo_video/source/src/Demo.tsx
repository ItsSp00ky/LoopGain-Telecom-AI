import { loadFont } from "@remotion/google-fonts/Poppins";
import type { CSSProperties, ReactNode } from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  OffthreadVideo,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { FPS, INTRO_SECONDS, OUTRO_SECONDS, STEPS, stepStarts, TOTAL_SECONDS } from "./timeline";

const { fontFamily } = loadFont("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] });

// Samsung-style palette: one strong blue on white, a deeper blue for depth, soft tints for ground.
const BLUE = "#1428A0";
const BLUE_DEEP = "#0B1766";
const BLUE_SOFT = "#EDF2FF";
const INK = "#0E1A3C";
const MUTED = "#55658A";
const BEZEL = "#15171D";

const LAPTOP = { x: 120, y: 150, width: 1088, height: 680, bezel: 16 };
const PHONE = { x: 1420, y: 150, width: 324, height: 720, bezel: 14 };

// Where to zoom in on the laptop screen so the copilot's text reads on a projector.
const ZOOM: Record<string, { from: number; scale: number; origin: string }> = {
  ask: { from: 0.55, scale: 1.38, origin: "62% 66%" },
  draft: { from: 0.35, scale: 1.38, origin: "62% 58%" },
  confirm: { from: 0.45, scale: 1.38, origin: "62% 45%" },
};

const ease = Easing.bezier(0.22, 1, 0.36, 1);

const fade = (frame: number, start: number, length = 12) =>
  interpolate(frame, [start, start + length], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });

const Background = () => (
  <AbsoluteFill style={{ background: "#FFFFFF" }}>
    <div
      style={{
        position: "absolute",
        right: -320,
        top: -380,
        width: 1100,
        height: 1100,
        borderRadius: "50%",
        background: `radial-gradient(circle at 40% 60%, ${BLUE_SOFT} 0%, rgba(237,242,255,0) 70%)`,
      }}
    />
    <div
      style={{
        position: "absolute",
        left: -260,
        bottom: -420,
        width: 900,
        height: 900,
        borderRadius: "50%",
        background: `radial-gradient(circle at 60% 40%, ${BLUE_SOFT} 0%, rgba(237,242,255,0) 70%)`,
      }}
    />
  </AbsoluteFill>
);

const Screen = ({
  src,
  segments,
  zoom,
  placeholder,
}: {
  src: string | null;
  segments: ([string, number, number] | null)[];
  zoom: boolean;
  placeholder: string;
}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: "#F4F7FB", overflow: "hidden" }}>
      {STEPS.map((step, index) => {
        const segment = segments[index];
        const from = (stepStarts[index] - (index === 0 ? INTRO_SECONDS : 0)) * FPS;
        const length = (step.seconds + (index === 0 ? INTRO_SECONDS : 0)) * FPS;
        if (!src || !segment) {
          return null;
        }
        const play = step.seconds;
        const [file, startAt, endAt] = segment;
        const rate = (endAt - startAt) / play;
        const z = zoom ? ZOOM[step.id] : undefined;
        const local = frame - stepStarts[index] * FPS;
        const scale = z
          ? interpolate(local, [z.from * play * FPS, z.from * play * FPS + 18], [1, z.scale], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: ease,
            })
          : 1;
        // The first step also covers the intro, so its recording starts when the devices appear.
        const trimBefore = Math.round(startAt * FPS);
        return (
          <Sequence key={step.id} from={from} durationInFrames={length} layout="none">
            <AbsoluteFill style={{ transform: `scale(${scale})`, transformOrigin: z?.origin ?? "50% 50%" }}>
              {index === 0 ? (
                <Sequence from={INTRO_SECONDS * FPS} layout="none">
                  <OffthreadVideo src={staticFile(file)} trimBefore={trimBefore} playbackRate={rate} muted style={fill} />
                </Sequence>
              ) : (
                <OffthreadVideo src={staticFile(file)} trimBefore={trimBefore} playbackRate={rate} muted style={fill} />
              )}
            </AbsoluteFill>
          </Sequence>
        );
      })}
      {!src && (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", color: MUTED, fontSize: 22 }}>
          {placeholder}
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

const fill: CSSProperties = { width: "100%", height: "100%", objectFit: "cover" };

const Chip = ({ children, x, y }: { children: ReactNode; x: number; y: number }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "7px 16px",
      borderRadius: 999,
      background: BLUE_SOFT,
      color: BLUE,
      fontSize: 19,
      fontWeight: 600,
      letterSpacing: 0.3,
    }}
  >
    <span style={{ width: 9, height: 9, borderRadius: 9, background: BLUE }} />
    {children}
  </div>
);

const Laptop = ({ children }: { children: ReactNode }) => {
  const { x, y, width, height, bezel } = LAPTOP;
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: x - bezel,
          top: y - bezel,
          width: width + bezel * 2,
          height: height + bezel * 2,
          borderRadius: 22,
          background: BEZEL,
          boxShadow: "0 30px 60px rgba(11,23,102,0.18)",
        }}
      />
      <div style={{ position: "absolute", left: x, top: y, width, height, borderRadius: 6, overflow: "hidden" }}>{children}</div>
      <div
        style={{
          position: "absolute",
          left: x - 90,
          top: y + height + bezel,
          width: width + 180,
          height: 22,
          borderRadius: "0 0 18px 18px",
          background: "linear-gradient(#E3E8F1, #C9D0DD)",
          boxShadow: "0 14px 24px rgba(11,23,102,0.12)",
        }}
      >
        <div style={{ margin: "0 auto", width: 170, height: 8, borderRadius: "0 0 8px 8px", background: "#B5BDCC" }} />
      </div>
    </>
  );
};

const Phone = ({ children }: { children: ReactNode }) => {
  const { x, y, width, height, bezel } = PHONE;
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: x - bezel,
          top: y - bezel,
          width: width + bezel * 2,
          height: height + bezel * 2,
          borderRadius: 54,
          background: BEZEL,
          boxShadow: "0 30px 60px rgba(11,23,102,0.2)",
        }}
      />
      <div style={{ position: "absolute", left: x, top: y, width, height, borderRadius: 42, overflow: "hidden" }}>{children}</div>
      <div
        style={{ position: "absolute", left: x + width / 2 - 7, top: y + 12, width: 14, height: 14, borderRadius: 14, background: BEZEL }}
      />
    </>
  );
};

const Header = () => (
  <>
    <div style={{ position: "absolute", left: 104, top: 40, display: "flex", alignItems: "center", gap: 14 }}>
      <div style={{ width: 18, height: 18, borderRadius: 5, background: BLUE }} />
      <span style={{ fontSize: 30, fontWeight: 700, color: BLUE, letterSpacing: -0.3 }}>LoopGain Telecom AI</span>
    </div>
    <div style={{ position: "absolute", right: 104, top: 46, fontSize: 20, color: MUTED, fontWeight: 500 }}>
      Team Loop Gain · SIC AI Capstone
    </div>
  </>
);

const Caption = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const index = STEPS.findIndex((_, i) => frame < (stepStarts[i] + STEPS[i].seconds) * FPS);
  const current = Math.max(0, index === -1 ? STEPS.length - 1 : index);
  const step = STEPS[current];
  const local = frame - stepStarts[current] * FPS;
  const enter = spring({ frame: local, fps, config: { damping: 200 }, durationInFrames: 14 });
  return (
    <div
      style={{
        position: "absolute",
        left: 260,
        right: 260,
        top: 924,
        height: 116,
        borderRadius: 22,
        background: "#FFFFFF",
        boxShadow: "0 18px 40px rgba(11,23,102,0.14)",
        border: `1px solid ${BLUE_SOFT}`,
        display: "flex",
        alignItems: "center",
        gap: 28,
        padding: "0 36px",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          flex: "none",
          width: 64,
          height: 64,
          borderRadius: 18,
          background: BLUE,
          color: "#FFFFFF",
          fontSize: 30,
          fontWeight: 700,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {current + 1}
      </div>
      <div style={{ opacity: enter, transform: `translateY(${(1 - enter) * 14}px)`, minWidth: 0 }}>
        <div style={{ fontSize: 34, fontWeight: 700, color: INK, letterSpacing: -0.4 }}>{step.caption}</div>
        <div style={{ fontSize: 22, color: MUTED, marginTop: 2 }}>{step.detail}</div>
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 6, display: "flex", gap: 4 }}>
        {STEPS.map((s, i) => {
          const progress =
            i < current ? 1 : i > current ? 0 : Math.min(1, Math.max(0, local / (s.seconds * FPS)));
          return (
            <div key={s.id} style={{ flex: 1, background: BLUE_SOFT }}>
              <div style={{ width: `${progress * 100}%`, height: "100%", background: BLUE }} />
            </div>
          );
        })}
      </div>
    </div>
  );
};

const Intro = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rise = (delay: number) => spring({ frame: frame - delay, fps, config: { damping: 200 }, durationInFrames: 22 });
  const out = interpolate(frame, [INTRO_SECONDS * FPS - 16, INTRO_SECONDS * FPS], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", opacity: out, background: "#FFFFFF" }}>
      <Background />
      <div style={{ textAlign: "center", position: "relative" }}>
        <div style={{ opacity: rise(0), fontSize: 22, fontWeight: 600, letterSpacing: 4, color: BLUE }}>
          SAMSUNG INNOVATION CAMPUS · AI CAPSTONE
        </div>
        <div
          style={{
            opacity: rise(6),
            transform: `translateY(${(1 - rise(6)) * 30}px)`,
            fontSize: 112,
            fontWeight: 700,
            color: BLUE,
            letterSpacing: -2.5,
            marginTop: 18,
          }}
        >
          LoopGain Telecom AI
        </div>
        <div style={{ opacity: rise(14), fontSize: 36, color: INK, marginTop: 10, fontWeight: 500 }}>
          One platform for the network, planning and customers
        </div>
        <div
          style={{
            opacity: rise(24),
            display: "inline-flex",
            marginTop: 34,
            padding: "14px 30px",
            borderRadius: 999,
            background: BLUE,
            color: "#FFFFFF",
            fontSize: 26,
            fontWeight: 600,
          }}
        >
          Desktop and Android · featuring the employee copilot
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Outro = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 20 });
  const pillars = [
    ["Grounded", "Every figure comes from the platform's own data"],
    ["Human in the loop", "The AI drafts, a named person decides"],
    ["One platform", "The same workflow on desktop and Android"],
  ];
  return (
    <AbsoluteFill style={{ opacity: enter, background: "rgba(255,255,255,0.94)", alignItems: "center", justifyContent: "center" }}>
      <div style={{ fontSize: 84, fontWeight: 700, color: BLUE, letterSpacing: -2 }}>LoopGain Telecom AI</div>
      <div style={{ display: "flex", gap: 28, marginTop: 44 }}>
        {pillars.map(([title, text], i) => {
          const pop = spring({ frame: frame - 6 - i * 5, fps, config: { damping: 200 }, durationInFrames: 18 });
          return (
            <div
              key={title}
              style={{
                width: 430,
                padding: "30px 32px",
                borderRadius: 24,
                background: i === 1 ? BLUE : BLUE_SOFT,
                color: i === 1 ? "#FFFFFF" : INK,
                opacity: pop,
                transform: `translateY(${(1 - pop) * 24}px)`,
              }}
            >
              <div style={{ fontSize: 32, fontWeight: 700, color: i === 1 ? "#FFFFFF" : BLUE }}>{title}</div>
              <div style={{ fontSize: 23, marginTop: 8, lineHeight: 1.4, color: i === 1 ? "#DCE4FF" : MUTED }}>{text}</div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 46, fontSize: 24, color: MUTED, fontWeight: 500 }}>Team Loop Gain · SIC AI Capstone</div>
    </AbsoluteFill>
  );
};

export const Demo = ({ phoneSrc = "phone" as string | null }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const appear = spring({ frame: frame - (INTRO_SECONDS * FPS - 10), fps, config: { damping: 200 }, durationInFrames: 24 });
  return (
    <AbsoluteFill style={{ fontFamily, color: INK }}>
      <Background />
      <AbsoluteFill style={{ opacity: appear, transform: `translateY(${(1 - appear) * 40}px)` }}>
        <Header />
        <Chip x={LAPTOP.x - LAPTOP.bezel} y={96}>Web platform · desktop</Chip>
        <Chip x={PHONE.x - PHONE.bezel} y={96}>Android app</Chip>
        <Laptop>
          <Screen src="desktop.mp4" segments={STEPS.map((s) => ["desktop.mp4", ...s.desktop] as [string, number, number])} zoom placeholder="" />
        </Laptop>
        <Phone>
          <Screen src={phoneSrc} segments={STEPS.map((s) => s.phone)} zoom={false} placeholder="Android recording" />
        </Phone>
        <Sequence from={INTRO_SECONDS * FPS} durationInFrames={(TOTAL_SECONDS - INTRO_SECONDS - OUTRO_SECONDS) * FPS} layout="none">
          <CaptionAtComposition />
        </Sequence>
      </AbsoluteFill>
      <Sequence durationInFrames={INTRO_SECONDS * FPS}>
        <Intro />
      </Sequence>
      <Sequence from={(TOTAL_SECONDS - OUTRO_SECONDS) * FPS}>
        <Outro />
      </Sequence>
    </AbsoluteFill>
  );
};

// The caption reads the composition frame, not the Sequence-local one, so it lines up with stepStarts.
const CaptionAtComposition = () => {
  return (
    <Sequence from={-INTRO_SECONDS * FPS} layout="none">
      <Caption />
    </Sequence>
  );
};
