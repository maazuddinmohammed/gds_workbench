import { Sequence, useCurrentFrame } from "remotion";
import {
  AtlasMark,
  Check,
  Counter,
  Cursor,
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
  Window,
} from "./kit";
import { len } from "./timeline";

/* ───────────────────────── Shared entity card ───────────────────────── */

export const ROW_H = 38;
export const HEAD_H = 64;
export const rowY = (y: number, i: number) => y + HEAD_H + i * ROW_H + ROW_H / 2 + 6;

export type Row = { n: string; tag?: string; tagColor?: string; hl?: boolean; dim?: boolean };

export function EntityCard({
  name,
  schema,
  x,
  y,
  w = 400,
  rows,
  at,
  color = T.mint,
  icon = "table",
  glow,
}: {
  name: string;
  schema?: string;
  x: number;
  y: number;
  w?: number;
  rows: Row[];
  at: number;
  color?: string;
  icon?: string;
  glow?: boolean;
}) {
  const f = useCurrentFrame();
  return (
    <Glass at={at} x={x} y={y} w={w} h={HEAD_H + rows.length * ROW_H + 18} pad={0} glow={glow ? color : undefined} from="scale" radius={16}>
      <div
        style={{
          height: HEAD_H,
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "0 18px",
          borderBottom: `1px solid ${T.border}`,
          background: `linear-gradient(90deg, ${color}26, transparent)`,
          borderRadius: "16px 16px 0 0",
        }}
      >
        <Icon kind={icon} size={26} color={color} />
        <span style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 28 }}>{name}</span>
        {schema ? (
          <span style={{ marginLeft: "auto", fontFamily: FONT.mono, fontSize: 15, color: T.sub }}>{schema}</span>
        ) : null}
      </div>
      <div style={{ padding: "6px 0" }}>
        {rows.map((r, i) => {
          const p = ramp(f, at + 8 + i * 3, at + 20 + i * 3);
          return (
            <div
              key={r.n}
              style={{
                height: ROW_H,
                display: "flex",
                alignItems: "center",
                padding: "0 18px",
                gap: 10,
                fontFamily: FONT.mono,
                fontSize: 19,
                color: r.dim ? T.dim : T.text,
                background: r.hl ? `${r.tagColor ?? T.copper}1F` : undefined,
                opacity: p,
              }}
            >
              <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden" }}>{r.n}</span>
              {r.tag ? (
                <span
                  style={{
                    fontFamily: FONT.body,
                    fontSize: 13,
                    fontWeight: 700,
                    letterSpacing: 0.8,
                    padding: "2px 7px",
                    borderRadius: 6,
                    color: r.tagColor ?? T.gold,
                    border: `1px solid ${r.tagColor ?? T.gold}77`,
                    background: `${r.tagColor ?? T.gold}18`,
                  }}
                >
                  {r.tag}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
    </Glass>
  );
}

/* ───────────────────────── 5. Scope ───────────────────────── */

const SCOPE_ROWS = [
  { o: "bronze_crm.customers", s: "CRM", pick: 120 },
  { o: "bronze_erp.orders", s: "ERP", pick: 145 },
  { o: "bronze_erp.order_items", s: "ERP", pick: 170 },
  { o: "bronze_erp.products", s: "ERP", pick: 195 },
  { o: "bronze_web.sessions", s: "Web Store", pick: -1 },
];

export const Scope = () => {
  const f = useCurrentFrame();
  const WX = 120;
  const WY = 320;
  const rowTop = (i: number) => WY + 46 + 268 + i * 62;
  const picked = SCOPE_ROWS.filter((r) => r.pick > 0 && f >= r.pick + 4).length;
  return (
    <Scene duration={len("Scope")}>
      <Title
        kicker="04 · Model scope"
        title="Create a model. Choose its scope."
        sub="Pick the Bronze objects the model may use. One model can span several source systems."
      />
      <div style={{ position: "absolute", left: WX, top: WY, width: 1000, height: 640 }}>
        <Window title="Atlas · New model" style={{ width: 1000, height: 640 }}>
          <div style={{ padding: "22px 30px" }}>
            <div style={{ fontSize: 17, letterSpacing: 2, textTransform: "uppercase", color: T.sub }}>Model name</div>
            <div
              style={{
                marginTop: 10,
                height: 60,
                borderRadius: 12,
                border: `1.5px solid ${T.copper}88`,
                background: "rgba(255,255,255,0.04)",
                display: "flex",
                alignItems: "center",
                padding: "0 18px",
                fontSize: 30,
                fontFamily: FONT.head,
                fontWeight: 600,
              }}
            >
              <Type text="Customer Orders 360" at={20} cpf={0.6} />
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 18, opacity: ramp(f, 62, 80) }}>
              <Pill color={T.silver} size={18}>Silver schema · silver_retail</Pill>
              <Pill color={T.gold} size={18}>Gold schema · gold_retail</Pill>
              <Pill color={T.mint} size={18}>Tenant · Retail</Pill>
            </div>
            <div
              style={{
                marginTop: 30,
                fontSize: 17,
                letterSpacing: 2,
                textTransform: "uppercase",
                color: T.sub,
                opacity: ramp(f, 80, 95),
              }}
            >
              Model input scope
            </div>
          </div>
        </Window>
      </div>
      {SCOPE_ROWS.map((r, i) => {
        const on = r.pick > 0 && f >= r.pick + 4;
        const p = ramp(f, 85 + i * 4, 100 + i * 4);
        return (
          <div
            key={r.o}
            style={{
              position: "absolute",
              left: WX + 30,
              top: rowTop(i),
              width: 940,
              height: 52,
              borderRadius: 12,
              display: "flex",
              alignItems: "center",
              gap: 16,
              padding: "0 16px",
              boxSizing: "border-box",
              background: on ? `${T.mint}14` : "rgba(255,255,255,0.025)",
              border: `1px solid ${on ? T.mint + "66" : T.border}`,
              opacity: p,
            }}
          >
            <div
              style={{
                width: 26,
                height: 26,
                borderRadius: 7,
                border: `2px solid ${on ? T.mint : T.dim}`,
                background: on ? T.mint : "transparent",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {on ? <Icon kind="check" size={20} color={T.bg0} stroke={4} /> : null}
            </div>
            <span style={{ fontFamily: FONT.mono, fontSize: 21, flex: 1 }}>{r.o}</span>
            <Pill color={T.azure} size={15}>{r.s}</Pill>
            <Pill color={T.bronze} size={15}>Bronze</Pill>
          </div>
        );
      })}
      <Cursor
        path={[
          [96, 700, 980],
          [116, WX + 60, rowTop(0) + 24],
          [141, WX + 60, rowTop(1) + 24],
          [166, WX + 60, rowTop(2) + 24],
          [191, WX + 60, rowTop(3) + 24],
          [225, WX + 420, rowTop(4) + 60],
        ]}
        clicks={[120, 145, 170, 195]}
      />
      <Glass at={40} x={1180} y={320} w={630} h={640} glow={T.copper} pad={34}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <AtlasMark size={46} />
          <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 38 }}>Customer Orders 360</div>
        </div>
        <div style={{ display: "flex", gap: 20, marginTop: 34 }}>
          {[
            { k: "Objects", v: <>{picked}</>, c: T.mint },
            { k: "Systems", v: <>{Math.min(2, picked > 0 ? (picked > 1 ? 2 : 1) : 0)}</>, c: T.azure },
            { k: "Zone", v: <>Bronze</>, c: T.bronze },
          ].map((m) => (
            <div
              key={m.k}
              style={{
                flex: 1,
                borderRadius: 14,
                border: `1px solid ${T.border}`,
                padding: "16px 18px",
                background: "rgba(255,255,255,0.03)",
              }}
            >
              <div style={{ fontFamily: FONT.head, fontWeight: 800, fontSize: 52, color: m.c }}>{m.v}</div>
              <div style={{ fontSize: 18, color: T.sub, letterSpacing: 1.5, textTransform: "uppercase" }}>{m.k}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 34, fontSize: 24, lineHeight: 1.45, color: T.sub, opacity: ramp(f, 215, 240) }}>
          The scope is saved with the model. Every workflow that follows, from profiling to code, works inside it.
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 26, opacity: ramp(f, 235, 255) }}>
          <Pill color={T.gold} size={17}>Gold history · SCD Type 2</Pill>
          <Pill color={T.mint} size={17}>Audit columns · on</Pill>
        </div>
      </Glass>
    </Scene>
  );
};

/* ───────────────────────── 6. Evidence: profile · enrich · analyze ───────────────────────── */

function StepTabs({ active }: { active: number }) {
  const steps = ["Profile", "Enrich", "Analyze"];
  return (
    <div style={{ position: "absolute", right: 120, top: 78, display: "flex", gap: 10 }}>
      {steps.map((s, i) => (
        <div
          key={s}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px 20px",
            borderRadius: 999,
            fontSize: 21,
            fontWeight: 600,
            color: i === active ? T.bg0 : i < active ? T.mint : T.dim,
            background: i === active ? T.copper : "rgba(255,255,255,0.04)",
            border: `1px solid ${i === active ? T.copper : i < active ? T.mint + "66" : T.border}`,
          }}
        >
          {i < active ? <Icon kind="check" size={18} color={T.mint} stroke={4} /> : <span>{i + 1}</span>}
          {s}
        </div>
      ))}
    </div>
  );
}

