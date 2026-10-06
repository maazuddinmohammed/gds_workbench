import { type ReactNode, useId } from "react";
import {
  AbsoluteFill,
  Easing,
  Interactive,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, Logo } from "../design";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/600.css";
import "@fontsource/source-sans-3/700.css";

export const motion = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
  easing: Easing.bezier(0.22, 0.8, 0.2, 1),
} as const;

/** Stable reading position on the left; only the current idea appears on the right. */
export function SplitStage({
  copy,
  children,
  dark = false,
}: {
  copy: ReactNode;
  children: ReactNode;
  dark?: boolean;
}) {
  return (
    <AbsoluteFill
      style={{
        background: dark ? C.dark : C.paper,
        color: dark ? C.paper : C.ink,
        fontFamily: '"Source Sans 3", sans-serif',
        overflow: "hidden",
      }}
    >
      <div style={{ position: "absolute", left: 96, top: 62 }}>
        <Logo size={48} light={dark} />
      </div>
      <div
        style={{
          position: "absolute",
          right: 100,
          top: 76,
          color: dark ? C.mint : C.muted,
          fontSize: 22,
          letterSpacing: 2.5,
        }}
      >
        01 / MEET ATLAS
      </div>
      <div
        style={{
          position: "absolute",
          left: 735,
          top: 190,
          bottom: 140,
          width: 1,
          background: dark ? "#4E6A61" : C.line,
        }}
      />
      {copy}
      <Interactive.Div
        name="Focused visual"
        style={{
          position: "absolute",
          left: 790,
          top: 190,
          width: 1050,
          height: 710,
        }}
      >
        {children}
      </Interactive.Div>
    </AbsoluteFill>
  );
}

export function StoryCopy({
  name,
  label,
  title,
  children,
  at,
  until,
  dark = false,
}: {
  name: string;
  label: string;
  title: string;
  children: ReactNode;
  at: number;
  until: number;
  dark?: boolean;
}) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <Interactive.Div
      name={name}
      style={{
        position: "absolute",
        left: 96,
        top: 300,
        width: 570,
        opacity: interpolate(
          f,
          [at * fps, (at + 1) * fps, (until - 0.45) * fps, until * fps],
          [0, 1, 1, 0],
          motion,
        ),
        translate: interpolate(
          f,
          [at * fps, (at + 1.2) * fps],
          ["0px 15px", "0px 0px"],
          motion,
        ),
      }}
    >
      <div
        style={{
          fontSize: 22,
          letterSpacing: 2.4,
          color: dark ? "#D9BB91" : C.accent,
        }}
      >
        {label}
      </div>
      <h1
        style={{
          fontWeight: 600,
          fontSize: 78,
          letterSpacing: -2,
          whiteSpace: "pre-line",
          lineHeight: 1.09,
          margin: "28px 0 34px",
        }}
      >
        {title}
      </h1>
      <div
        style={{
          fontSize: 34,
          lineHeight: 1.5,
          color: dark ? C.mint : C.muted,
        }}
      >
        {children}
      </div>
    </Interactive.Div>
  );
}

export function Arrow({
  d,
  at,
  until,
  dashed = false,
  color = C.accent,
}: {
  d: string;
  at: number;
  until: number;
  dashed?: boolean;
  color?: string;
}) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const id = useId();
  return (
    <svg
      width="1050"
      height="710"
      style={{
        position: "absolute",
        inset: 0,
        overflow: "visible",
        opacity: interpolate(
          f,
          [at * fps, (at + 0.6) * fps, (until - 0.3) * fps, until * fps],
          [0, 1, 1, 0],
          motion,
        ),
      }}
    >
      <defs>
        <marker
          id={id}
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto"
        >
          <path
            d="M1 1L8 5L1 9"
            fill="none"
            stroke={color}
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </marker>
      </defs>
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeDasharray={dashed ? "8 8" : undefined}
        markerEnd={`url(#${id})`}
      />
    </svg>
  );
}

export function SourceGlyph({ size = 120 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size * 0.8}
      viewBox="0 0 120 96"
      fill="none"
      aria-label="Source database"
    >
      <path
        d="M18 20V74C18 96 102 96 102 74V20"
        fill="#D8E5DB"
        stroke="#527E66"
        strokeWidth="2"
      />
      <ellipse
        cx="60"
        cy="20"
        rx="42"
        ry="15"
        fill="#EAF0E6"
        stroke="#527E66"
        strokeWidth="2"
      />
      <path
        d="M18 46C18 68 102 68 102 46M18 66C18 88 102 88 102 66"
        stroke="#527E66"
        strokeWidth="2"
      />
    </svg>
  );
}
