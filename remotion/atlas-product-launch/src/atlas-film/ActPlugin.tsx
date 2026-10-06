import { type ReactNode } from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import {
  AtlasMark,
  Check,
  clampOpts,
  Counter,
  Cursor,
  Flow,
  FONT,
  Glass,
  Icon,
  Orb,
  Pill,
  ramp,
  Scene,
  T,
  Title,
  Type,
  Window,
} from "./kit";
import { SqlLine } from "./ActBuild";
import { len } from "./timeline";

/* ───────────────────────── Chat bubble ───────────────────────── */

function Bubble({
  who,
  at,
  children,
}: {
  who: "you" | "atlas";
  at: number;
  children: ReactNode;
}) {
  const f = useCurrentFrame();
  const p = ramp(f, at, at + 14);
  const you = who === "you";
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: you ? "flex-end" : "flex-start",
        opacity: p,
        transform: `translateY(${(1 - p) * 18}px)`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 15,
          letterSpacing: 1.5,
          textTransform: "uppercase",
          fontWeight: 600,
          color: you ? T.sub : T.copper,
          marginBottom: 6,
        }}
      >
        {you ? null : <AtlasMark size={18} />}
        {you ? "You" : "Atlas"}
      </div>
      <div
        style={{
          maxWidth: 820,
          padding: "14px 20px",
          borderRadius: 16,
          fontSize: 23,
          lineHeight: 1.45,
          background: you ? `${T.azure}24` : "rgba(255,255,255,0.05)",
          border: `1px solid ${you ? T.azure + "55" : T.border}`,
        }}
      >
        {children}
      </div>
    </div>
  );
}

/* ───────────────────────── 12. Two ways ───────────────────────── */