const PROFILE = [
  { c: "order_line_id", t: "BIGINT", nulls: "0%", distinct: "6.1M", range: "unique", seed: 1 },
  { c: "order_id", t: "BIGINT", nulls: "0%", distinct: "2.4M", range: "1 – 2.4M", seed: 2 },
  { c: "sku", t: "STRING", nulls: "0%", distinct: "8,214", range: "A-0001 …", seed: 3 },
  { c: "quantity", t: "INT", nulls: "0%", distinct: "48", range: "1 – 48", seed: 4 },
  { c: "unit_price", t: "DECIMAL", nulls: "0%", distinct: "3,920", range: "0.99 – 1,899", seed: 5 },
  { c: "discount_pct", t: "DECIMAL", nulls: "38%", distinct: "21", range: "0 – 0.35", seed: 6, warn: true },
];

const ProfileBeat = () => {
  const f = useCurrentFrame();
  return (
    <>
      <Title
        kicker="05 · Evidence"
        title="Profile: measure what is really there."
        sub="Deterministic statistics for each selected column, over all rows or a batch, saved with provenance."
      />
      <Glass at={10} x={120} y={330} w={1180} h={630} pad={0}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "18px 26px", borderBottom: `1px solid ${T.border}` }}>
          <Icon kind="table" size={28} color={T.bronze} />
          <span style={{ fontFamily: FONT.mono, fontSize: 24 }}>bronze_erp.order_items</span>
          <span style={{ marginLeft: "auto", display: "flex", gap: 10 }}>
            <Pill color={T.mint} size={16}>All rows</Pill>
            <Pill color={T.sub} size={16}>
              <Counter from={0} to={6.1} at={20} dur={60} decimals={1} suffix="M rows" />
            </Pill>
          </span>
        </div>
        <div style={{ display: "flex", padding: "12px 26px", fontSize: 15, letterSpacing: 2, textTransform: "uppercase", color: T.dim }}>
          <span style={{ width: 250 }}>Column</span>
          <span style={{ width: 130 }}>Type</span>
          <span style={{ width: 290 }}>Distribution</span>
          <span style={{ width: 120 }}>Nulls</span>
          <span style={{ width: 130 }}>Distinct</span>
          <span>Range</span>
        </div>
        {PROFILE.map((r, i) => {
          const at = 30 + i * 10;
          const p = ramp(f, at, at + 14);
          return (
            <div
              key={r.c}
              style={{
                display: "flex",
                alignItems: "center",
                height: 72,
                padding: "0 26px",
                borderTop: `1px solid ${T.border}`,
                opacity: p,
                background: r.warn && f > 200 ? `${T.copper}14` : undefined,
              }}
            >
              <span style={{ width: 250, fontFamily: FONT.mono, fontSize: 21 }}>{r.c}</span>
              <span style={{ width: 130, fontFamily: FONT.mono, fontSize: 17, color: T.sub }}>{r.t}</span>
              <span style={{ width: 290, display: "flex", alignItems: "flex-end", gap: 4, height: 44 }}>
                {Array.from({ length: 16 }).map((_, j) => {
                  const hgt = 8 + rand(r.seed * 40 + j) * 36;
                  const g = ramp(f, at + 6 + j * 1.5, at + 26 + j * 1.5);
                  return (
                    <span
                      key={j}
                      style={{
                        width: 13,
                        height: hgt * g,
                        borderRadius: 3,
                        background: r.warn ? T.copper : T.mint,
                        opacity: 0.85,
                      }}
                    />
                  );
                })}
              </span>
              <span
                style={{
                  width: 120,
                  fontFamily: FONT.mono,
                  fontSize: 21,
                  color: r.warn ? T.copper : T.text,
                  fontWeight: r.warn ? 700 : 400,
                }}
              >
                {r.nulls}
              </span>
              <span style={{ width: 130, fontFamily: FONT.mono, fontSize: 21 }}>{r.distinct}</span>
              <span style={{ fontFamily: FONT.mono, fontSize: 18, color: T.sub }}>{r.range}</span>
            </div>
          );
        })}
      </Glass>
      {[
        { i: "chart", t: "Completeness", d: "Null rates for every column", c: T.mint },
        { i: "key", t: "Key candidates", d: "Distinct counts and uniqueness", c: T.gold },
        { i: "search", t: "Shapes and ranges", d: "Min, max and value patterns", c: T.azure },
      ].map((b, i) => (
        <Glass key={b.t} at={60 + i * 14} x={1340} y={330 + i * 150} w={470} h={130} pad={22} from="right">
          <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
            <Orb kind={b.i} color={b.c} size={64} />
            <div>
              <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 30 }}>{b.t}</div>
              <div style={{ fontSize: 20, color: T.sub }}>{b.d}</div>
            </div>
          </div>
        </Glass>
      ))}
      <Glass at={190} x={1340} y={790} w={470} h={170} pad={22} glow={T.copper} from="right">
        <div style={{ fontSize: 17, letterSpacing: 2, textTransform: "uppercase", color: T.copper, fontWeight: 600 }}>
          Worth knowing
        </div>
        <div style={{ fontSize: 24, lineHeight: 1.4, marginTop: 8 }}>
          <span style={{ fontFamily: FONT.mono }}>discount_pct</span> is empty on 38% of order lines.
        </div>
      </Glass>
    </>
  );
};

