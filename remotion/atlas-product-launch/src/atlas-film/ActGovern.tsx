import { type ReactNode } from "react";
import { useCurrentFrame } from "remotion";
import {
  AtlasMark,
  Check,
  Flow,
  FONT,
  Glass,
  Icon,
  Orb,
  Pill,
  RAIL,
  ramp,
  Scene,
  T,
  Title,
} from "./kit";
import { len } from "./timeline";

function Avatar({ name, color, size = 52 }: { name: string; color: string; size?: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: 99,
        background: `${color}30`,
        border: `2px solid ${color}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: FONT.head,
        fontWeight: 700,
        fontSize: size * 0.42,
        color,
        flexShrink: 0,
      }}
    >
      {name[0]}
    </div>
  );
}

/** Horizontal shake for a rejected action. */
function shake(f: number, at: number) {
  if (f < at || f > at + 18) return 0;
  return Math.sin((f - at) * 1.6) * 10 * (1 - (f - at) / 18);
}

/* ───────────────────────── 15. Security ───────────────────────── */

const VAULTS = [
  { t: "Retail", x: 560, c: T.mint, at: 80, verdict: "Architect", d: "Reads and changes models", ok: true },
  { t: "Finance", x: 980, c: T.gold, at: 120, verdict: "Viewer", d: "Read only, writes refused", ok: true },
  { t: "HR", x: 1400, c: T.red, at: 160, verdict: "No access", d: "Not even visible to her", ok: false },
];

const ROLES = [
  { r: "Viewer", d: "Read authorized records", h: 120 },
  { r: "Developer", d: "+ Change metadata", h: 160 },
  { r: "Architect", d: "+ Change models", h: 200 },
  { r: "Tenant Admin", d: "+ Administer the tenant", h: 240 },
];

export const Security = () => {
  const f = useCurrentFrame();
  return (
    <Scene duration={len("Security")}>
      <Title
        kicker="13 · Tenant security"
        title="Every tenant is its own secure space."
        sub="Identity comes from Microsoft Entra ID. Roles are checked on the server, per tenant, for every read and write."
        kickerColor={T.gold}
      />
      <Glass at={20} x={120} y={350} w={360} h={276} pad={26} glow={T.azure} from="left">
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Avatar name="Maya" color={T.azure} size={64} />
          <div>
            <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 32 }}>Maya</div>
            <div style={{ fontSize: 18, color: T.sub }}>Signed in with Entra ID</div>
          </div>
        </div>
        <div style={{ marginTop: 22, fontSize: 18, color: T.sub, lineHeight: 1.5 }}>
          The server resolves who she is. The browser or agent cannot claim a role.
        </div>
      </Glass>
      {VAULTS.map((v, i) => {
        const p = ramp(f, v.at + 20, v.at + 34);
        const y = 330 + i * 110;
        return (
          <div key={v.t}>
            <Flow
              a={{ x: 480, y: 480 }}
              b={{ x: 640, y: y + 48 }}
              at={v.at}
              dur={20}
              color={v.c}
              width={2.5}
              packets={1}
              speed={50}
              opacity={v.ok ? 1 : 0.6}
              dashed={!v.ok}
            />
            <div
              style={{
                position: "absolute",
                left: 640,
                top: y,
                width: 740,
                height: 96,
                borderRadius: 18,
                boxSizing: "border-box",
                padding: "0 26px",
                display: "flex",
                alignItems: "center",
                gap: 16,
                border: `2px ${v.ok ? "solid" : "dashed"} ${p > 0 ? v.c + (v.ok ? "AA" : "66") : T.border}`,
                background: v.ok ? `linear-gradient(90deg, ${v.c}${p > 0 ? "1E" : "08"}, rgba(255,255,255,0.02))` : "transparent",
                boxShadow: v.ok && p > 0 ? `0 0 40px ${v.c}28` : undefined,
                opacity: ramp(f, 30 + i * 6, 46 + i * 6) * (v.ok ? 1 : 1 - 0.4 * p),
              }}
            >
              <Icon kind={v.ok ? (p > 0 ? "unlock" : "lock") : "eye"} size={34} color={p > 0 ? v.c : T.sub} />
              <span style={{ width: 150, display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: 14, letterSpacing: 2.5, color: T.dim, fontWeight: 600 }}>TENANT</span>
                <span style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 32, lineHeight: 1.05 }}>{v.t}</span>
              </span>
              <span style={{ opacity: p, display: "flex", alignItems: "center", gap: 14 }}>
                <Pill color={v.c} size={19} solid={v.ok}>
                  {v.verdict}
                </Pill>
                <span style={{ fontSize: 20, color: T.sub }}>{v.d}</span>
              </span>
            </div>
          </div>
        );
      })}
      <div style={{ position: "absolute", left: 120, top: 660, fontSize: 18, letterSpacing: 3, fontWeight: 600, textTransform: "uppercase", color: T.sub, opacity: ramp(f, 200, 215) }}>
        Roles build on each other
      </div>
      {ROLES.map((r, i) => {
        const p = ramp(f, 210 + i * 14, 230 + i * 14);
        return (
          <div
            key={r.r}
            style={{
              position: "absolute",
              left: 120 + i * 428,
              top: 950 - r.h * p,
              width: 404,
              height: r.h * p,
              borderRadius: "16px 16px 4px 4px",
              boxSizing: "border-box",
              padding: "16px 20px",
              overflow: "hidden",
              background: `linear-gradient(180deg, ${T.gold}${["14", "20", "2C", "3A"][i]}, ${T.gold}08)`,
              border: `1.5px solid ${T.gold}66`,
              opacity: Math.min(1, p * 4),
            }}
          >
            <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 28 }}>{r.r}</div>
            <div style={{ fontSize: 19, color: T.sub, marginTop: 4 }}>{r.d}</div>
          </div>
        );
      })}
      <Glass at={200} x={1420} y={330} w={390} h={316} pad={28} glow={T.copper} from="right">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Icon kind="shield" size={30} color={T.copper} />
          <span style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 28 }}>Super Admin</span>
        </div>
        <div style={{ fontSize: 20, color: T.sub, lineHeight: 1.45, marginTop: 12 }}>
          Works across tenants, yet never bypasses locks, revision checks or the audit log.
        </div>
      </Glass>
    </Scene>
  );
};

/* ───────────────────────── 16. Locks and concurrency ───────────────────────── */

function Column({ x, at, icon, title, color, children, foot }: { x: number; at: number; icon: string; title: string; color: string; children: ReactNode; foot: string }) {
  return (
    <Glass at={at} x={x} y={320} w={530} h={640} pad={28} glow={color}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <Orb kind={icon} color={color} size={56} />
        <span style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 34 }}>{title}</span>
      </div>
      <div style={{ position: "relative", height: 420, marginTop: 24 }}>{children}</div>
      <div style={{ fontSize: 19, color: T.sub, lineHeight: 1.45, borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>{foot}</div>
    </Glass>
  );
}

function Row({ children, top, at, x = 0, color }: { children: ReactNode; top: number; at: number; x?: number; color?: string }) {
  const f = useCurrentFrame();
  const p = ramp(f, at, at + 14);
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        right: 0,
        top,
        padding: "14px 18px",
        borderRadius: 14,
        background: color ? `${color}18` : "rgba(255,255,255,0.04)",
        border: `1px solid ${color ? color + "77" : T.border}`,
        opacity: p,
        transform: `translateY(${(1 - p) * 14}px)`,
      }}
    >
      {children}
    </div>
  );
}

function Bar({ start, end, color }: { start: number; end: number; color: string }) {
  const f = useCurrentFrame();
  const p = ramp(f, start, end, (t) => t);
  return (
    <div style={{ height: 8, borderRadius: 9, background: "rgba(255,255,255,0.08)", marginTop: 12, overflow: "hidden" }}>
      <div style={{ width: `${p * 100}%`, height: "100%", background: color, boxShadow: `0 0 12px ${color}` }} />
    </div>
  );
}

export const Locks = () => {
  const f = useCurrentFrame();
  const lockOn = f >= 50;
  const ring = ramp(f, 50, 470, (t) => t);
  const runADone = f >= 300;
  const runBStart = 312;
  const rejected = f >= 300 && f < 370;
  const rebuilt = f >= 395;
  return (
    <Scene duration={len("Locks")}>
      <Title
        kicker="14 · Concurrency"
        title="Parallel work never overwrites itself."
        sub="Tenant locks, one running workflow per tenant, and revision checks protect every change."
        kickerColor={T.gold}
      />
      <Column x={120} at={10} icon="lock" title="Tenant Lock" color={T.copper} foot="An override must give a reason, and it is audited.">
        <Row top={0} at={24}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <Avatar name="Maya" color={T.azure} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 22, fontWeight: 600 }}>Maya · plugin</div>
              <div style={{ fontSize: 18, color: lockOn ? T.mint : T.sub }}>{lockOn ? "Holds the lock for Retail" : "Acquiring lock…"}</div>
            </div>
            <svg width={56} height={56} viewBox="0 0 56 56">
              <circle cx={28} cy={28} r={24} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={4} />
              <circle
                cx={28}
                cy={28}
                r={24}
                fill="none"
                stroke={T.copper}
                strokeWidth={4}
                strokeDasharray={151}
                strokeDashoffset={lockOn ? 151 * ring * 0.3 : 151}
                transform="rotate(-90 28 28)"
                strokeLinecap="round"
              />
              <g transform="translate(16 15) scale(0.6)">
                <rect x="8" y="17" width="24" height="19" rx="3" fill="none" stroke={lockOn ? T.copper : T.sub} strokeWidth={3} />
                <path d={lockOn ? "M13 17v-7a7 7 0 0 1 14 0v7" : "M13 17v-7a7 7 0 0 1 13-3"} fill="none" stroke={lockOn ? T.copper : T.sub} strokeWidth={3} />
              </g>
            </svg>
          </div>
        </Row>
        <div style={{ position: "absolute", top: 108, left: 0, fontSize: 17, color: T.dim, opacity: ramp(f, 60, 75) }}>
          Lease set by database time · up to 4 hours
        </div>
        <Row top={160} at={100} color={f >= 140 ? T.red : undefined}>
          <div style={{ display: "flex", alignItems: "center", gap: 14, transform: `translateX(${shake(f, 140)}px)` }}>
            <Avatar name="Sam" color={T.violet} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 22, fontWeight: 600 }}>Sam · web app</div>
              <div style={{ fontSize: 18, color: f >= 140 ? T.red : T.sub }}>
                {f >= 140 ? "Blocked: Retail is locked by Maya" : "Applies a metadata change…"}
              </div>
            </div>
            {f >= 140 ? <Icon kind="x" size={30} color={T.red} stroke={3} /> : null}
          </div>
        </Row>
        <div style={{ position: "absolute", top: 290, left: 0, right: 0, fontSize: 21, lineHeight: 1.5, color: T.text, opacity: ramp(f, 170, 190) }}>
          Only the lock owner can write. Roles alone are not enough, not even for a Super Admin.
        </div>
      </Column>
      <Column x={700} at={110} icon="workflow" title="One run per tenant" color={T.violet} foot="Run exclusivity is separate from the lock. Both are enforced in the database.">
        <Row top={0} at={130} color={runADone ? T.mint : undefined}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 22, fontWeight: 600 }}>Run A · Logical model</span>
            {runADone ? <Check at={300} size={28} /> : <Pill color={T.violet} size={15}>Running</Pill>}
          </div>
          <Bar start={140} end={300} color={runADone ? T.mint : T.violet} />
        </Row>
        <Row top={130} at={170} color={f >= runBStart ? T.violet : T.gold}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 22, fontWeight: 600 }}>Run B · Mapping</span>
            <Pill color={f >= runBStart ? T.violet : T.gold} size={15}>
              {f >= runBStart ? "Running" : "Waiting"}
            </Pill>
          </div>
          <div style={{ fontSize: 18, color: T.sub, marginTop: 8 }}>
            {f >= runBStart ? "Started after Run A finished" : "Another workflow is running for Retail"}
          </div>
          {f >= runBStart ? <Bar start={runBStart} end={470} color={T.violet} /> : null}
        </Row>
        <div style={{ position: "absolute", top: 300, left: 0, right: 0, fontSize: 21, lineHeight: 1.5, opacity: ramp(f, 200, 220) }}>
          Workflows never race each other inside the same tenant.
        </div>
      </Column>
      <Column x={1280} at={210} icon="branch" title="Revision checks" color={T.mint} foot="Stale work can never overwrite newer work.">
        <div style={{ position: "absolute", top: 0, left: 0, opacity: ramp(f, 225, 240) }}>
          <Pill color={T.mint} size={19}>Current model · revision 43</Pill>
        </div>
        <Row top={64} at={245} color={rebuilt ? T.mint : rejected ? T.red : undefined}>
          <div style={{ transform: `translateX(${shake(f, 300)}px)` }}>
            <div style={{ fontSize: 22, fontWeight: 600 }}>Sam's draft</div>
            <div style={{ fontSize: 18, color: rebuilt ? T.mint : rejected ? T.red : T.sub, marginTop: 4 }}>
              {rebuilt ? "Rebuilt on revision 43" : rejected ? "Rejected: based on revision 42" : f >= 370 ? "Refreshing snapshot…" : "Based on revision 42 · staging…"}
            </div>
          </div>
        </Row>
        <div style={{ position: "absolute", top: 190, left: 0, right: 0, display: "flex", alignItems: "center", gap: 14, opacity: ramp(f, 370, 385) }}>
          <div style={{ transform: `rotate(${ramp(f, 370, 400) * 360}deg)` }}>
            <Icon kind="refresh" size={32} color={T.mint} />
          </div>
          <span style={{ fontSize: 21 }}>Refresh, reassess, then stage again</span>
        </div>
        <div style={{ position: "absolute", top: 260, left: 0, display: "flex", alignItems: "center", gap: 12, opacity: ramp(f, 400, 415) }}>
          <Check at={400} size={30} />
          <span style={{ fontSize: 21 }}>Validated against the latest model</span>
        </div>
      </Column>
    </Scene>
  );
};

/* ───────────────────────── 17. Close ───────────────────────── */

export const Close = () => {
  const f = useCurrentFrame();
  const left = 170;
  const right = 1750;
  const step = (right - left) / (RAIL.length - 1);
  const lit = ramp(f, 110, 190, (t) => t) * (RAIL.length - 1);
  return (
    <Scene duration={len("Close")} fadeOut={30}>
      <div style={{ position: "absolute", top: 220, width: 1920, display: "flex", justifyContent: "center", alignItems: "center", gap: 36, opacity: ramp(f, 6, 30), transform: `scale(${0.94 + 0.06 * ramp(f, 6, 40)})` }}>
        <AtlasMark size={130} />
        <span style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 110, letterSpacing: 26 }}>ATLAS</span>
      </div>
      <div style={{ position: "absolute", top: 430, width: 1920, display: "flex", justifyContent: "center", gap: 28 }}>
        {["Understand.", "Model.", "Build.", "Evolve."].map((w, i) => {
          const p = ramp(f, 34 + i * 12, 54 + i * 12);
          return (
            <span
              key={w}
              style={{
                fontFamily: FONT.head,
                fontWeight: 700,
                fontSize: 72,
                color: i === 3 ? T.copper : T.text,
                opacity: p,
                transform: `translateY(${(1 - p) * 20}px)`,
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
      <div style={{ position: "absolute", top: 548, width: 1920, textAlign: "center", fontSize: 30, color: T.sub, opacity: ramp(f, 90, 110) }}>
        Governed from source to lakehouse, with the AI assistant you already use.
      </div>
      <div style={{ position: "absolute", left, width: right - left, top: 760, height: 3, background: "rgba(220,235,228,0.12)" }} />
      <div
        style={{
          position: "absolute",
          left,
          width: step * lit,
          top: 760,
          height: 3,
          background: `linear-gradient(90deg, ${T.mint}, ${T.copper})`,
          boxShadow: `0 0 16px ${T.copper}`,
        }}
      />
      {RAIL.map((name, i) => {
        const on = lit >= i;
        return (
          <div key={name}>
            <div
              style={{
                position: "absolute",
                left: left + step * i - 9,
                top: 761 - 9,
                width: 18,
                height: 18,
                borderRadius: 99,
                background: on ? (i === RAIL.length - 1 ? T.copper : T.mint) : T.bg1,
                border: `2px solid ${on ? T.mint : "rgba(220,235,228,0.3)"}`,
                boxShadow: on ? `0 0 14px ${T.mint}` : undefined,
                opacity: ramp(f, 100, 115),
              }}
            />
            <div
              style={{
                position: "absolute",
                left: left + step * i - 80,
                width: 160,
                top: 790,
                textAlign: "center",
                fontSize: 17,
                letterSpacing: 1.5,
                textTransform: "uppercase",
                fontWeight: 600,
                color: on ? T.text : T.dim,
                opacity: ramp(f, 100, 115),
              }}
            >
              {name}
            </div>
          </div>
        );
      })}
    </Scene>
  );
};
