import { Img, staticFile, useCurrentFrame } from "remotion";
import {
  AtlasMark,
  Check,
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
  Window,
} from "./kit";
import { EntityCard, rowY, type Row } from "./ActModel";
import { LakeLayer } from "./ActFoundation";
import { len } from "./timeline";

/* ───────────────────────── SQL rendering ───────────────────────── */

const KEYWORDS = new Set([
  "SELECT", "FROM", "JOIN", "ON", "WHERE", "AS", "AND", "CAST", "COALESCE", "LEFT", "DATE", "WITH", "IS", "NULL", "NOT", "INNER",
]);

export function SqlLine({ text, color }: { text: string; color?: string }) {
  if (text.trim().startsWith("--")) {
    return <span style={{ color: T.dim }}>{text}</span>;
  }
  const parts = text.split(/(\s+|[(),*<>=]|'[^']*')/).filter((p) => p !== "");
  return (
    <span style={{ color }}>
      {parts.map((p, i) => {
        let c: string | undefined;
        if (KEYWORDS.has(p.toUpperCase()) && p === p.toUpperCase()) c = T.violet;
        else if (/^'.*'$/.test(p)) c = T.gold;
        else if (/^\d/.test(p)) c = T.gold;
        else if (/^[(),*<>=]$/.test(p)) c = T.sub;
        else if (/^[A-Z][A-Za-z]+$/.test(p)) c = T.mint;
        return (
          <span key={i} style={{ color: color ?? c }}>
            {p}
          </span>
        );
      })}
    </span>
  );
}

/** Reveals code character by character across lines. */
export function CodeType({
  lines,
  at,
  cpf = 3,
  size = 22,
  lineHeight = 1.65,
}: {
  lines: string[];
  at: number;
  cpf?: number;
  size?: number;
  lineHeight?: number;
}) {
  const f = useCurrentFrame();
  let budget = Math.max(0, (f - at) * cpf);
  return (
    <div style={{ fontFamily: FONT.mono, fontSize: size, lineHeight }}>
      {lines.map((l, i) => {
        const shown = Math.max(0, Math.min(l.length, Math.floor(budget)));
        budget -= l.length + 4;
        const visible = shown > 0 || (l.length === 0 && budget > 0);
        return (
          <div key={i} style={{ display: "flex", opacity: visible ? 1 : 0, whiteSpace: "pre" }}>
            <span style={{ width: 46, color: T.dim, textAlign: "right", marginRight: 22, flexShrink: 0 }}>{i + 1}</span>
            <SqlLine text={l.slice(0, shown)} />
          </div>
        );
      })}
    </div>
  );
}

/* ───────────────────────── 9. Mapping ───────────────────────── */

const SRC_ROWS: Row[] = [
  { n: "oi.order_line_id" },
  { n: "oi.quantity" },
  { n: "oi.unit_price" },
  { n: "oi.discount_pct", tag: "NOT MAPPED", tagColor: T.dim, dim: true },
  { n: "o.cust_id" },
  { n: "o.order_date" },
  { n: "o.status" },
];
const TGT_ROWS: Row[] = [
  { n: "SourceOrderLineID" },
  { n: "Quantity" },
  { n: "SalesAmount", tag: "MEASURE", tagColor: T.mint },
  { n: "CustomerKey", tag: "FK", tagColor: T.azure },
  { n: "OrderDateKey", tag: "FK", tagColor: T.azure },
];
const CHIPS = [
  { expr: "direct", from: [0], to: 0 },
  { expr: "direct", from: [1], to: 1 },
  { expr: "quantity * unit_price", from: [1, 2], to: 2 },
  { expr: "lookup current DimCustomer", from: [4], to: 3 },
  { expr: "CAST(order_date AS DATE)", from: [5], to: 4 },
];

export const Mapping = () => {
  const f = useCurrentFrame();
  const SX = 120;
  const SY = 330;
  const SW = 440;
  const TX = 1370;
  const TY = 400;
  const CX = 690;
  const CW = 520;
  const chipY = (i: number) => 380 + i * 82;
  return (
    <Scene duration={len("Mapping")}>
      <Title
        kicker="07 · Mapping"
        title="Map every target column to its sources."
        sub="Rowsets, joins, filters and field expressions, documented for each target and source system."
      />
      <EntityCard name="Source rowset" schema="bronze_erp" x={SX} y={SY} w={SW} rows={SRC_ROWS} at={10} color={T.bronze} />
      <EntityCard name="FactSales" schema="gold_retail" x={TX} y={TY} w={440} rows={TGT_ROWS} at={20} color={T.gold} icon="chart" />
      {CHIPS.map((c, i) => {
        const at = 50 + i * 30;
        const y = chipY(i);
        const active = f >= at && f < at + 60;
        return (
          <div key={i}>
            {c.from.map((s) => (
              <Flow key={s} a={{ x: SX + SW, y: rowY(SY, s) }} b={{ x: CX, y: y + 28 }} at={at} dur={18} color={T.mint} width={2.5} />
            ))}
            <Flow a={{ x: CX + CW, y: y + 28 }} b={{ x: TX, y: rowY(TY, c.to) }} at={at + 14} dur={18} color={T.gold} width={2.5} packets={1} speed={45} />
            <div
              style={{
                position: "absolute",
                left: CX,
                top: y,
                width: CW,
                height: 56,
                boxSizing: "border-box",
                borderRadius: 12,
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "0 18px",
                background: active ? `${T.copper}22` : "rgba(255,255,255,0.05)",
                border: `1.5px solid ${active ? T.copper : T.border}`,
                boxShadow: active ? `0 0 30px ${T.copper}40` : undefined,
                opacity: ramp(f, at + 6, at + 18),
                transform: `scale(${0.9 + 0.1 * ramp(f, at + 6, at + 20)})`,
              }}
            >
              <Icon kind="code" size={22} color={T.copper} />
              <span style={{ fontFamily: FONT.mono, fontSize: 21 }}>{c.expr}</span>
            </div>
          </div>
        );
      })}
      <Glass at={210} x={120} y={800} w={1690} h={150} pad={26} glow={T.copper}>
        <div style={{ display: "flex", alignItems: "center", gap: 34 }}>
          <div style={{ fontSize: 17, letterSpacing: 2, textTransform: "uppercase", color: T.copper, fontWeight: 600, width: 200 }}>
            Object transformation
          </div>
          {[
            ["Rowset", "order_items JOIN orders ON order_id"],
            ["Filter", "status <> 'X'"],
            ["Source system", "ERP"],
          ].map(([k, v], i) => (
            <div key={k} style={{ opacity: ramp(f, 225 + i * 12, 240 + i * 12) }}>
              <div style={{ fontSize: 16, color: T.dim, letterSpacing: 1.5, textTransform: "uppercase" }}>{k}</div>
              <div style={{ fontFamily: FONT.mono, fontSize: 23, marginTop: 6 }}>{v}</div>
            </div>
          ))}
        </div>
      </Glass>
    </Scene>
  );
};

/* ───────────────────────── 10. Code ───────────────────────── */

const SQL = [
  "-- fact_sales.sql · target gold_retail.FactSales · system ERP",
  "SELECT",
  "  oi.order_line_id               AS SourceOrderLineID,",
  "  o.cust_id                      AS SourceCustomerID,",
  "  CAST(o.order_date AS DATE)     AS OrderDate,",
  "  oi.quantity                    AS Quantity,",
  "  oi.quantity * oi.unit_price    AS SalesAmount",
  "FROM bronze_erp.order_items oi",
  "JOIN bronze_erp.orders o",
  "  ON o.order_id = oi.order_id",
  "WHERE o.status <> 'X'",
];

const FILES = [
  ["silver", "customer.sql"],
  ["silver", "order.sql"],
  ["silver", "order_line.sql"],
  ["silver", "product.sql"],
  ["gold", "dim_customer.sql"],
  ["gold", "fact_sales.sql"],
];

export const Code = () => {
  const f = useCurrentFrame();
  return (
    <Scene duration={len("Code")}>
      <Title
        kicker="08 · Code generation"
        title="Generate the transformation SQL."
        sub="Built from the applied mapping, one file per target and source system, then reviewed before it is saved."
      />
      <div style={{ position: "absolute", left: 120, top: 320 }}>
        <Window
          title="fact_sales.sql"
          style={{ width: 1090, height: 640 }}
          bar={<Pill color={T.mint} size={15}>Generated from applied mapping</Pill>}
        >
          <div style={{ padding: "24px 20px" }}>
            <CodeType lines={SQL} at={20} cpf={3.2} size={23} lineHeight={1.75} />
          </div>
        </Window>
      </div>
      <Glass at={30} x={1260} y={320} w={550} h={360} pad={24} from="right">
        <div style={{ fontSize: 17, letterSpacing: 2, textTransform: "uppercase", color: T.sub, fontWeight: 600, marginBottom: 12 }}>
          Code artifacts
        </div>
        {FILES.map(([layer, file], i) => (
          <div key={file} style={{ display: "flex", alignItems: "center", gap: 14, height: 44, opacity: ramp(f, 40 + i * 18, 52 + i * 18) }}>
            <Check at={52 + i * 18} size={26} color={layer === "gold" ? T.gold : T.silver} />
            <span style={{ fontFamily: FONT.mono, fontSize: 20, color: T.dim }}>{layer}/</span>
            <span style={{ fontFamily: FONT.mono, fontSize: 21, marginLeft: -12 }}>{file}</span>
          </div>
        ))}
      </Glass>
      <Glass at={170} x={1260} y={700} w={550} h={260} pad={24} from="right" glow={T.mint}>
        <div style={{ fontSize: 17, letterSpacing: 2, textTransform: "uppercase", color: T.mint, fontWeight: 600, marginBottom: 12 }}>
          Validation definitions
        </div>
        {["Row count matches the source rowset", "SalesAmount is never null", "Every CustomerKey resolves"].map((t, i) => (
          <div key={t} style={{ display: "flex", alignItems: "center", gap: 12, height: 44, fontSize: 21, opacity: ramp(f, 185 + i * 14, 198 + i * 14) }}>
            <Icon kind="shield" size={24} color={T.mint} />
            {t}
          </div>
        ))}
        <div style={{ marginTop: 10, fontSize: 17, color: T.dim, opacity: ramp(f, 240, 260) }}>
          Saved as definitions. The platform runs them.
        </div>
      </Glass>
    </Scene>
  );
};

/* ───────────────────────── 11. Lakehouse ───────────────────────── */

export const Lakehouse = () => {
  const f = useCurrentFrame();
  const silver = ramp(f, 150, 240, (t) => t);
  const gold = ramp(f, 210, 300, (t) => t);
  return (
    <Scene duration={len("Lakehouse")}>
      <Title
        kicker="09 · Silver and Gold"
        title="GDS runs the code. Silver and Gold fill up."
        sub="Targets and process metadata are registered, then the framework loads each layer in order."
      />
      <Glass at={10} x={120} y={420} w={340} h={300} pad={26} glow={T.copper} from="left">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <AtlasMark size={40} />
          <span style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 30 }}>Applied in Atlas</span>
        </div>
        {["Logical + dimensional model", "Mapping", "Transformation SQL", "Validation definitions"].map((t, i) => (
          <div key={t} style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16, fontSize: 21, color: T.sub }}>
            <Check at={20 + i * 8} size={24} />
            {t}
          </div>
        ))}
      </Glass>
      <Glass at={40} x={530} y={420} w={340} h={300} pad={26} glow={T.violet}>
        <Orb kind="workflow" color={T.violet} size={56} />
        <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 30, marginTop: 14 }}>Platform handoff</div>
        <div style={{ fontSize: 20, color: T.sub, lineHeight: 1.45, marginTop: 8 }}>
          Register Silver and Gold targets. Add process metadata for execution order.
        </div>
      </Glass>
      <Glass at={70} x={940} y={420} w={340} h={300} pad={26} glow={T.azure}>
        <div style={{ display: "flex", gap: 14 }}>
          <Img src={staticFile("brands/azure-data-factory.svg")} style={{ width: 54, height: 54 }} />
          <Img src={staticFile("brands/databricks.svg")} style={{ width: 54, height: 54 }} />
        </div>
        <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 30, marginTop: 14 }}>GDS Framework</div>
        <div style={{ fontSize: 20, color: T.sub, lineHeight: 1.45, marginTop: 8 }}>
          Runs the SQL in order and maintains each layer.
        </div>
      </Glass>
      <Flow a={{ x: 460, y: 570 }} b={{ x: 530, y: 570 }} at={50} color={T.copper} packets={1} speed={40} />
      <Flow a={{ x: 870, y: 570 }} b={{ x: 940, y: 570 }} at={80} color={T.violet} packets={1} speed={40} />
      <Flow a={{ x: 1280, y: 540 }} b={{ x: 1380, y: 570 }} at={140} color={T.silver} packets={2} speed={60} />
      <Flow a={{ x: 1280, y: 600 }} b={{ x: 1380, y: 396 }} at={200} color={T.gold} packets={2} speed={60} />
      <LakeLayer name="Gold" color={T.gold} x={1380} y={315} h={162} w={430} fill={gold} tables={["fact_sales", "dim_customer", "dim_product", "dim_date"]} at={20} active={f > 210} />
      <LakeLayer name="Silver" color={T.silver} x={1380} y={490} h={162} w={430} fill={silver} tables={["customer", "order", "order_line", "product", "order_status"]} at={26} active={f > 150} />
      <LakeLayer name="Bronze" color={T.bronze} x={1380} y={665} h={162} w={430} fill={1} tables={["customers", "orders", "order_items", "products"]} at={32} active />
      <div
        style={{
          position: "absolute",
          left: 120,
          top: 790,
          width: 1160,
          display: "flex",
          gap: 14,
          opacity: ramp(f, 250, 275),
        }}
      >
        <Icon kind="shield" size={28} color={T.gold} />
        <span style={{ fontSize: 23, color: T.sub, lineHeight: 1.4 }}>
          Applying in Atlas saves governed records. Deployment and execution remain separate, approved platform steps.
        </span>
      </div>
    </Scene>
  );
};
