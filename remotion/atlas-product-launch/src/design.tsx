import { type CSSProperties, type ReactNode } from "react";
import {
  AbsoluteFill,
  Easing,
  Interactive,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/ibm-plex-mono/400.css";

export const C = {
  paper: "#F5F2EB",
  white: "#FFFEFA",
  ink: "#233A34",
  muted: "#68766E",
  line: "#DCDDD3",
  accent: "#BC603E",
  pale: "#F0DECE",
  green: "#487D64",
  dark: "#173C35",
  mint: "#C7D7C8",
  gold: "#BC9957",
};
export const ease = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
  easing: Easing.bezier(0.18, 0.8, 0.2, 1),
} as const;

export function Logo({
  size = 48,
  light = false,
  word = true,
}: {
  size?: number;
  light?: boolean;
  word?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: size * 0.26,
        color: light ? C.paper : C.ink,
      }}
    >
      <svg width={size} height={size} viewBox="0 0 40 40" aria-label="Atlas">
        <path d="M4 34 17 5h6l13 29h-7L20 13l-9 21Z" fill="currentColor" />
        <path d="m14 25 12 0 3 6H11Z" fill={C.accent} />
      </svg>
      {word ? (
        <span
          style={{
            fontSize: size * 0.66,
            letterSpacing: size * 0.11,
            fontWeight: 600,
          }}
        >
          ATLAS
        </span>
      ) : null}
    </div>
  );
}

export function Frame({
  children,
  chapter,
  index,
  dark = false,
}: {
  children: ReactNode;
  chapter: string;
  index: number;
  dark?: boolean;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{
        background: dark ? C.dark : C.paper,
        color: dark ? C.paper : C.ink,
        fontFamily: "Inter",
        overflow: "hidden",
      }}
    >
      <AbsoluteFill
        style={{
          opacity: dark ? 0.06 : 0.18,
          backgroundImage: `radial-gradient(${dark ? "#fff" : "#929A8A"} 1px, transparent 1px)`,
          backgroundSize: "28px 28px",
          maskImage: "linear-gradient(90deg,transparent 10%,black 90%)",
        }}
      />
      <div style={{ position: "absolute", left: 96, top: 54 }}>
        <Logo size={42} light={dark} />
      </div>
      <div
        style={{
          position: "absolute",
          right: 100,
          top: 64,
          fontSize: 22,
          letterSpacing: 3,
          color: dark ? C.mint : C.muted,
          textTransform: "uppercase",
        }}
      >
        {String(index).padStart(2, "0")} / {chapter}
      </div>
      <Interactive.Div
        name="Scene artwork"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(frame, [0, 0.65 * fps], [0, 1], ease),
          translate: interpolate(
            frame,
            [0, 0.8 * fps],
            ["0px 18px", "0px 0px"],
            ease,
          ),
        }}
      >
        {children}
      </Interactive.Div>
      <div
        style={{
          position: "absolute",
          left: 100,
          right: 100,
          bottom: 32,
          display: "flex",
          gap: 9,
        }}
      >
        {Array.from({ length: 12 }, (_, i) => (
          <div
            key={i}
            style={{
              height: 3,
              flex: 1,
              background: i < index ? C.accent : dark ? "#426158" : "#DEDFD5",
            }}
          />
        ))}
      </div>
    </AbsoluteFill>
  );
}

export function Reveal({
  children,
  at = 0,
  style,
}: {
  children: ReactNode;
  at?: number;
  style?: CSSProperties;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      style={{
        ...style,
        opacity: interpolate(
          frame,
          [at * fps, (at + 0.75) * fps],
          [0, 1],
          ease,
        ),
        translate: interpolate(
          frame,
          [at * fps, (at + 0.85) * fps],
          ["0px 24px", "0px 0px"],
          ease,
        ),
      }}
    >
      {children}
    </div>
  );
}

