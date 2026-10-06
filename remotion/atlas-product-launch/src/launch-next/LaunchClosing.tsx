import {
  AbsoluteFill,
  Interactive,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, Logo } from "../design";
import { motion } from "./MeetLayout";

export const LaunchClosing = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{
        background: C.paper,
        color: C.ink,
        fontFamily: '"Source Sans 3", sans-serif',
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
      }}
    >
      <Interactive.Div
        name="Atlas closing wordmark"
        style={{
          position: "absolute",
          top: 214,
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
          opacity: interpolate(f, [0, 1.2 * fps], [0, 1], motion),
          translate: interpolate(
            f,
            [0, 1.4 * fps],
            ["0px 20px", "0px 0px"],
            motion,
          ),
        }}
      >
        <Logo size={124} />
      </Interactive.Div>
      <Interactive.Div
        name="Closing purpose"
        style={{
          position: "absolute",
          top: 426,
          left: 96,
          right: 96,
          textAlign: "center",
          opacity: interpolate(f, [1.2 * fps, 2.7 * fps], [0, 1], motion),
          translate: interpolate(
            f,
            [1.2 * fps, 2.7 * fps],
            ["0px 20px", "0px 0px"],
            motion,
          ),
        }}
      >
        <h1
          style={{
            margin: 0,
            fontSize: 91,
            letterSpacing: -2.8,
            lineHeight: 1.1,
            fontWeight: 650,
          }}
        >
          From ticket to
          <br />
          governed change.
        </h1>
      </Interactive.Div>
      <Interactive.Div
        name="Atlas lifecycle closing line"
        style={{
          position: "absolute",
          top: 715,
          left: 96,
          right: 96,
          textAlign: "center",
          fontSize: 40,
          color: C.muted,
          opacity: interpolate(f, [3.2 * fps, 4.6 * fps], [0, 1], motion),
        }}
      >
        Understand. Model. Build. Evolve.
      </Interactive.Div>
      <Interactive.Div
        name="Terracotta closing rule"
        style={{
          position: "absolute",
          top: 811,
          height: 5,
          width: 134,
          borderRadius: 3,
          background: C.accent,
          scale: interpolate(f, [3.5 * fps, 4.8 * fps], [0.2, 1], motion),
          opacity: interpolate(f, [3.5 * fps, 4.8 * fps], [0, 1], motion),
        }}
      />
    </AbsoluteFill>
  );
};