export const TwoWays = () => {
  const f = useCurrentFrame();
  return (
    <Scene duration={len("TwoWays")}>
      <Title
        kicker="10 · Two ways to work"
        title="Two ways to work. One source of truth."
        sub="The Atlas web app and the Atlas plugin read and write the same governed records."
      />
      <Glass at={10} x={110} y={315} w={830} h={530} pad={0} from="left" style={{ overflow: "hidden" }}>
        <div style={{ height: 44, display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: `1px solid ${T.border}` }}>
          <Icon kind="globe" size={22} color={T.sub} />
          <span style={{ fontSize: 17, color: T.sub }}>Atlas web app · Databricks App</span>
        </div>
        <Img src={staticFile("captures/complete/overview.png")} style={{ width: 830, height: 467, objectFit: "cover", objectPosition: "top left" }} />
      </Glass>
      <div style={{ position: "absolute", left: 980, top: 315, opacity: ramp(f, 20, 36), transform: `translateX(${(1 - ramp(f, 20, 40)) * 40}px)` }}>
        <Window title="VS Code · Copilot Chat" accent={T.violet} style={{ width: 830, height: 530 }}>
          <div style={{ padding: 26, display: "flex", flexDirection: "column", gap: 18 }}>
            <Bubble who="you" at={40}>
              Start atlas. Tenant: Retail. Model: Customer Orders 360.
            </Bubble>
            <Bubble who="atlas" at={80}>
              Ready. Snapshot loaded at revision 42. What would you like to change or understand?
            </Bubble>
          </div>
        </Window>
      </div>
      <Flow a={{ x: 525, y: 845 }} b={{ x: 750, y: 914 }} at={110} color={T.mint} packets={2} speed={50} />
      <Flow a={{ x: 1395, y: 845 }} b={{ x: 1170, y: 914 }} at={110} color={T.violet} packets={2} speed={50} />
      <Glass at={100} x={750} y={872} w={420} h={84} pad={0} glow={T.gold} radius={16} from="scale">
        <div style={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center", gap: 14 }}>
          <Icon kind="database" size={38} color={T.gold} />
          <span style={{ fontSize: 24, fontWeight: 600, color: T.gold }}>Shared Atlas records</span>
        </div>
      </Glass>
    </Scene>
  );
};

/* ───────────────────────── 13. Plugin connection ───────────────────────── */

const CHAIN = [
  { t: "AI assistant", d: "GitHub Copilot in VS Code, or Codex", icon: "chat", c: T.violet },
  { t: "Atlas plugin", d: "12 modeling skills and Atlas Local Workbench", icon: "atlas", c: T.copper },
  { t: "Stage Runner", d: "VS Code extension with Microsoft sign-in", icon: "plug", c: T.azure },
  { t: "Atlas MCP server", d: "Governed, audited tools only", icon: "server", c: T.mint },
  { t: "Atlas records", d: "PostgreSQL, plus read-only Databricks SQL", icon: "database", c: T.gold },
];

const SKILLS = [
  "Start & route",
  "Investigate",
  "Source analysis",
  "Conceptual model",
  "Logical model",
  "Dimensional model",
  "Mapping",
  "Code generation",
  "Verify",
  "Model change",
  "Metadata",
  "Registration",
];

export const PluginConnect = () => {
  const f = useCurrentFrame();
  const W = 300;
  const X = (i: number) => 120 + i * 347;
  const Y = 360;
  const H = 250;
  return (
    <Scene duration={len("PluginConnect")}>
      <Title
        kicker="11 · Atlas plugin"
        title="Plug Atlas into the AI assistant you already use."
        sub="The plugin brings Atlas skills to GitHub Copilot or Codex, with the AI model you choose."
      />
      {CHAIN.map((c, i) => (
        <Glass key={c.t} at={20 + i * 14} x={X(i)} y={Y} w={W} h={H} glow={c.c} pad={24}>
          {c.icon === "atlas" ? (
            <div
              style={{
                width: 64,
                height: 64,
                borderRadius: 19,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: `${T.copper}26`,
                border: `1.5px solid ${T.copper}70`,
              }}
            >
              <AtlasMark size={40} />
            </div>
          ) : (
            <Orb kind={c.icon} color={c.c} size={64} />
          )}
          <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 31, marginTop: 16 }}>{c.t}</div>
          <div style={{ fontSize: 19, color: T.sub, lineHeight: 1.4, marginTop: 6 }}>{c.d}</div>
          {i === 0 ? (
            <div
              style={{
                marginTop: 12,
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "5px 12px",
                borderRadius: 8,
                border: `1px solid ${T.violet}66`,
                fontSize: 16,
                color: T.violet,
                opacity: ramp(f, 90, 110),
              }}
            >
              Model: your choice ▾
            </div>
          ) : null}
        </Glass>
      ))}
      {[0, 1, 2, 3].map((i) => (
        <div key={i}>
          <Flow a={{ x: X(i) + W, y: Y + 105 }} b={{ x: X(i + 1), y: Y + 105 }} at={60 + i * 12} dur={14} color={CHAIN[i + 1].c} packets={1} speed={30} />
          <Flow a={{ x: X(i + 1), y: Y + 150 }} b={{ x: X(i) + W, y: Y + 150 }} at={70 + i * 12} dur={14} color={T.sub} packets={1} speed={30} width={1.5} packetStart={140 + i * 6} />
        </div>
      ))}
      <div style={{ position: "absolute", left: 120, top: 650, display: "flex", alignItems: "center", gap: 14, opacity: ramp(f, 150, 166) }}>
        <AtlasMark size={30} />
        <span style={{ fontSize: 20, letterSpacing: 3, textTransform: "uppercase", color: T.copper, fontWeight: 600 }}>
          12 skills, loaded only when needed
        </span>
      </div>
      <div style={{ position: "absolute", left: 120, top: 700, width: 1690, display: "flex", flexWrap: "wrap", gap: 12 }}>
        {SKILLS.map((s, i) => {
          const p = ramp(f, 160 + i * 6, 176 + i * 6);
          return (
            <span key={s} style={{ opacity: p, transform: `scale(${0.7 + 0.3 * p})` }}>
              <Pill color={s === "Model change" ? T.copper : T.mint} size={22}>
                {s}
              </Pill>
            </span>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 120, top: 860, width: 1690, display: "flex", gap: 18 }}>
        {[
          { t: "Sign-in tokens never reach the agent", i: "lock" },
          { t: "No direct deletes or arbitrary writes", i: "shield" },
          { t: "Every tool call is audited", i: "audit" },
        ].map((g, i) => (
          <div
            key={g.t}
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              gap: 14,
              padding: "16px 20px",
              borderRadius: 14,
              background: `${T.gold}10`,
              border: `1px solid ${T.gold}44`,
              fontSize: 21,
              opacity: ramp(f, 270 + i * 16, 290 + i * 16),
              transform: `translateY(${(1 - ramp(f, 270 + i * 16, 292 + i * 16)) * 16}px)`,
            }}
          >
            <Icon kind={g.i} size={28} color={T.gold} />
            {g.t}
          </div>
        ))}
      </div>
    </Scene>
  );
};

