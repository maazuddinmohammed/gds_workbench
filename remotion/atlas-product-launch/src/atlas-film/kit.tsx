import { type CSSProperties, type ReactNode } from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/600.css";
import "@fontsource/source-sans-3/700.css";
import "@fontsource/source-sans-3/800.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/ibm-plex-mono/400.css";

/** Dark cinematic palette derived from the Atlas brand (ink green + copper). */
export const T = {
  bg0: "#050F0C",
  bg1: "#0A1B17",
  bg2: "#0F2620",
  panel: "rgba(236,246,240,0.045)",
  panelHi: "rgba(236,246,240,0.085)",
  border: "rgba(222,236,228,0.13)",
  borderHi: "rgba(222,236,228,0.30)",
  text: "#F4F0E7",
  sub: "#AFC1B8",
  dim: "#6F857B",
  copper: "#EE8C5C",
  copperDeep: "#BC603E",
  mint: "#7FDDB0",
  green: "#3E9B73",
  gold: "#EEC56E",
  azure: "#45A6FF",
  lava: "#FF5A36",
  violet: "#AE9BFF",
  red: "#FF6E6E",
  bronze: "#D99566",
  silver: "#C6D3D8",
};

export const FONT = {
  head: '"Source Sans 3", sans-serif',
  body: "Inter, sans-serif",
  mono: '"IBM Plex Mono", monospace',
};

export const EASE = Easing.bezier(0.16, 1, 0.3, 1);
export const clampOpts = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;

/** 0→1 between two frames with a smooth ease-out. */
export function ramp(
  f: number,
  start: number,
  end: number,
  easing: (t: number) => number = EASE,
) {
  return interpolate(f, [start, end], [0, 1], { ...clampOpts, easing });
}

export function useSpring(delay: number, damping = 200, durationInFrames?: number) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({
    frame: f - delay,
    fps,
    config: { damping },
    durationInFrames,
  });
}

/** Deterministic pseudo-random in [0,1). */
export function rand(seed: number) {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
}

/** Fades a scene's content in and out at its edges. */
export function Scene({
  children,
  duration,
  fadeIn = 14,
  fadeOut = 14,
  style,
}: {
  children: ReactNode;
  duration: number;
  fadeIn?: number;
  fadeOut?: number;
  style?: CSSProperties;
}) {
  const f = useCurrentFrame();
  const opacity = Math.min(
    ramp(f, 0, fadeIn),
    1 - ramp(f, duration - fadeOut, duration, Easing.in(Easing.quad)),
  );
  const scale = interpolate(f, [0, duration], [1.012, 1], clampOpts);
  return (
    <AbsoluteFill
      style={{
        opacity,
        transform: `scale(${scale})`,
        fontFamily: FONT.body,
        color: T.text,
        ...style,
      }}
    >
      {children}
    </AbsoluteFill>
  );
}

/** Persistent animated backdrop: deep gradient, faint grid and drifting glows. */
export function Backdrop({ hue = T.copper }: { hue?: string }) {
  const f = useCurrentFrame();
  const a = f / 30;
  return (
    <AbsoluteFill style={{ background: T.bg0, overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(120% 90% at 50% 40%, ${T.bg2} 0%, ${T.bg1} 45%, ${T.bg0} 100%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1100,
          height: 1100,
          borderRadius: "50%",
          left: 1100 + Math.sin(a * 0.11) * 160,
          top: -420 + Math.cos(a * 0.09) * 120,
          background: `radial-gradient(circle, ${hue}22 0%, transparent 62%)`,
          filter: "blur(10px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1200,
          height: 1200,
          borderRadius: "50%",
          left: -520 + Math.cos(a * 0.08) * 140,
          top: 380 + Math.sin(a * 0.1) * 100,
          background: `radial-gradient(circle, ${T.mint}14 0%, transparent 60%)`,
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.5,
          backgroundImage:
            "linear-gradient(rgba(200,230,215,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(200,230,215,0.035) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          backgroundPosition: `${(a * 6) % 64}px ${(a * 3) % 64}px`,
          maskImage:
            "radial-gradient(ellipse 75% 65% at 50% 50%, black 30%, transparent 100%)",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse 90% 80% at 50% 50%, transparent 55%, rgba(0,0,0,0.55) 100%)",
        }}
      />
    </AbsoluteFill>
  );
}