const ENRICH = [
  { a: "customers.customer_id", d: "Unique identifier for a customer", phys: "BIGINT", inf: "BIGINT", tags: [["Primary key", T.gold]] },
  { a: "customers.email", d: "Customer contact email address", phys: "STRING", inf: "STRING", tags: [["PII", T.red]] },
  { a: "orders.order_date", d: "Date the order was placed", phys: "STRING", inf: "DATE", tags: [["Type inferred", T.azure]] },
  { a: "orders.status", d: "Order status: S shipped, C cancelled, R returned, X void", phys: "STRING", inf: "STRING", tags: [["Coded values", T.violet]] },
  { a: "order_items.discount_pct", d: "Line discount as a fraction of the price", phys: "DECIMAL", inf: "DECIMAL(5,4)", tags: [["Nullable", T.copper]] },
] as const;

const EnrichBeat = () => {
  const f = useCurrentFrame();
  return (
    <>
      <Title
        kicker="05 · Evidence"
        title="Enrich: add meaning, types and keys."
        sub="Descriptions, inferred types, keys, nullability and PII findings, owned by the model and editable by people."
      />
      <Glass at={6} x={120} y={330} w={1690} h={630} pad={0}>
        <div style={{ display: "flex", padding: "18px 28px", fontSize: 15, letterSpacing: 2, textTransform: "uppercase", color: T.dim, borderBottom: `1px solid ${T.border}` }}>
          <span style={{ width: 380 }}>Attribute</span>
          <span style={{ width: 640 }}>Description</span>
          <span style={{ width: 330 }}>Physical → inferred type</span>
          <span>Findings</span>
        </div>
        {ENRICH.map((r, i) => {
          const at = 18 + i * 26;
          return (
            <div
              key={r.a}
              style={{
                display: "flex",
                alignItems: "center",
                height: 108,
                padding: "0 28px",
                borderBottom: i < ENRICH.length - 1 ? `1px solid ${T.border}` : undefined,
                opacity: ramp(f, at - 10, at),
              }}
            >
              <span style={{ width: 380, fontFamily: FONT.mono, fontSize: 21 }}>{r.a}</span>
              <span style={{ width: 640, fontSize: 23, color: T.text, paddingRight: 30 }}>
                <Type text={r.d} at={at} cpf={1.8} caret={false} />
              </span>
              <span style={{ width: 330, fontFamily: FONT.mono, fontSize: 19, display: "flex", gap: 10, alignItems: "center" }}>
                <span style={{ color: T.dim }}>{r.phys}</span>
                <span style={{ color: T.dim }}>→</span>
                <span
                  style={{
                    color: r.phys !== r.inf ? T.azure : T.text,
                    opacity: ramp(f, at + 20, at + 30),
                    fontWeight: r.phys !== r.inf ? 700 : 400,
                  }}
                >
                  {r.inf}
                </span>
              </span>
              <span style={{ display: "flex", gap: 8, opacity: ramp(f, at + 26, at + 36), transform: `scale(${0.8 + 0.2 * ramp(f, at + 26, at + 36)})` }}>
                {r.tags.map(([t, c]) => (
                  <Pill key={t} color={c} size={18}>
                    {t}
                  </Pill>
                ))}
              </span>
            </div>
          );
        })}
      </Glass>
      <div
        style={{
          position: "absolute",
          right: 120,
          top: 268,
          fontSize: 20,
          color: T.sub,
          display: "flex",
          alignItems: "center",
          gap: 10,
          opacity: ramp(f, 170, 190),
        }}
      >
        <Icon kind="lock" size={22} color={T.mint} /> Human edits and locked values are preserved on every rerun.
      </div>
    </>
  );
};

