import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import {
  AtlasMark,
  Flow,
  FONT,
  Glass,
  Icon,
  Orb,
  Pill,
  ramp,
  rand,
  Scene,
  T,
  Title,
  Type,
  clampOpts,
  useSpring,
} from "./kit";
import { len } from "./timeline";

/* ───────────────────────── 1. Open ───────────────────────── */

export const Open = () => {
  const f = useCurrentFrame();
  const markIn = useSpring(48, 14);
  const flash = interpolate(f, [44, 54, 90], [0, 1, 0], clampOpts);
  const letters = "ATLAS".split("");
  return (
    <Scene duration={len("Open")} fadeIn={1}>
      {/* converging data points */}
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        {Array.from({ length: 120 }).map((_, i) => {
          const ang = rand(i) * Math.PI * 2;
          const dist = 500 + rand(i + 99) * 700;
          const sx = 960 + Math.cos(ang) * dist;
          const sy = 430 + Math.sin(ang) * dist * 0.62;
          const delay = rand(i + 7) * 18;
          const p = ramp(f, delay, 52 + delay * 0.3, (t) => t * t * (3 - 2 * t));
          const x = sx + (960 - sx) * p;
          const y = sy + (430 - sy) * p;
          const colors = [T.mint, T.copper, T.gold, T.azure];
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r={2 + rand(i + 3) * 3}
              fill={colors[i % 4]}
              opacity={(1 - ramp(f, 46, 58)) * (0.4 + 0.6 * ramp(f, 0, 12))}
            />
          );
        })}
      </svg>
      <div
        style={{
          position: "absolute",
          left: 960 - 500,
          top: 430 - 500,
          width: 1000,
          height: 1000,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${T.copper}55 0%, transparent 55%)`,
          opacity: flash,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          width: 1920,
          top: 300,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          gap: 44,
        }}
      >
        <div style={{ transform: `scale(${0.6 + 0.4 * markIn})`, opacity: markIn }}>
          <AtlasMark size={210} draw={ramp(f, 48, 70)} />
        </div>
        <div style={{ display: "flex" }}>
          {letters.map((l, i) => {
            const p = ramp(f, 62 + i * 5, 84 + i * 5);
            return (
              <span
                key={i}
                style={{
                  fontFamily: FONT.head,
                  fontWeight: 700,
                  fontSize: 170,
                  letterSpacing: 34 + (1 - p) * 30,
                  color: T.text,
                  opacity: p,
                  filter: `blur(${(1 - p) * 10}px)`,
                }}
              >
                {l}
              </span>
            );
          })}
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          top: 610,
          left: 0,
          width: 1920,
          textAlign: "center",
          fontFamily: FONT.head,
          fontWeight: 600,
          fontSize: 56,
          color: T.text,
          opacity: ramp(f, 108, 132),
          transform: `translateY(${(1 - ramp(f, 108, 136)) * 20}px)`,
        }}
      >
        From raw sources to governed data models.
      </div>
      <div
        style={{
          position: "absolute",
          top: 700,
          left: 0,
          width: 1920,
          display: "flex",
          justifyContent: "center",
          gap: 18,
        }}
      >
        {["Metadata", "Lakehouse", "Modeling", "Mapping", "Code", "AI plugin", "Governance"].map(
          (w, i) => (
            <span
              key={w}
              style={{
                opacity: ramp(f, 138 + i * 5, 156 + i * 5),
                transform: `translateY(${(1 - ramp(f, 138 + i * 5, 160 + i * 5)) * 14}px)`,
              }}
            >
              <Pill color={i === 5 ? T.violet : i === 6 ? T.gold : T.mint} size={22}>
                {w}
              </Pill>
            </span>
          ),
        )}
      </div>
      <div
        style={{
          position: "absolute",
          left: 760,
          width: 400,
          top: 800,
          height: 2,
          background: `linear-gradient(90deg, transparent, ${T.copper}, transparent)`,
          transform: `scaleX(${ramp(f, 150, 200)})`,
        }}
      />
    </Scene>
  );
};

/* ───────────────────────── 2. Sources ───────────────────────── */

const SOURCES = [
  { name: "Relational databases", icon: "database", color: T.azure, eg: "crm.customers · erp.orders" },
  { name: "NoSQL stores", icon: "nosql", color: T.mint, eg: "web.sessions  { json }" },
  { name: "REST APIs", icon: "api", color: T.violet, eg: "GET /v2/products" },
  { name: "Files", icon: "file", color: T.gold, eg: "pricing.csv · returns.parquet" },
  { name: "Event streams", icon: "stream", color: T.copper, eg: "clickstream topic" },
  { name: "SaaS applications", icon: "cloud", color: T.silver, eg: "support tickets" },
];

export const Sources = () => {
  const f = useCurrentFrame();
  return (
    <Scene duration={len("Sources")}>
      <Title
        kicker="01 · Sources"
        title="Your data lives everywhere."
        sub="Relational databases, NoSQL stores, APIs, files and event streams, each with its own shape."
      />
      {SOURCES.map((s, i) => {
        const col = i % 3;
        const row = Math.floor(i / 3);
        const x = 180 + col * 540;
        const y = 410 + row * 220;
        const bob = Math.sin((f + i * 20) / 28) * 5;
        return (
          <Glass key={s.name} at={30 + i * 7} x={x} y={y + bob} w={500} h={180} glow={s.color}>
            <div style={{ display: "flex", gap: 22, alignItems: "center" }}>
              <Orb kind={s.icon} color={s.color} size={84} />
              <div>
                <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 36 }}>{s.name}</div>
                <div style={{ fontFamily: FONT.mono, fontSize: 19, color: T.sub, marginTop: 8 }}>{s.eg}</div>
              </div>
            </div>
          </Glass>
        );
      })}
      <div
        style={{
          position: "absolute",
          top: 880,
          width: 1920,
          textAlign: "center",
          fontFamily: FONT.head,
          fontSize: 44,
          fontWeight: 600,
          color: T.copper,
          opacity: ramp(f, 170, 195),
          transform: `translateY(${(1 - ramp(f, 170, 198)) * 16}px)`,
        }}
      >
        How do you bring it together, consistently?
      </div>
    </Scene>
  );
};

/* ───────────────────────── 3. Metadata ───────────────────────── */

const META_ROWS = [
  { kind: "Tenant", color: T.copper, icon: "shield", items: ["Retail"] },
  { kind: "Systems", color: T.azure, icon: "server", items: ["CRM", "ERP", "Web Store"] },
  { kind: "Connections", color: T.violet, icon: "plug", items: ["crm_sqlserver", "erp_oracle", "web_api"] },
  { kind: "Objects", color: T.mint, icon: "table", items: ["customers", "orders", "order_items", "products"] },
  {
    kind: "Attributes",
    color: T.gold,
    icon: "tag",
    items: ["customer_id BIGINT", "email STRING", "order_date STRING", "quantity INT", "unit_price DECIMAL"],
  },
];

export const Metadata = () => {
  const f = useCurrentFrame();
  const srcY = [400, 500, 600, 700, 800];
  const srcs = ["CRM database", "ERP database", "Web Store API", "Pricing files", "Clickstream"];
  const srcIcons = ["database", "database", "api", "file", "stream"];
  return (
    <Scene duration={len("Metadata")}>
      <Title
        kicker="02 · Metadata in Atlas"
        title="Describe every source once, in Atlas."
        sub="Atlas holds the metadata the platform runs on: what exists, where it lives, and how it is ingested."
      />
      {srcs.map((s, i) => (
        <Glass key={s} at={20 + i * 5} x={110} y={srcY[i] - 34} w={330} h={68} pad={14} radius={14} from="left">
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <Icon kind={srcIcons[i]} size={34} color={T.sub} />
            <span style={{ fontSize: 22, fontWeight: 500 }}>{s}</span>
          </div>
        </Glass>
      ))}
      {srcs.map((s, i) => (
        <Flow
          key={s}
          a={{ x: 440, y: srcY[i] }}
          b={{ x: 560, y: 610 }}
          at={50 + i * 4}
          dur={22}
          color={T.copper}
          packets={1}
          speed={40}
          width={2}
        />
      ))}
      <Glass at={36} x={560} y={330} w={850} h={600} glow={T.copper} pad={0}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 14,
            padding: "18px 26px",
            borderBottom: `1px solid ${T.border}`,
          }}
        >
          <AtlasMark size={34} />
          <span style={{ fontFamily: FONT.head, fontSize: 30, fontWeight: 700 }}>Atlas · Metadata</span>
          <span style={{ marginLeft: "auto" }}>
            <Pill color={T.mint} size={17}>
              Governed · versioned · audited
            </Pill>
          </span>
        </div>
        <div style={{ padding: "16px 26px" }}>
          {META_ROWS.map((r, i) => {
            const at = 70 + i * 30;
            const p = ramp(f, at, at + 18);
            return (
              <div
                key={r.kind}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 16,
                  padding: "14px 0",
                  paddingLeft: i * 22,
                  borderBottom: i < META_ROWS.length - 1 ? `1px dashed ${T.border}` : undefined,
                  opacity: p,
                  transform: `translateX(${(1 - p) * -20}px)`,
                }}
              >
                <Orb kind={r.icon} color={r.color} size={44} />
                <div style={{ width: 150, flexShrink: 0, paddingTop: 10 }}>
                  <span style={{ fontSize: 20, fontWeight: 600, color: r.color, letterSpacing: 1 }}>{r.kind}</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, paddingTop: 4 }}>
                  {r.items.map((it, j) => (
                    <span
                      key={it}
                      style={{
                        fontFamily: FONT.mono,
                        fontSize: 18,
                        padding: "6px 12px",
                        borderRadius: 8,
                        background: "rgba(255,255,255,0.06)",
                        border: `1px solid ${T.border}`,
                        opacity: ramp(f, at + 8 + j * 4, at + 20 + j * 4),
                      }}
                    >
                      {it}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Glass>
      <div style={{ position: "absolute", left: 1450, top: 330, width: 360 }}>
        <div
          style={{
            fontSize: 20,
            fontWeight: 600,
            letterSpacing: 3,
            textTransform: "uppercase",
            color: T.sub,
            opacity: ramp(f, 200, 215),
          }}
        >
          Ingestion rules
        </div>
      </div>
      {[
        { t: "Copy", d: "crm.customers → Bronze", icon: "link", c: T.azure },
        { t: "Copy Group", d: "nightly_crm · CRM objects", icon: "layers", c: T.violet },
        { t: "Process", d: "Execution order and settings", icon: "workflow", c: T.mint },
      ].map((r, i) => (
        <Glass key={r.t} at={215 + i * 12} x={1450} y={380 + i * 130} w={360} h={112} pad={18} glow={r.c} from="right">
          <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
            <Orb kind={r.icon} color={r.c} size={52} />
            <div>
              <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 28 }}>{r.t}</div>
              <div style={{ fontSize: 18, color: T.sub }}>{r.d}</div>
            </div>
          </div>
        </Glass>
      ))}
      <Glass at={270} x={1450} y={780} w={360} h={130} pad={18} from="right">
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Icon kind="lock" size={30} color={T.gold} />
          <span style={{ fontSize: 20, lineHeight: 1.35, color: T.sub }}>
            Connections are registered. <span style={{ color: T.gold }}>Secrets are never stored</span> in metadata.
          </span>
        </div>
      </Glass>
    </Scene>
  );
};

/* ───────────────────────── 4. Bronze ───────────────────────── */

function Brand({ src, size = 64 }: { src: string; size?: number }) {
  return <Img src={staticFile(src)} style={{ width: size, height: size, objectFit: "contain" }} />;
}

export function LakeLayer({
  name,
  color,
  x,
  y,
  w,
  fill,
  tables,
  at,
  active,
  h = 150,
}: {
  name: string;
  color: string;
  x: number;
  y: number;
  w: number;
  fill: number;
  tables: string[];
  at: number;
  active: boolean;
  h?: number;
}) {
  const f = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: w,
        height: h,
        borderRadius: 18,
        border: `1.5px solid ${active ? color : T.border}`,
        background: `linear-gradient(160deg, ${color}${active ? "26" : "0C"}, rgba(255,255,255,0.02))`,
        boxShadow: active ? `0 0 50px ${color}40` : undefined,
        overflow: "hidden",
        opacity: ramp(f, at, at + 16),
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          bottom: 0,
          height: 8,
          width: `${fill * 100}%`,
          background: color,
          boxShadow: `0 0 16px ${color}`,
        }}
      />
      <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ width: 14, height: 14, borderRadius: 4, background: color }} />
        <span style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 30, color: active ? T.text : T.dim }}>
          {name}
        </span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 7, padding: "0 20px" }}>
        {tables.map((t, i) => (
          <span
            key={t}
            style={{
              fontFamily: FONT.mono,
              fontSize: 15,
              padding: "3px 9px",
              borderRadius: 6,
              color: T.text,
              background: `${color}22`,
              border: `1px solid ${color}55`,
              opacity: fill > (i + 0.5) / tables.length ? 1 : 0,
            }}
          >
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

export const Bronze = () => {
  const f = useCurrentFrame();
  const srcs = [
    { n: "CRM", i: "database", y: 520 },
    { n: "ERP", i: "database", y: 610 },
    { n: "Web Store", i: "api", y: 700 },
    { n: "Files", i: "file", y: 790 },
  ];
  const bronzeFill = ramp(f, 230, 400, (t) => t);
  return (
    <Scene duration={len("Bronze")}>
      <Title
        kicker="03 · GDS Framework"
        title="The framework reads that metadata and loads Bronze."
        sub="Azure Data Factory triggers the pipelines. Databricks notebooks use the metadata to ingest each source into the lakehouse."
        size={66}
      />
      {/* Atlas metadata */}
      <Glass at={20} x={640} y={360} w={460} h={104} pad={18} glow={T.copper}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <AtlasMark size={52} />
          <div>
            <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 30 }}>Atlas metadata</div>
            <div style={{ fontSize: 18, color: T.sub }}>Systems · objects · copy groups</div>
          </div>
        </div>
      </Glass>
      {srcs.map((s, i) => (
        <Glass key={s.n} at={30 + i * 5} x={110} y={s.y - 34} w={250} h={68} pad={14} radius={14} from="left">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Icon kind={s.i} size={30} color={T.sub} />
            <span style={{ fontSize: 22, fontWeight: 500 }}>{s.n}</span>
          </div>
        </Glass>
      ))}
      {/* ADF */}
      <Glass at={60} x={500} y={560} w={330} h={240} glow={T.azure} pad={22}>
        <Brand src="brands/azure-data-factory.svg" size={64} />
        <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 30, marginTop: 12 }}>Data Factory</div>
        <div style={{ fontSize: 19, color: T.sub, marginTop: 4, lineHeight: 1.35 }}>Triggers and pipelines copy each source</div>
      </Glass>
      {/* Databricks */}
      <Glass at={80} x={910} y={560} w={330} h={240} glow={T.lava} pad={22}>
        <Brand src="brands/databricks.svg" size={64} />
        <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 30, marginTop: 12 }}>Databricks</div>
        <div style={{ fontSize: 19, color: T.sub, marginTop: 4, lineHeight: 1.35 }}>Notebooks ingest using the metadata</div>
      </Glass>
      {/* metadata drives both */}
      <Flow a={{ x: 760, y: 464 }} b={{ x: 665, y: 560 }} at={100} vertical dashed color={T.copper} width={2.5} />
      <Flow a={{ x: 980, y: 464 }} b={{ x: 1075, y: 560 }} at={110} vertical dashed color={T.copper} width={2.5} />
      <div
        style={{
          position: "absolute",
          left: 815,
          top: 486,
          fontFamily: FONT.mono,
          fontSize: 16,
          color: T.copper,
          opacity: ramp(f, 120, 140),
        }}
      >
        metadata
      </div>
      {/* data flow */}
      {srcs.map((s, i) => (
        <Flow key={s.n} a={{ x: 360, y: s.y }} b={{ x: 500, y: 680 }} at={140 + i * 4} color={T.azure} packets={2} speed={70} width={2} />
      ))}
      <Flow a={{ x: 830, y: 680 }} b={{ x: 910, y: 680 }} at={170} color={T.azure} packets={2} speed={60} />
      <Flow a={{ x: 1240, y: 680 }} b={{ x: 1380, y: 830 }} at={190} color={T.bronze} packets={3} speed={70} width={3} />
      {/* trigger */}
      <Glass at={150} x={500} y={830} w={740} h={76} pad={16} radius={14}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <Icon kind="play" size={26} color={T.azure} />
          <span style={{ fontFamily: FONT.mono, fontSize: 20 }}>
            <Type text="trigger · tenant=Retail · systems=CRM,ERP,Web" at={158} cpf={2} />
          </span>
        </div>
      </Glass>
      {/* Lakehouse */}
      <div
        style={{
          position: "absolute",
          left: 1380,
          top: 330,
          width: 430,
          fontSize: 20,
          letterSpacing: 3,
          fontWeight: 600,
          textTransform: "uppercase",
          color: T.sub,
          opacity: ramp(f, 40, 60),
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <Brand src="brands/databricks.svg" size={24} /> Lakehouse
      </div>
      <LakeLayer name="Gold" color={T.gold} x={1380} y={380} w={430} fill={0} tables={[]} at={50} active={false} />
      <LakeLayer name="Silver" color={T.silver} x={1380} y={550} w={430} fill={0} tables={[]} at={56} active={false} />
      <LakeLayer
        name="Bronze"
        color={T.bronze}
        x={1380}
        y={720}
        w={430}
        fill={bronzeFill}
        tables={["customers", "orders", "order_items", "products", "sessions"]}
        at={62}
        active={f > 200}
      />
      <div
        style={{
          position: "absolute",
          left: 1400,
          top: 455,
          width: 400,
          fontSize: 18,
          color: T.dim,
          opacity: ramp(f, 300, 330),
        }}
      >
        Modeled by Atlas next →
      </div>
    </Scene>
  );
};