export function AtlasMark({
  size = 64,
  color = T.text,
  accent = T.copper,
  draw = 1,
}: {
  size?: number;
  color?: string;
  accent?: string;
  draw?: number;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40">
      <path
        d="M4 34 17 5h6l13 29h-7L20 13l-9 21Z"
        fill={color}
        opacity={draw}
      />
      <path
        d="m14 25 12 0 3 6H11Z"
        fill={accent}
        opacity={interpolate(draw, [0.5, 1], [0, 1], clampOpts)}
      />
    </svg>
  );
}

export function Wordmark({ size = 48, opacity = 1 }: { size?: number; opacity?: number }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: size * 0.3,
        opacity,
      }}
    >
      <AtlasMark size={size} />
      <span
        style={{
          fontFamily: FONT.head,
          fontWeight: 700,
          fontSize: size * 0.7,
          letterSpacing: size * 0.16,
          color: T.text,
        }}
      >
        ATLAS
      </span>
    </div>
  );
}

/** Kicker + headline + subline with staggered word reveal. */
export function Title({
  kicker,
  title,
  sub,
  at = 0,
  x = 120,
  y = 96,
  width = 1680,
  size = 76,
  align = "left",
  kickerColor = T.copper,
}: {
  kicker?: string;
  title: string;
  sub?: string;
  at?: number;
  x?: number;
  y?: number;
  width?: number;
  size?: number;
  align?: "left" | "center";
  kickerColor?: string;
}) {
  const f = useCurrentFrame();
  const words = title.split(" ");
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width,
        textAlign: align,
      }}
    >
      {kicker ? (
        <div
          style={{
            fontFamily: FONT.body,
            fontWeight: 600,
            fontSize: 22,
            letterSpacing: 5,
            textTransform: "uppercase",
            color: kickerColor,
            marginBottom: 16,
            opacity: ramp(f, at, at + 14),
            transform: `translateY(${(1 - ramp(f, at, at + 18)) * 12}px)`,
          }}
        >
          {kicker}
        </div>
      ) : null}
      <div
        style={{
          fontFamily: FONT.head,
          fontWeight: 700,
          fontSize: size,
          lineHeight: 1.04,
          letterSpacing: -1.5,
          color: T.text,
        }}
      >
        {words.map((w, i) => {
          const s = at + 4 + i * 3;
          const p = ramp(f, s, s + 18);
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                marginRight: size * 0.24,
                opacity: p,
                transform: `translateY(${(1 - p) * 26}px)`,
                filter: `blur(${(1 - p) * 8}px)`,
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
      {sub ? (
        <div
          style={{
            fontFamily: FONT.body,
            fontSize: 28,
            lineHeight: 1.45,
            color: T.sub,
            marginTop: 18,
            maxWidth: align === "center" ? undefined : 1560,
            marginLeft: align === "center" ? "auto" : undefined,
            marginRight: align === "center" ? "auto" : undefined,
            opacity: ramp(f, at + 14 + words.length * 3, at + 34 + words.length * 3),
          }}
        >
          {sub}
        </div>
      ) : null}
    </div>
  );
}

/** Glass card that springs into place. */
export function Glass({
  children,
  at = 0,
  x,
  y,
  w,
  h,
  glow,
  style,
  from = "up",
  pad = 24,
  radius = 20,
}: {
  children?: ReactNode;
  at?: number;
  x: number;
  y: number;
  w: number;
  h?: number;
  glow?: string;
  style?: CSSProperties;
  from?: "up" | "left" | "right" | "scale";
  pad?: number;
  radius?: number;
}) {
  const p = useSpring(at, 18);
  const o = useSpring(at, 200);
  const off = (1 - p) * 40;
  const transform =
    from === "left"
      ? `translateX(${-off}px)`
      : from === "right"
        ? `translateX(${off}px)`
        : from === "scale"
          ? `scale(${0.85 + 0.15 * p})`
          : `translateY(${off}px)`;
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: w,
        height: h,
        padding: pad,
        boxSizing: "border-box",
        borderRadius: radius,
        background: `linear-gradient(160deg, ${T.panelHi}, ${T.panel})`,
        border: `1.5px solid ${glow ? glow + "88" : T.border}`,
        boxShadow: glow
          ? `0 0 0 1px ${glow}22, 0 20px 60px rgba(0,0,0,0.45), 0 0 50px ${glow}30`
          : "0 20px 60px rgba(0,0,0,0.45)",
        opacity: o,
        transform,
        backdropFilter: "blur(6px)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function Pill({
  children,
  color = T.mint,
  solid = false,
  size = 18,
  style,
}: {
  children: ReactNode;
  color?: string;
  solid?: boolean;
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: `${size * 0.28}px ${size * 0.7}px`,
        borderRadius: 999,
        fontFamily: FONT.body,
        fontWeight: 600,
        fontSize: size,
        letterSpacing: 0.3,
        whiteSpace: "nowrap",
        color: solid ? T.bg0 : color,
        background: solid ? color : `${color}1C`,
        border: `1px solid ${color}66`,
        ...style,
      }}
    >
      {children}
    </span>
  );
}