type Node = { name: string; x: number; y: number; cols: string[] };
const NODES: Record<string, Node> = {
  customers: { name: "customers", x: 130, y: 350, cols: ["customer_id", "email", "full_name", "created_at"] },
  orders: { name: "orders", x: 690, y: 350, cols: ["order_id", "cust_id", "order_date", "status"] },
  items: { name: "order_items", x: 1250, y: 350, cols: ["order_line_id", "order_id", "sku", "quantity", "unit_price", "discount_pct"] },
  products: { name: "products", x: 690, y: 690, cols: ["product_code", "name", "category"] },
};
const NODE_W = 340;

function TableNode({ n, at, hl = [] }: { n: Node; at: number; hl?: number[] }) {
  return (
    <EntityCard
      name={n.name}
      x={n.x}
      y={n.y}
      w={NODE_W}
      at={at}
      color={T.bronze}
      rows={n.cols.map((c, i) => ({ n: c, hl: hl.includes(i), tagColor: T.mint }))}
    />
  );
}

const AnalyzeBeat = () => {
  const f = useCurrentFrame();
  const { customers, orders, items, products } = NODES;
  const rels = [
    { a: { x: orders.x, y: rowY(orders.y, 1) }, b: { x: customers.x + NODE_W, y: rowY(customers.y, 0) }, at: 70, label: "0.98 · many-to-one" },
    { a: { x: items.x, y: rowY(items.y, 1) }, b: { x: orders.x + NODE_W, y: rowY(orders.y, 0) }, at: 110, label: "0.99 · many-to-one" },
    { a: { x: items.x, y: rowY(items.y, 2) }, b: { x: products.x + NODE_W, y: rowY(products.y, 0) }, at: 150, label: "0.91 · many-to-one" },
  ];
  return (
    <>
      <Title
        kicker="05 · Evidence"
        title="Analyze: discover how the tables connect."
        sub="Relationships inferred from real columns, each with its reasoning and a confidence score."
      />
      <TableNode n={customers} at={6} hl={f > 70 ? [0] : []} />
      <TableNode n={orders} at={12} hl={f > 70 ? (f > 110 ? [0, 1] : [1]) : []} />
      <TableNode n={items} at={18} hl={f > 110 ? (f > 150 ? [1, 2] : [1]) : []} />
      <TableNode n={products} at={24} hl={f > 150 ? [0] : []} />
      {rels.map((r) => (
        <Flow key={r.label} a={r.a} b={r.b} at={r.at} dur={26} color={T.mint} width={3} label={r.label} packets={1} speed={60} />
      ))}
      <Glass at={190} x={130} y={640} w={500} h={310} pad={26} glow={T.mint} from="left">
        <div style={{ fontSize: 17, letterSpacing: 2, textTransform: "uppercase", color: T.mint, fontWeight: 600 }}>Reasoning</div>
        <div style={{ fontFamily: FONT.mono, fontSize: 21, marginTop: 10 }}>orders.cust_id → customers.customer_id</div>
        {[
          "99.7% of cust_id values match a customer_id",
          "Same BIGINT type, aligned names",
          "Many orders per customer",
        ].map((t, i) => (
          <div key={t} style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 14, fontSize: 21, color: T.sub }}>
            <Check at={205 + i * 14} size={26} />
            <span style={{ opacity: ramp(f, 205 + i * 14, 220 + i * 14) }}>{t}</span>
          </div>
        ))}
      </Glass>
      <Glass at={230} x={1250} y={680} w={560} h={150} pad={24} from="right">
        <div style={{ fontSize: 22, lineHeight: 1.45, color: T.sub }}>
          Inferred confidence is stored as analysis. <span style={{ color: T.text }}>Measured validation stays separate</span>, so evidence is never overstated.
        </div>
      </Glass>
    </>
  );
};