export function Heading({
  kicker,
  children,
  subtitle,
  dark = false,
}: {
  kicker: string;
  children: ReactNode;
  subtitle?: string;
  dark?: boolean;
}) {
  return (
    <div style={{ position: "absolute", left: 100, top: 154, right: 100 }}>
      <div
        style={{
          fontSize: 23,
          letterSpacing: 3,
          textTransform: "uppercase",
          color: dark ? C.mint : C.accent,
          marginBottom: 18,
        }}
      >
        {kicker}
      </div>
      <h1
        style={{
          fontSize: 88,
          lineHeight: 1.05,
          letterSpacing: -4.5,
          fontWeight: 500,
          margin: 0,
        }}
      >
        {children}
      </h1>
      {subtitle ? (
        <p
          style={{
            fontSize: 31,
            color: dark ? C.mint : C.muted,
            margin: "24px 0 0",
            lineHeight: 1.45,
          }}
        >
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}

export function Icon({
  kind,
  size = 44,
  color = "currentColor",
}: {
  kind: string;
  size?: number;
  color?: string;
}) {
  const paths: Record<string, ReactNode> = {
    database: (
      <>
        <ellipse cx="20" cy="9" rx="13" ry="5" />
        <path d="M7 9v22c0 7 26 7 26 0V9M7 20c0 7 26 7 26 0" />
      </>
    ),
    file: (
      <>
        <path d="M9 4h14l9 9v23H9ZM23 4v10h9M14 22h13M14 28h10" />
      </>
    ),
    stream: (
      <>
        <path d="M4 20h5l5-13 10 26 5-13h7M7 8h2M31 32h2" />
      </>
    ),
    api: (
      <>
        <path d="m13 10-9 10 9 10m14-20 9 10-9 10M23 6l-6 28" />
      </>
    ),
    folder: <path d="M4 11h12l4 4h16v20H4ZM4 11V6h12l4 5h12v4" />,
    document: (
      <>
        <path d="M6 5h28v30H6ZM13 12h14M13 19h14M13 26h8" />
      </>
    ),
    check: <path d="m8 20 8 8L33 11" />,
    model: (
      <>
        <rect x="14" y="3" width="12" height="9" rx="2" />
        <rect x="2" y="28" width="12" height="9" rx="2" />
        <rect x="26" y="28" width="12" height="9" rx="2" />
        <path d="M20 12v8H8v8m12-8h12v8" />
      </>
    ),
    arrow: <path d="M4 20h30m-10-10 10 10-10 10" />,
    lock: (
      <>
        <rect x="8" y="17" width="24" height="19" rx="3" />
        <path d="M13 17v-7a7 7 0 0 1 14 0v7M20 25v4" />
      </>
    ),
    search: (
      <>
        <circle cx="17" cy="17" r="11" />
        <path d="m25 25 11 11" />
      </>
    ),
    code: (
      <>
        <path d="m13 10-9 10 9 10m14-20 9 10-9 10M23 6l-6 28" />
      </>
    ),
    layers: (
      <>
        <path d="m3 13 17-9 17 9-17 9ZM3 21l17 9 17-9M3 29l17 9 17-9" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[kind] ?? paths.document}
    </svg>
  );
}

export function LinkLine({
  d,
  at = 1,
  color = C.accent,
  dashed = false,
}: {
  d: string;
  at?: number;
  color?: string;
  dashed?: boolean;
}) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <svg
      width={1920}
      height={1080}
      style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
    >
      <path d={d} fill="none" stroke={color} strokeWidth={2.5} opacity={0.2} />
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={3}
        pathLength={1}
        strokeDasharray={dashed ? ".012 .01" : "1"}
        strokeDashoffset={
          dashed
            ? -f / 600
            : interpolate(f, [at * fps, (at + 1.8) * fps], [1, 0], ease)
        }
        opacity={interpolate(f, [at * fps, (at + 0.4) * fps], [0, 1], ease)}
      />
    </svg>
  );
}

export function Chip({
  children,
  dark = false,
  color = C.green,
}: {
  children: ReactNode;
  dark?: boolean;
  color?: string;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 9,
        padding: "10px 16px",
        borderRadius: 6,
        background: dark ? "#35554B" : color === C.green ? "#E6EDE3" : C.pale,
        color: dark ? C.mint : color,
        fontSize: 23,
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}

export function AppWindow({
  tab,
  children,
  style,
}: {
  tab: string;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div
      style={{
        position: "absolute",
        left: 100,
        right: 100,
        top: 354,
        height: 478,
        border: `1px solid ${C.line}`,
        borderRadius: 15,
        background: C.white,
        boxShadow: "0 18px 55px #263A3410",
        overflow: "hidden",
        ...style,
      }}
    >
      <div
        style={{
          height: 68,
          display: "flex",
          alignItems: "center",
          padding: "0 30px",
          gap: 26,
          borderBottom: `1px solid ${C.line}`,
          fontSize: 23,
        }}
      >
        <Logo size={27} />
        <span style={{ color: C.line }}>│</span>
        <span>Retail Sales</span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: 18,
            color: C.muted,
            letterSpacing: 1,
          }}
        >
          ILLUSTRATIVE DEMO
        </span>
        <Icon kind="lock" size={21} />
      </div>
      <div
        style={{
          height: 62,
          display: "flex",
          alignItems: "center",
          gap: 32,
          padding: "0 32px",
          borderBottom: `1px solid ${C.line}`,
          fontSize: 21,
        }}
      >
        {[
          "Scope",
          "Profiling",
          "Enrichment",
          "Analysis",
          "Logical",
          "Dimensional",
          "Mapping",
          "Code",
          "Validation",
        ].map((t) => (
          <span
            key={t}
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              color: t === tab ? C.accent : C.muted,
              borderBottom:
                t === tab ? `3px solid ${C.accent}` : "3px solid transparent",
            }}
          >
            {t}
          </span>
        ))}
      </div>
      <div style={{ padding: "28px 34px" }}>{children}</div>
    </div>
  );
}