/** Typewriter text; characters per frame. */
export function Type({
  text,
  at,
  cpf = 1.2,
  caret = true,
  style,
}: {
  text: string;
  at: number;
  cpf?: number;
  caret?: boolean;
  style?: CSSProperties;
}) {
  const f = useCurrentFrame();
  const n = Math.max(0, Math.min(text.length, Math.floor((f - at) * cpf)));
  const typing = n > 0 && n < text.length;
  const blink = Math.floor(f / 15) % 2 === 0;
  return (
    <span style={{ whiteSpace: "pre-wrap", ...style }}>
      {text.slice(0, n)}
      {caret && (typing || (n === text.length && blink && f - at < text.length / cpf + 40)) ? (
        <span style={{ color: T.copper }}>▍</span>
      ) : null}
    </span>
  );
}

export function Counter({
  from,
  to,
  at,
  dur = 30,
  decimals = 0,
  suffix = "",
}: {
  from: number;
  to: number;
  at: number;
  dur?: number;
  decimals?: number;
  suffix?: string;
}) {
  const f = useCurrentFrame();
  const v = from + (to - from) * ramp(f, at, at + dur);
  return (
    <>
      {v.toFixed(decimals)}
      {suffix}
    </>
  );
}

type Pt = { x: number; y: number };

/** Cubic curve between two points with horizontal (or vertical) tangents. */
export function curve(a: Pt, b: Pt, vertical = false, bend = 0.5) {
  const c1 = vertical
    ? { x: a.x, y: a.y + (b.y - a.y) * bend }
    : { x: a.x + (b.x - a.x) * bend, y: a.y };
  const c2 = vertical
    ? { x: b.x, y: b.y - (b.y - a.y) * bend }
    : { x: b.x - (b.x - a.x) * bend, y: b.y };
  const at = (t: number): Pt => {
    const u = 1 - t;
    return {
      x: u * u * u * a.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t * t * t * b.x,
      y: u * u * u * a.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t * t * t * b.y,
    };
  };
  const d = `M${a.x},${a.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${b.x},${b.y}`;
  let len = 0;
  let prev = a;
  for (let i = 1; i <= 24; i++) {
    const p = at(i / 24);
    len += Math.hypot(p.x - prev.x, p.y - prev.y);
    prev = p;
  }
  return { d, at, len };
}