export const Evidence = () => {
  const f = useCurrentFrame();
  const active = f < 300 ? 0 : f < 570 ? 1 : 2;
  return (
    <Scene duration={len("Evidence")}>
      <Sequence durationInFrames={300} layout="none">
        <Scene duration={300} fadeIn={1}>
          <ProfileBeat />
        </Scene>
      </Sequence>
      <Sequence from={300} durationInFrames={270} layout="none">
        <Scene duration={270}>
          <EnrichBeat />
        </Scene>
      </Sequence>
      <Sequence from={570} durationInFrames={330} layout="none">
        <Scene duration={330} fadeOut={1}>
          <AnalyzeBeat />
        </Scene>
      </Sequence>
      <StepTabs active={active} />
    </Scene>
  );
};

/* ───────────────────────── 7. Logical ───────────────────────── */

export const Logical = () => {
  const f = useCurrentFrame();
  const X = { cust: 120, order: 590, line: 1060 };
  const Y = { top: 340, low: 720 };
  const W = 420;
  const lineRows: Row[] = [
    { n: "OrderLineID", tag: "PK" },
    { n: "OrderID", tag: "FK", tagColor: T.azure },
    { n: "ProductID", tag: "FK", tagColor: T.azure },
    { n: "Quantity" },
    { n: "UnitPrice" },
    { n: "DiscountPct" },
  ];
  return (
    <Scene duration={len("Logical")}>
      <Title
        kicker="06 · Logical model"
        title="Design the logical model for Silver."
        sub="Normalized entities, keys and relationships, built from the evidence and reviewed before Apply."
      />
      <EntityCard
        name="Customer"
        schema="silver_retail"
        x={X.cust}
        y={Y.top}
        w={W}
        at={20}
        icon="user"
        rows={[{ n: "CustomerID", tag: "PK" }, { n: "SourceCustomerID", tag: "NK", tagColor: T.violet }, { n: "Email", tag: "PII", tagColor: T.red }, { n: "FullName" }]}
      />
      <EntityCard
        name="Order"
        schema="silver_retail"
        x={X.order}
        y={Y.top}
        w={W}
        at={40}
        rows={[{ n: "OrderID", tag: "PK" }, { n: "CustomerID", tag: "FK", tagColor: T.azure }, { n: "OrderDate" }, { n: "OrderStatusCode", tag: "FK", tagColor: T.azure }]}
      />
      <EntityCard name="Order Line" schema="silver_retail" x={X.line} y={Y.top} w={W} at={60} rows={lineRows} />
      <EntityCard
        name="Order Status"
        schema="silver_retail"
        x={X.order}
        y={Y.low}
        w={W}
        at={110}
        rows={[{ n: "OrderStatusCode", tag: "PK" }, { n: "Description" }]}
        glow={f > 110 && f < 220}
        color={T.violet}
      />
      <EntityCard
        name="Product"
        schema="silver_retail"
        x={X.line}
        y={Y.low}
        w={W}
        at={90}
        rows={[{ n: "ProductID", tag: "PK" }, { n: "SKU", tag: "NK", tagColor: T.violet }, { n: "ProductName" }]}
      />
      <Flow a={{ x: X.order, y: rowY(Y.top, 1) }} b={{ x: X.cust + W, y: rowY(Y.top, 0) }} at={80} color={T.azure} width={3} />
      <Flow a={{ x: X.line, y: rowY(Y.top, 1) }} b={{ x: X.order + W, y: rowY(Y.top, 0) }} at={95} color={T.azure} width={3} />
      <Flow a={{ x: X.line + W / 2, y: Y.top + HEAD_H + lineRows.length * ROW_H + 18 }} b={{ x: X.line + W / 2, y: Y.low }} at={120} color={T.azure} width={3} vertical label="many : 1" labelT={0.45} />
      <Flow a={{ x: X.order + W / 2, y: Y.top + HEAD_H + 4 * ROW_H + 18 }} b={{ x: X.order + W / 2, y: Y.low }} at={130} color={T.violet} width={3} vertical label="normalized codes" labelT={0.5} />
      {[
        { t: "Third normal form", d: "Status codes move to their own entity", c: T.violet, at: 170, i: "layers" },
        { t: "Model policy", d: "Audit and history columns added automatically", c: T.mint, at: 230, i: "shield" },
        { t: "Governed Apply", d: "Reviewed draft saved as a new model revision", c: T.copper, at: 290, i: "check" },
      ].map((b, i) => (
        <Glass key={b.t} at={b.at} x={1530} y={340 + i * 200} w={280} h={180} pad={22} from="right" glow={b.c}>
          <Orb kind={b.i} color={b.c} size={48} />
          <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 26, marginTop: 12 }}>{b.t}</div>
          <div style={{ fontSize: 18, color: T.sub, lineHeight: 1.35, marginTop: 4 }}>{b.d}</div>
        </Glass>
      ))}
      <div
        style={{
          position: "absolute",
          left: X.cust,
          top: 600,
          width: W,
          opacity: ramp(f, 240, 262),
          fontFamily: FONT.mono,
          fontSize: 19,
          lineHeight: 1.7,
          color: T.sub,
        }}
      >
        <div style={{ color: T.mint, fontFamily: FONT.body, fontSize: 15, letterSpacing: 2, fontWeight: 600 }}>+ AUDIT COLUMNS</div>
        GDSBatchID · PipelineRunID
        <br />
        CreatedDate · UpdatedDate
        <br />
        CreatedBy · UpdatedBy · IsActive
      </div>
    </Scene>
  );
};