/* ───────────────────────── 14. Plugin change in action ───────────────────────── */

const STEPS = [
  { s: "Ask", at: 0 },
  { s: "Gather context", at: 100 },
  { s: "Impact", at: 260 },
  { s: "Propose", at: 400 },
  { s: "Review", at: 540 },
  { s: "Stage", at: 620 },
  { s: "Validate", at: 680 },
  { s: "Apply", at: 750 },
];

function StepTracker() {
  const f = useCurrentFrame();
  let active = 0;
  STEPS.forEach((s, i) => {
    if (f >= s.at) active = i;
  });
  const done = f >= 800;
  return (
    <div style={{ position: "absolute", left: 120, top: 196, width: 1690, display: "flex", alignItems: "center" }}>
      {STEPS.map((s, i) => {
        const isDone = i < active || done;
        const isActive = i === active && !done;
        return (
          <div key={s.s} style={{ display: "flex", alignItems: "center", flex: i < STEPS.length - 1 ? 1 : undefined }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 16px",
                borderRadius: 999,
                fontSize: 19,
                fontWeight: 600,
                whiteSpace: "nowrap",
                color: isActive ? T.bg0 : isDone ? T.mint : T.dim,
                background: isActive ? T.copper : isDone ? `${T.mint}14` : "rgba(255,255,255,0.03)",
                border: `1px solid ${isActive ? T.copper : isDone ? T.mint + "66" : T.border}`,
                boxShadow: isActive ? `0 0 24px ${T.copper}66` : undefined,
              }}
            >
              {isDone ? <Icon kind="check" size={16} color={T.mint} stroke={4} /> : null}
              {s.s}
            </div>
            {i < STEPS.length - 1 ? (
              <div style={{ flex: 1, height: 2, margin: "0 8px", background: isDone ? T.mint + "88" : T.border }} />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

const MSGS: { who: "you" | "atlas"; at: number; h: number; body: ReactNode }[] = [
  {
    who: "you",
    at: 10,
    h: 132,
    body: <Type text="SalesAmount should be net of line discounts. Please fix the mapping and the SQL in Customer Orders 360." at={16} cpf={1.6} />,
  },
  {
    who: "atlas",
    at: 105,
    h: 262,
    body: (
      <>
        Reading the current model at revision 42 and everything that depends on SalesAmount.
        {[
          ["read model snapshot", 125],
          ["read_mapping_context  FactSales", 150],
          ["read code  gold/fact_sales.sql", 175],
          ["read profile  order_items.discount_pct", 200],
        ].map(([t, a]) => (
          <div key={t as string} style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, fontFamily: FONT.mono, fontSize: 18, color: T.sub }}>
            <Check at={a as number} size={22} />
            {t}
          </div>
        ))}
      </>
    ),
  },
  {
    who: "atlas",
    at: 270,
    h: 132,
    body: <>Impact: the SalesAmount mapping and fact_sales.sql change. One check needs review. Locked records stay as they are.</>,
  },
  {
    who: "atlas",
    at: 410,
    h: 132,
    body: <>The change is ready in Atlas Local Workbench. Local validation passed with no errors. Please review it.</>,
  },
  { who: "you", at: 550, h: 90, body: <>I approve these changes for Stage.</> },
  {
    who: "atlas",
    at: 690,
    h: 186,
    body: <>Staged and validated on the server. Apply these validated changes to Customer Orders 360?</>,
  },
  {
    who: "atlas",
    at: 790,
    h: 132,
    body: <>Applied. Customer Orders 360 is now at revision 43, and your snapshot is refreshed.</>,
  },
];
const GAP = 20;
const VIEW_H = 600;

function msgTop(i: number) {
  let t = 0;
  for (let j = 0; j < i; j++) t += MSGS[j].h + GAP;
  return t;
}

function scrollAt(f: number) {
  const frames: number[] = [0];
  const values: number[] = [0];
  MSGS.forEach((m, i) => {
    const bottom = msgTop(i) + m.h;
    frames.push(m.at, m.at + 16);
    values.push(values[values.length - 1], Math.max(0, bottom - VIEW_H));
  });
  return interpolate(f, frames, values, clampOpts);
}

function Panel({ from, to, children }: { from: number; to: number; children: ReactNode }) {
  const f = useCurrentFrame();
  const o = Math.min(ramp(f, from, from + 14), 1 - ramp(f, to - 10, to));
  if (o <= 0) return null;
  return (
    <div style={{ position: "absolute", inset: 0, padding: 30, opacity: o, transform: `translateY(${(1 - ramp(f, from, from + 18)) * 16}px)` }}>
      {children}
    </div>
  );
}

const PanelHead = ({ children, color = T.copper }: { children: ReactNode; color?: string }) => (
  <div style={{ fontSize: 17, letterSpacing: 2.5, textTransform: "uppercase", color, fontWeight: 600, marginBottom: 18 }}>{children}</div>
);

function ImpactNode({ label, sub, tag, color, y, at, dim, x = 0 }: { label: string; sub: string; tag: string; color: string; y: number; at: number; dim?: boolean; x?: number }) {
  const f = useCurrentFrame();
  const p = ramp(f, at, at + 14);
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: dim ? 200 : 400,
        height: 82,
        borderRadius: 14,
        boxSizing: "border-box",
        padding: "12px 18px",
        border: `1.5px ${dim ? "dashed" : "solid"} ${dim ? T.border : color + "99"}`,
        background: dim ? "transparent" : `${color}16`,
        opacity: p * (dim ? 0.6 : 1),
        transform: `scale(${0.9 + 0.1 * p})`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontFamily: FONT.mono, fontSize: 19 }}>{label}</span>
        <Pill color={color} size={14}>{tag}</Pill>
      </div>
      <div style={{ fontSize: 16, color: T.sub, marginTop: 4 }}>{sub}</div>
    </div>
  );
}

function DiffLine({ sign, text }: { sign: "-" | "+"; text: string }) {
  const c = sign === "+" ? T.mint : T.red;
  return (
    <div style={{ display: "flex", fontFamily: FONT.mono, fontSize: 18, lineHeight: 1.7, background: `${c}14`, borderLeft: `3px solid ${c}`, padding: "0 12px", whiteSpace: "pre" }}>
      <span style={{ color: c, width: 22 }}>{sign}</span>
      <SqlLine text={text} />
    </div>
  );
}

const SUBMIT = [
  { t: "Reviewed in Atlas Local Workbench", at: 548 },
  { t: "You approved Stage", at: 570 },
  { t: "Tenant Lock held by you", at: 628 },
  { t: "Stage Runner verified the approved files", at: 648 },
  { t: "Server draft validated", at: 690 },
  { t: "You approved Apply", at: 770 },
];

export const PluginChange = () => {
  const f = useCurrentFrame();
  const CHAT_X = 120;
  const CHAT_Y = 260;
  const CONTENT_Y = CHAT_Y + 46 + 24;
  const scroll = scrollAt(f);
  const applyBtnY = CONTENT_Y + msgTop(5) - scrollAt(760) + 30 + 116;
  return (
    <Scene duration={len("PluginChange")}>
      <Title kicker="12 · Plugin in action" title="Ask for any change. Atlas makes it the governed way." size={60} y={70} />
      <StepTracker />
      <div style={{ position: "absolute", left: CHAT_X, top: CHAT_Y }}>
        <Window title="VS Code · Copilot Chat · Atlas" accent={T.violet} style={{ width: 960, height: 700 }}>
          <div style={{ position: "absolute", left: 24, right: 24, top: 24, height: VIEW_H + 10, overflow: "hidden" }}>
            <div style={{ transform: `translateY(${-scroll}px)`, display: "flex", flexDirection: "column", gap: GAP }}>
              {MSGS.map((m, i) => (
                <div key={i} style={{ height: m.h }}>
                  {f >= m.at ? (
                    <Bubble who={m.who} at={m.at}>
                      {m.body}
                      {i === 5 ? (
                        <div style={{ display: "flex", gap: 12, marginTop: 14 }}>
                          <span
                            style={{
                              padding: "8px 22px",
                              borderRadius: 10,
                              fontWeight: 700,
                              fontSize: 20,
                              color: T.bg0,
                              background: f >= 760 ? T.mint : T.copper,
                            }}
                          >
                            {f >= 760 ? "Applying…" : "Apply"}
                          </span>
                          <span style={{ padding: "8px 22px", borderRadius: 10, fontSize: 20, border: `1px solid ${T.border}`, color: T.sub }}>Cancel</span>
                        </div>
                      ) : null}
                    </Bubble>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </Window>
      </div>
      <Cursor
        path={[
          [700, 900, 900],
          [745, CHAT_X + 90, applyBtnY + 18],
          [790, CHAT_X + 140, applyBtnY + 60],
        ]}
        clicks={[755]}
      />
      {/* Right-hand live panel */}
      <div
        style={{
          position: "absolute",
          left: 1120,
          top: CHAT_Y,
          width: 690,
          height: 700,
          borderRadius: 18,
          background: `linear-gradient(160deg, ${T.panelHi}, ${T.panel})`,
          border: `1.5px solid ${T.border}`,
          overflow: "hidden",
          opacity: ramp(f, 4, 20),
        }}
      >
        <Panel from={0} to={105}>
          <PanelHead>Ask in plain language</PanelHead>
          {[
            "Add a loyalty tier to Customer",
            "Why does FactSales exclude voided orders?",
            "SalesAmount should be net of discounts",
            "Change Order Line to daily grain",
            "Describe the new CRM tables",
          ].map((q, i) => {
            const hit = i === 2 && f > 60;
            return (
              <div
                key={q}
                style={{
                  marginBottom: 14,
                  padding: "14px 18px",
                  borderRadius: 12,
                  fontSize: 21,
                  border: `1px solid ${hit ? T.copper : T.border}`,
                  background: hit ? `${T.copper}1E` : "rgba(255,255,255,0.03)",
                  color: hit ? T.text : T.sub,
                  opacity: ramp(f, 10 + i * 6, 24 + i * 6),
                }}
              >
                {q}
              </div>
            );
          })}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 20, opacity: ramp(f, 70, 86) }}>
            <span style={{ fontSize: 19, color: T.sub }}>Routed to skill</span>
            <Pill color={T.copper} size={19} solid>
              Model change
            </Pill>
          </div>
        </Panel>
        <Panel from={105} to={265}>
          <PanelHead color={T.mint}>Context gathered</PanelHead>
          {[
            ["Model snapshot", "Customer Orders 360 · revision 42", 125],
            ["Mapping", "FactSales.SalesAmount", 150],
            ["Code", "gold/fact_sales.sql", 175],
            ["Profile", "order_items.discount_pct · 38% null", 200],
            ["Lineage", "bronze_erp.order_items → FactSales", 222],
          ].map(([k, v, a]) => (
            <div key={k as string} style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 18, opacity: ramp(f, a as number, (a as number) + 12) }}>
              <Check at={a as number} size={30} />
              <div>
                <div style={{ fontSize: 16, letterSpacing: 1.5, textTransform: "uppercase", color: T.dim }}>{k}</div>
                <div style={{ fontFamily: FONT.mono, fontSize: 20 }}>{v}</div>
              </div>
            </div>
          ))}
          <div style={{ fontSize: 19, color: T.sub, marginTop: 8, opacity: ramp(f, 235, 250) }}>Read through governed tools. Nothing has changed yet.</div>
        </Panel>
        <Panel from={265} to={405}>
          <PanelHead>Impact analysis</PanelHead>
          <div style={{ position: "relative", height: 560 }}>
            <ImpactNode label="order_items.discount_pct" sub="Source column, already profiled" tag="Input" color={T.bronze} y={0} at={275} />
            <ImpactNode label="Mapping · SalesAmount" sub="Expression changes" tag="Definite" color={T.copper} y={130} at={295} />
            <ImpactNode label="gold/fact_sales.sql" sub="Regenerated from the mapping" tag="Definite" color={T.copper} y={260} at={315} />
            <ImpactNode label="Check · SalesAmount" sub="Validation definition" tag="Review" color={T.gold} y={390} at={335} />
            <ImpactNode label="DimCustomer" sub="Not affected" tag="Same" color={T.sub} y={130} x={430} at={350} dim />
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: 198,
                  top: 82 + i * 130,
                  width: 3,
                  height: 48 * ramp(f, 290 + i * 20, 302 + i * 20),
                  background: T.copper,
                  boxShadow: `0 0 10px ${T.copper}`,
                }}
              />
            ))}
          </div>
        </Panel>
        <Panel from={405} to={545}>
          <PanelHead>Proposed change</PanelHead>
          <div style={{ fontSize: 17, color: T.sub, marginBottom: 8 }}>Mapping · FactSales.SalesAmount</div>
          <div style={{ opacity: ramp(f, 415, 430) }}>
            <DiffLine sign="-" text="quantity * unit_price" />
            <DiffLine sign="+" text="quantity * unit_price" />
            <DiffLine sign="+" text="  * (1 - COALESCE(discount_pct, 0))" />
          </div>
          <div style={{ fontSize: 17, color: T.sub, margin: "22px 0 8px" }}>gold/fact_sales.sql</div>
          <div style={{ opacity: ramp(f, 440, 455) }}>
            <DiffLine sign="-" text="oi.quantity * oi.unit_price AS SalesAmount" />
            <DiffLine sign="+" text="oi.quantity * oi.unit_price" />
            <DiffLine sign="+" text="  * (1 - COALESCE(oi.discount_pct, 0))" />
            <DiffLine sign="+" text="  AS SalesAmount" />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 26, fontSize: 21, opacity: ramp(f, 480, 495) }}>
            <Check at={480} size={28} />
            Local validation: 0 errors · locked records untouched
          </div>
        </Panel>
        <Panel from={545} to={790}>
          <PanelHead color={T.mint}>Governed submission</PanelHead>
          {SUBMIT.map((s) => {
            const done = f >= s.at;
            const waiting = s.t === "You approved Apply" && f >= 700 && !done;
            return (
              <div key={s.t} style={{ display: "flex", alignItems: "center", gap: 16, height: 66, fontSize: 22, color: done ? T.text : T.dim }}>
                {done ? (
                  <Check at={s.at} size={32} />
                ) : (
                  <div style={{ width: 32, height: 32, borderRadius: 99, border: `2px ${waiting ? "solid" : "dashed"} ${waiting ? T.copper : T.dim}` }} />
                )}
                <span style={{ color: waiting ? T.copper : undefined }}>{waiting ? "Waiting for your Apply approval" : s.t}</span>
              </div>
            );
          })}
          <div style={{ marginTop: 16, fontSize: 18, color: T.sub, lineHeight: 1.45 }}>
            Stage sends the reviewed files to a server draft. Apply saves it. Each step needs your approval.
          </div>
        </Panel>
        <Panel from={790} to={1000}>
          <PanelHead color={T.mint}>Applied</PanelHead>
          <div style={{ display: "flex", alignItems: "baseline", gap: 20, marginTop: 10 }}>
            <span style={{ fontSize: 22, color: T.sub }}>Revision</span>
            <span style={{ fontFamily: FONT.head, fontWeight: 800, fontSize: 120, color: T.mint, lineHeight: 1 }}>
              <Counter from={42} to={43} at={800} dur={20} />
            </span>
          </div>
          {["Mapping updated", "fact_sales.sql updated", "Validation check reviewed"].map((t, i) => (
            <div key={t} style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 16, fontSize: 22, opacity: ramp(f, 820 + i * 10, 834 + i * 10) }}>
              <Check at={820 + i * 10} size={28} />
              {t}
            </div>
          ))}
          <div
            style={{
              marginTop: 34,
              padding: "16px 20px",
              borderRadius: 14,
              background: "#F4F0E7",
              color: "#173C35",
              display: "flex",
              alignItems: "center",
              gap: 12,
              fontSize: 20,
              fontWeight: 600,
              opacity: ramp(f, 860, 876),
              transform: `translateY(${(1 - ramp(f, 860, 880)) * 20}px)`,
            }}
          >
            <Icon kind="refresh" size={24} color="#173C35" />
            Atlas web app shows revision 43
          </div>
          <div
            style={{
              marginTop: 40,
              fontFamily: FONT.head,
              fontWeight: 700,
              fontSize: 40,
              lineHeight: 1.15,
              color: T.copper,
              opacity: ramp(f, 885, 905),
            }}
          >
            Full context in.
            <br />
            Governed change out.
          </div>
        </Panel>
      </div>
    </Scene>
  );
};