/** An animated connector: draws in, then optionally carries glowing packets. */
export function Flow({
  a,
  b,
  at,
  dur = 24,
  color = T.mint,
  packets = 0,
  packetStart,
  speed = 50,
  vertical = false,
  dashed = false,
  width = 2.5,
  bend = 0.5,
  opacity = 1,
  label,
  labelT = 0.5,
}: {
  a: Pt;
  b: Pt;
  at: number;
  dur?: number;
  color?: string;
  packets?: number;
  packetStart?: number;
  speed?: number;
  vertical?: boolean;
  dashed?: boolean;
  width?: number;
  bend?: number;
  opacity?: number;
  label?: string;
  labelT?: number;
}) {
  const f = useCurrentFrame();
  const c = curve(a, b, vertical, bend);
  const p = ramp(f, at, at + dur);
  const ps = packetStart ?? at + dur;
  const lp = c.at(labelT);
  return (
    <svg
      style={{ position: "absolute", left: 0, top: 0, overflow: "visible", opacity }}
      width={1920}
      height={1080}
    >
      <path
        d={c.d}
        fill="none"
        stroke={color}
        strokeOpacity={0.18}
        strokeWidth={width + 6}
        strokeDasharray={c.len}
        strokeDashoffset={c.len * (1 - p)}
        strokeLinecap="round"
      />
      <path
        d={c.d}
        fill="none"
        stroke={color}
        strokeWidth={width}
        strokeDasharray={dashed ? "8 10" : c.len}
        strokeDashoffset={dashed ? -f * 0.8 : c.len * (1 - p)}
        strokeLinecap="round"
        opacity={dashed ? p : 1}
      />
      {Array.from({ length: packets }).map((_, i) => {
        const period = c.len / speed;
        const t = (f - ps) / period - i / packets;
        if (f < ps || t < 0) return null;
        const tt = t % 1;
        const pt = c.at(tt);
        const fade = Math.min(1, tt * 6, (1 - tt) * 6);
        return (
          <g key={i} opacity={fade}>
            <circle cx={pt.x} cy={pt.y} r={11} fill={color} opacity={0.22} />
            <circle cx={pt.x} cy={pt.y} r={5} fill={color} />
          </g>
        );
      })}
      {label ? (
        <g opacity={ramp(f, at + dur * 0.6, at + dur + 8)}>
          <foreignObject x={lp.x - 160} y={lp.y - 22} width={320} height={44}>
            <div
              style={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                height: 44,
              }}
            >
              <span
                style={{
                  fontFamily: FONT.mono,
                  fontSize: 17,
                  color,
                  background: T.bg1,
                  border: `1px solid ${color}55`,
                  borderRadius: 8,
                  padding: "4px 10px",
                  whiteSpace: "nowrap",
                }}
              >
                {label}
              </span>
            </div>
          </foreignObject>
        </g>
      ) : null}
    </svg>
  );
}