/* ───────────────────────── 8. Dimensional ───────────────────────── */

export const Dimensional = () => {
  const f = useCurrentFrame();
  const fx = 760;
  const fy = 430;
  const W = 400;
  const factRows: Row[] = [
    { n: "CustomerKey", tag: "FK", tagColor: T.azure },
    { n: "ProductKey", tag: "FK", tagColor: T.azure },
    { n: "OrderDateKey", tag: "FK", tagColor: T.azure },
    { n: "OrderStatusKey", tag: "FK", tagColor: T.azure },
    { n: "Quantity", tag: "MEASURE", tagColor: T.mint },
    { n: "SalesAmount", tag: "MEASURE", tagColor: T.mint },
  ];
  const custRows: Row[] = [
    { n: "CustomerKey", tag: "SK" },
    { n: "SourceCustomerID" },
    { n: "Email", tag: "PII", tagColor: T.red },
    { n: "IsCurrentRecord", hl: f > 150, tagColor: T.gold },
    { n: "RecordStartTime", hl: f > 150, tagColor: T.gold },
    { n: "RecordEndTime", hl: f > 150, tagColor: T.gold },
  ];
  return (
    <Scene duration={len("Dimensional")}>
      <Title
        kicker="06 · Dimensional model"
        title="Then the dimensional model for Gold."
        sub="Facts, dimensions and history policies, built on the applied logical model."
      />
      <EntityCard name="FactSales" schema="gold_retail" x={fx} y={fy} w={W} at={20} rows={factRows} color={T.gold} icon="chart" glow />
      <EntityCard name="DimCustomer" schema="gold_retail" x={160} y={320} w={W} at={50} rows={custRows} color={T.copper} icon="user" />
      <EntityCard name="DimProduct" schema="gold_retail" x={1360} y={320} w={W} at={60} rows={[{ n: "ProductKey", tag: "SK" }, { n: "SKU" }, { n: "ProductName" }, { n: "Category" }]} color={T.copper} />
      <EntityCard name="DimDate" schema="gold_retail" x={160} y={740} w={W} at={70} rows={[{ n: "DateKey", tag: "SK" }, { n: "CalendarDate" }, { n: "MonthName" }]} color={T.copper} icon="clock" />
      <EntityCard name="DimOrderStatus" schema="gold_retail" x={1360} y={740} w={W} at={80} rows={[{ n: "OrderStatusKey", tag: "SK" }, { n: "StatusCode" }, { n: "Description" }]} color={T.copper} />
      <Flow a={{ x: fx, y: rowY(fy, 0) }} b={{ x: 560, y: rowY(320, 0) }} at={90} color={T.gold} width={3} />
      <Flow a={{ x: fx + W, y: rowY(fy, 1) }} b={{ x: 1360, y: rowY(320, 0) }} at={98} color={T.gold} width={3} />
      <Flow a={{ x: fx, y: rowY(fy, 2) }} b={{ x: 560, y: rowY(740, 0) }} at={106} color={T.gold} width={3} />
      <Flow a={{ x: fx + W, y: rowY(fy, 3) }} b={{ x: 1360, y: rowY(740, 0) }} at={114} color={T.gold} width={3} />
      <div style={{ position: "absolute", left: fx, top: 360, width: W, display: "flex", justifyContent: "center", opacity: ramp(f, 40, 60) }}>
        <Pill color={T.gold} size={19}>Grain · one row per order line</Pill>
      </div>
      <div style={{ position: "absolute", left: 160, top: 290, opacity: ramp(f, 150, 170) }}>
        <Pill color={T.gold} size={18} solid>
          SCD Type 2 · keeps every version
        </Pill>
      </div>
    </Scene>
  );
};