export function Ledger({
  headers,
  rows,
  highlight = -1,
}: {
  headers: string[];
  rows: string[][];
  highlight?: number;
}) {
  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        fontSize: 28,
        textAlign: "left",
        tableLayout: "fixed",
      }}
    >
      <thead>
        <tr>
          {headers.map((h) => (
            <th
              key={h}
              style={{
                fontSize: 20,
                fontWeight: 500,
                color: C.muted,
                padding: "0 14px 17px",
                borderBottom: `1px solid ${C.line}`,
              }}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr
            key={i}
            style={{ background: i === highlight ? "#F5E5D7" : "transparent" }}
          >
            {row.map((value, j) => (
              <td
                key={j}
                style={{
                  padding: "19px 14px",
                  borderBottom: `1px solid ${C.line}`,
                  color: j === 0 ? C.ink : C.muted,
                }}
              >
                {value}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Entity({
  name,
  fields,
  x,
  y,
  width = 330,
  accent = false,
  at = 0,
  highlightField,
}: {
  name: string;
  fields: string[];
  x: number;
  y: number;
  width?: number;
  accent?: boolean;
  at?: number;
  highlightField?: string;
}) {
  return (
    <Reveal
      at={at}
      style={{
        position: "absolute",
        left: x,
        top: y,
        width,
        border: `1.5px solid ${accent ? C.accent : C.line}`,
        background: C.white,
        borderRadius: 12,
        overflow: "hidden",
        boxShadow: "0 12px 26px #173C3508",
      }}
    >
      <div
        style={{
          fontSize: 32,
          fontWeight: 500,
          padding: "18px 24px",
          background: accent ? C.accent : C.ink,
          color: C.paper,
        }}
      >
        {name}
      </div>
      {fields.map((f, i) => (
        <div
          key={f}
          style={{
            padding: "11px 24px",
            fontSize: 28,
            fontFamily: "IBM Plex Mono",
            color: f === highlightField || i === 0 ? C.accent : C.muted,
            background: f === highlightField ? C.pale : undefined,
            borderTop: `1px solid ${C.line}`,
          }}
        >
          {f}
        </div>
      ))}
    </Reveal>
  );
}