const ICONS: Record<string, ReactNode> = {
  database: (
    <>
      <ellipse cx="20" cy="9" rx="13" ry="5" />
      <path d="M7 9v22c0 7 26 7 26 0V9M7 20c0 7 26 7 26 0" />
    </>
  ),
  nosql: (
    <>
      <path d="M8 6h24v8H8zM8 16h24v8H8zM8 26h24v8H8z" />
      <path d="M12 10h2M12 20h2M12 30h2" />
    </>
  ),
  api: <path d="m13 10-9 10 9 10m14-20 9 10-9 10M23 6l-6 28" />,
  file: <path d="M9 4h14l9 9v23H9ZM23 4v10h9M14 22h13M14 28h10" />,
  stream: <path d="M3 20h6l5-13 10 26 5-13h8" />,
  cloud: <path d="M11 31h19a7 7 0 0 0 0-14 10 10 0 0 0-19-2A8 8 0 0 0 11 31Z" />,
  table: (
    <>
      <rect x="4" y="7" width="32" height="26" rx="3" />
      <path d="M4 15h32M4 24h32M15 15v18" />
    </>
  ),
  check: <path d="m8 20 8 8L33 11" />,
  x: <path d="M10 10l20 20M30 10 10 30" />,
  lock: (
    <>
      <rect x="8" y="17" width="24" height="19" rx="3" />
      <path d="M13 17v-7a7 7 0 0 1 14 0v7M20 25v4" />
    </>
  ),
  unlock: (
    <>
      <rect x="8" y="17" width="24" height="19" rx="3" />
      <path d="M13 17v-7a7 7 0 0 1 13-3M20 25v4" />
    </>
  ),
  user: (
    <>
      <circle cx="20" cy="13" r="7" />
      <path d="M6 36c1-8 7-12 14-12s13 4 14 12" />
    </>
  ),
  shield: <path d="M20 4 6 9v10c0 9 6 15 14 18 8-3 14-9 14-18V9Z" />,
  spark: (
    <path d="M20 3c1 9 4 13 14 15-10 2-13 6-14 16-1-10-4-14-14-16 10-2 13-6 14-15Z" />
  ),
  code: <path d="m13 10-9 10 9 10m14-20 9 10-9 10M23 6l-6 28" />,
  chat: <path d="M5 7h30v20H17l-8 7v-7H5Z" />,
  layers: <path d="m3 13 17-9 17 9-17 9ZM3 21l17 9 17-9M3 29l17 9 17-9" />,
  server: (
    <>
      <rect x="5" y="5" width="30" height="12" rx="2" />
      <rect x="5" y="23" width="30" height="12" rx="2" />
      <path d="M10 11h3M10 29h3" />
    </>
  ),
  plug: <path d="M14 4v8M26 4v8M9 12h22v6a11 11 0 0 1-22 0ZM20 29v8" />,
  search: (
    <>
      <circle cx="17" cy="17" r="11" />
      <path d="m25 25 11 11" />
    </>
  ),
  chart: <path d="M5 35h30M9 35V21M17 35V11M25 35V17M33 35V6" />,
  tag: (
    <>
      <path d="M4 20 20 4h14v14L18 34Z" />
      <circle cx="28" cy="11" r="2.5" />
    </>
  ),
  link: (
    <path d="M17 23a7 7 0 0 0 10 0l6-6a7 7 0 0 0-10-10l-2 2M23 17a7 7 0 0 0-10 0l-6 6a7 7 0 0 0 10 10l2-2" />
  ),
  key: (
    <>
      <circle cx="12" cy="20" r="7" />
      <path d="M19 20h17M30 20v6M35 20v4" />
    </>
  ),
  clock: (
    <>
      <circle cx="20" cy="20" r="15" />
      <path d="M20 11v10l7 4" />
    </>
  ),
  play: <path d="M12 7v26l22-13Z" />,
  refresh: <path d="M33 13A14 14 0 1 0 34 25M33 5v8h-8" />,
  eye: (
    <>
      <path d="M3 20s6-11 17-11 17 11 17 11-6 11-17 11S3 20 3 20Z" />
      <circle cx="20" cy="20" r="5" />
    </>
  ),
  folder: <path d="M4 11h12l4 4h16v20H4ZM4 11V6h12l4 5h12v4" />,
  workflow: (
    <>
      <circle cx="9" cy="10" r="5" />
      <circle cx="31" cy="30" r="5" />
      <path d="M14 10h8a6 6 0 0 1 6 6v9" />
    </>
  ),
  branch: (
    <>
      <circle cx="11" cy="8" r="4" />
      <circle cx="11" cy="32" r="4" />
      <circle cx="29" cy="14" r="4" />
      <path d="M11 12v16M29 18c0 7-10 6-16 11" />
    </>
  ),
  bug: (
    <>
      <rect x="12" y="11" width="16" height="22" rx="8" />
      <path d="M15 11a5 5 0 0 1 10 0M4 18h8M28 18h8M4 28h8M28 28h8M20 17v16" />
    </>
  ),
  globe: (
    <>
      <circle cx="20" cy="20" r="15" />
      <path d="M5 20h30M20 5c-6 7-6 23 0 30M20 5c6 7 6 23 0 30" />
    </>
  ),
  audit: (
    <>
      <path d="M8 4h18l6 6v26H8Z" />
      <path d="M13 16h14M13 22h14M13 28h8" />
    </>
  ),
};

