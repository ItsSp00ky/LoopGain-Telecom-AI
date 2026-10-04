import { Composition } from "remotion";
import { Demo } from "./Demo";
import { FPS, TOTAL_SECONDS } from "./timeline";

export const RemotionRoot = () => (
  <Composition
    id="LoopGainDemo"
    component={Demo}
    durationInFrames={TOTAL_SECONDS * FPS}
    fps={FPS}
    width={1920}
    height={1080}
  />
);