export function Icon({
  kind,
  size = 40,
  color = "currentColor",
  stroke = 2.2,
}: {
  kind: keyof typeof ICONS | string;
  size?: number;
  color?: string;
  stroke?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      stroke={color}
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0 }}
    >
      {ICONS[kind] ?? ICONS.table}
    </svg>
  );
}

/** Circular icon badge with glow. */
export function Orb({
  kind,
  color,
  size = 72,
  style,
}: {
  kind: string;
  color: string;
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.3,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: `linear-gradient(145deg, ${color}38, ${color}12)`,
        border: `1.5px solid ${color}70`,
        boxShadow: `0 0 30px ${color}30`,
        flexShrink: 0,
        ...style,
      }}
    >
      <Icon kind={kind} size={size * 0.55} color={color} />
    </div>
  );
}

export const RAIL = [
  "Sources",
  "Metadata",
  "Bronze",
  "Scope",
  "Profile",
  "Enrich",
  "Analyze",
  "Model",
  "Map",
  "Code",
  "Silver · Gold",
  "Evolve",
];

/** Bottom lifecycle rail. `active` may be fractional to animate progress. */
export function Rail({ active, opacity = 1 }: { active: number; opacity?: number }) {
  const left = 150;
  const right = 1770;
  const step = (right - left) / (RAIL.length - 1);
  const progressX = left + step * Math.max(0, Math.min(RAIL.length - 1, active));
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: 1920, height: 1080, opacity }}>
      <div
        style={{
          position: "absolute",
          left,
          width: right - left,
          top: 1012,
          height: 2,
          background: "rgba(220,235,228,0.12)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left,
          width: progressX - left,
          top: 1012,
          height: 2,
          background: `linear-gradient(90deg, ${T.mint}, ${T.copper})`,
          boxShadow: `0 0 12px ${T.copper}`,
        }}
      />
      {RAIL.map((name, i) => {
        const x = left + step * i;
        const reached = active >= i - 0.02;
        const current = Math.abs(active - i) < 0.5;
        return (
          <div key={name}>
            <div
              style={{
                position: "absolute",
                left: x - (current ? 8 : 5),
                top: 1013 - (current ? 8 : 5),
                width: current ? 16 : 10,
                height: current ? 16 : 10,
                borderRadius: 99,
                background: reached ? (current ? T.copper : T.mint) : T.bg1,
                border: `2px solid ${reached ? (current ? T.copper : T.mint) : "rgba(220,235,228,0.3)"}`,
                boxShadow: current ? `0 0 16px ${T.copper}` : undefined,
              }}
            />
            <div
              style={{
                position: "absolute",
                left: x - 80,
                width: 160,
                top: 1030,
                textAlign: "center",
                fontFamily: FONT.body,
                fontSize: 15,
                fontWeight: current ? 600 : 500,
                letterSpacing: 1,
                textTransform: "uppercase",
                color: current ? T.text : reached ? T.sub : T.dim,
              }}
            >
              {name}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Small window chrome used for UI mock-ups. */
export function Window({
  title,
  children,
  accent = T.copper,
  style,
  bar,
}: {
  title: string;
  children: ReactNode;
  accent?: string;
  style?: CSSProperties;
  bar?: ReactNode;
}) {
  return (
    <div
      style={{
        borderRadius: 18,
        overflow: "hidden",
        background: "#0B1714",
        border: `1.5px solid ${T.border}`,
        boxShadow: `0 30px 80px rgba(0,0,0,0.55), 0 0 60px ${accent}18`,
        display: "flex",
        flexDirection: "column",
        ...style,
      }}
    >
      <div
        style={{
          height: 46,
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "0 18px",
          background: "rgba(255,255,255,0.04)",
          borderBottom: `1px solid ${T.border}`,
          flexShrink: 0,
        }}
      >
        {["#FF6159", "#FFBD2E", "#28C941"].map((c) => (
          <div key={c} style={{ width: 12, height: 12, borderRadius: 9, background: c, opacity: 0.8 }} />
        ))}
        <div
          style={{
            marginLeft: 12,
            fontFamily: FONT.body,
            fontSize: 17,
            color: T.sub,
            fontWeight: 500,
          }}
        >
          {title}
        </div>
        <div style={{ marginLeft: "auto" }}>{bar}</div>
      </div>
      <div style={{ flex: 1, position: "relative" }}>{children}</div>
    </div>
  );
}

/** Animated pointer that moves through waypoints [frame, x, y] and clicks. */
export function Cursor({
  path,
  clicks = [],
}: {
  path: [number, number, number][];
  clicks?: number[];
}) {
  const f = useCurrentFrame();
  const frames = path.map((p) => p[0]);
  const x = interpolate(f, frames, path.map((p) => p[1]), { ...clampOpts, easing: Easing.inOut(Easing.cubic) });
  const y = interpolate(f, frames, path.map((p) => p[2]), { ...clampOpts, easing: Easing.inOut(Easing.cubic) });
  const visible = ramp(f, frames[0], frames[0] + 8);
  let ring = 0;
  let press = 1;
  for (const c of clicks) {
    if (f >= c && f < c + 20) {
      ring = (f - c) / 20;
      press = 0.85 + 0.15 * Math.min(1, (f - c) / 6);
    }
  }
  return (
    <div style={{ position: "absolute", left: x, top: y, opacity: visible, pointerEvents: "none" }}>
      {ring > 0 ? (
        <div
          style={{
            position: "absolute",
            left: -26 * ring - 4,
            top: -26 * ring - 4,
            width: 52 * ring + 8,
            height: 52 * ring + 8,
            borderRadius: 99,
            border: `3px solid ${T.copper}`,
            opacity: 1 - ring,
          }}
        />
      ) : null}
      <svg width={34} height={34} viewBox="0 0 24 24" style={{ transform: `scale(${press})`, filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.6))" }}>
        <path d="M3 2l7 19 2.5-7.5L20 11Z" fill="#fff" stroke="#111" strokeWidth={1.2} strokeLinejoin="round" />
      </svg>
    </div>
  );
}

export function Check({ at, size = 30, color = T.mint }: { at: number; size?: number; color?: string }) {
  const f = useCurrentFrame();
  const p = ramp(f, at, at + 14);
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: 99,
        background: `${color}22`,
        border: `1.5px solid ${color}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        transform: `scale(${0.5 + 0.5 * p})`,
        opacity: p,
        flexShrink: 0,
      }}
    >
      <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 40 40">
        <path
          d="m8 20 8 8L33 11"
          fill="none"
          stroke={color}
          strokeWidth={5}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={40}
          strokeDashoffset={40 * (1 - p)}
        />
      </svg>
    </div>
  );
}

/** Fixed footnote for honest framing. */
export function Note({ children, at = 0 }: { children: ReactNode; at?: number }) {
  const f = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        right: 120,
        top: 60,
        fontFamily: FONT.body,
        fontSize: 16,
        letterSpacing: 0.5,
        color: T.dim,
        opacity: ramp(f, at, at + 20),
      }}
    >
      {children}
    </div>
  );
}
