/*
 * THROWAWAY PROTOTYPE — sample data only; delete or absorb after design review.
 * Question: Can one stable Object card accumulate evidence across the Model journey?
 * Visual thesis: warm, restrained workspace; Object identity anchors each card.
 * Content plan: Model context, journey, scoped Objects, progressively added evidence.
 * Interaction thesis: stable card order, brief evidence reveals, native detail disclosure.
 * Three layouts on /prototype/object-cards?variant=A|B|C. Verdict: awaiting user review.
 */
import { useEffect, useState } from "react";
import { Brand, DatabaseIcon, ModelIcon, PanelToggleIcon, SearchIcon } from "../../shared/ui";
import "../../styles/object-cards-prototype.css";

export type CardVariant = "A" | "B" | "C";
export const cardStages = ["Input Scope", "Enrichment", "Profiling", "Analysis", "Conceptual", "Logical"] as const;
const stageNotes = [
  "Physical Objects selected as inputs to this Model.",
  "The same Objects, with business descriptions and Attribute meaning.",
  "Descriptions stay visible. Saved measurements add context to each Object.",
  "Descriptions and profiles stay visible. Relationships connect the Objects.",
  "Business concepts bring together evidence from one or more physical Objects.",
  "Normalized Entities define grain, identifiers, Attributes, and relationships.",
];

interface Attribute { name: string; type: string; description: string; distinct: string; nulls: number }
interface PhysicalObject { name: string; description: string; rows: string; note: string; attributes: Attribute[] }
const objects: PhysicalObject[] = [
  { name: "customers", description: "Individuals and organizations that purchase products, including their contact details and registration date.", rows: "128,640", note: "email is missing in 2.4% of rows.", attributes: [
    { name: "customer_id", type: "bigint", description: "Identifier assigned to a customer.", distinct: "128,640", nulls: 0 },
    { name: "customer_name", type: "string", description: "Customer display name.", distinct: "126,902", nulls: 0 },
    { name: "email", type: "string", description: "Primary email used to contact the customer.", distinct: "125,120", nulls: 2.4 },
    { name: "registered_at", type: "timestamp", description: "Date and time the customer registered.", distinct: "128,503", nulls: 0 },
  ] },
  { name: "orders", description: "Purchases placed by customers. Each record captures one order, its placement date, status, and total amount.", rows: "482,190", note: "customer_id is complete; repeated values are expected.", attributes: [
    { name: "order_id", type: "bigint", description: "Identifier assigned to an order.", distinct: "482,190", nulls: 0 },
    { name: "customer_id", type: "bigint", description: "Customer who placed the order.", distinct: "108,421", nulls: 0 },
    { name: "ordered_at", type: "timestamp", description: "Date and time the order was placed.", distinct: "481,650", nulls: 0 },
    { name: "status", type: "string", description: "Current fulfillment state of the order.", distinct: "5", nulls: 0 },
    { name: "total_amount", type: "decimal(12,2)", description: "Total order amount in the source currency.", distinct: "28,416", nulls: 0 },
  ] },
  { name: "order_items", description: "Individual product lines within an order, recording the product, quantity, and unit price at the time of purchase.", rows: "1,432,056", note: "unit_price is missing in 0.1% of rows.", attributes: [
    { name: "order_item_id", type: "bigint", description: "Identifier assigned to an order line.", distinct: "1,432,056", nulls: 0 },
    { name: "order_id", type: "bigint", description: "Order containing this line.", distinct: "482,190", nulls: 0 },
    { name: "product_code", type: "string", description: "Product identifier recorded at purchase.", distinct: "8,420", nulls: 0 },
    { name: "quantity", type: "integer", description: "Number of product units ordered.", distinct: "24", nulls: 0 },
    { name: "unit_price", type: "decimal(12,2)", description: "Price for one product unit at purchase.", distinct: "1,204", nulls: 0.1 },
  ] },
];
const relationships = [
  { from: "orders", to: "customers", key: "customer_id", confidence: "High" },
  { from: "order_items", to: "orders", key: "order_id", confidence: "High" },
];
const concepts = [
  { name: "Customer", description: "A person or organization that purchases from the business.", sources: ["customers"], relationship: "Customer places Purchase", rationale: "Customer identity and contact evidence describe the same business participant." },
  { name: "Purchase", description: "A customer's agreement to buy a set of products at an agreed price.", sources: ["orders", "order_items"], relationship: "Purchase is placed by Customer", rationale: "Order headers and their product lines together describe one business transaction." },
];
const entities = [
  { name: "Customer", grain: "One customer", sources: ["customers"], attributes: ["CustomerID · Identifier", "CustomerName", "RegisteredAt"], relationship: "Customer has CustomerContact; Customer places SalesOrder" },
  { name: "CustomerContact", grain: "One contact method per customer", sources: ["customers"], attributes: ["CustomerID · Identifier / reference", "ContactType · Identifier", "ContactValue"], relationship: "CustomerContact.CustomerID → Customer.CustomerID" },
  { name: "SalesOrder", grain: "One customer order", sources: ["orders"], attributes: ["SalesOrderID · Identifier", "CustomerID · Reference", "OrderedAt", "OrderStatus", "TotalAmount"], relationship: "SalesOrder.CustomerID → Customer.CustomerID" },
  { name: "OrderLine", grain: "One product line within an order", sources: ["order_items"], attributes: ["OrderLineID · Identifier", "SalesOrderID · Reference", "ProductCode", "Quantity", "UnitPrice"], relationship: "OrderLine.SalesOrderID → SalesOrder.SalesOrderID" },
];

export function ObjectCardsPrototype({ variant, stage, onNavigate }: { variant: CardVariant; stage: number; onNavigate: (variant: CardVariant, stage: number) => void }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("customers");
  const [railHidden, setRailHidden] = useState(false);
  const filtered = objects.filter((object) => `sales.${object.name} ${stage > 0 ? object.description : ""}`.toLowerCase().includes(query.toLowerCase()));
  const shown = filtered.find((object) => object.name === selected) ?? filtered[0];
  const variants: CardVariant[] = ["A", "B", "C"];
  const cycle = (offset: number) => onNavigate(variants[(variants.indexOf(variant) + offset + 3) % 3]!, stage);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).closest("input, textarea, select, button, summary, [contenteditable]")) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); cycle(event.key === "ArrowLeft" ? -1 : 1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const changeStage = (next: number) => { setQuery(""); onNavigate(variant, next); };

  return <div className={`app-shell oc-prototype ${railHidden ? "oc-rail-hidden" : ""}`}>
    <header className="oc-topbar"><Brand compact /><div className="oc-model-context"><span>Tenant <strong>DEMO</strong></span><span className="oc-divider" /><span>Model <strong>Customer Commerce</strong></span><span className="oc-revision">r18</span></div><span className="oc-demo">Prototype · Sample data</span></header>
    <aside className="oc-app-rail" aria-label="Workspace"><span title="Metadata"><DatabaseIcon /></span><span className="oc-active" title="Models"><ModelIcon /><small>Models</small></span></aside>
    <aside className="oc-journey" aria-label="Model journey"><button className="oc-hide" type="button" onClick={() => setRailHidden(!railHidden)} aria-label={railHidden ? "Show Model journey" : "Hide Model journey"} aria-expanded={!railHidden}><PanelToggleIcon collapsed={railHidden} /><span>{railHidden ? "Show" : "Hide"}</span></button><nav>{cardStages.map((label, index) => <button key={label} type="button" title={label} aria-current={stage === index ? "step" : undefined} className={stage === index ? "oc-active" : ""} onClick={() => changeStage(index)}><span className="oc-step-number">{index + 1}</span><span>{label}<small>{["3 physical Objects", "Descriptions", "Measurements", "Relationships", "2 business concepts", "4 normalized Entities"][index]}</small></span></button>)}</nav><p className="oc-rail-note">One Model.<br />Evidence at every stage.</p></aside>
    <main className="oc-main">
      <div className="oc-context"><span>Model workspace <span aria-hidden="true">/</span> {stage < 4 ? "Physical Objects" : "Modeled Objects"}</span><span>Tenant Lock · Free</span></div>
      <header className="oc-heading"><div><h1>{cardStages[stage]}</h1><p>{stageNotes[stage]}</p></div><span className="oc-stage-count">{stage < 4 ? "3 Objects in scope" : stage === 4 ? "2 concepts" : "4 Entities"}</span></header>
      <div className="oc-layer-bar" aria-label="Evidence visible on cards">{(stage < 4 ? ["Identity", "Descriptions", "Profiles", "Relationships"] : ["Business meaning", "Physical evidence", "Relationships", ...(stage === 5 ? ["Grain & identifiers"] : [])]).map((label, index) => <span key={label} className={stage >= 4 || index <= stage ? "oc-present" : ""}><i aria-hidden="true" />{label}</span>)}<small>{stage < 4 ? "Same Objects · Added context" : "Separate modeled cards"}</small></div>
      {stage < 4 ? <>
        <div className="oc-toolbar"><label className="oc-search"><span>Find an Object</span><div><SearchIcon /><input type="search" placeholder="Schema or Object name…" value={query} onChange={(event) => setQuery(event.target.value)} /></div></label><span>{filtered.length} of 3 Objects <span aria-hidden="true">·</span> DEMO / COMMERCE / Source</span></div>
        {variant === "A" ? <div className="oc-card-list">{filtered.map((object) => <ObjectCard key={object.name} object={object} stage={stage} />)}</div> : null}
        {variant === "B" && shown ? <div className="oc-inspector-layout"><div className="oc-object-picker" aria-label="Choose an Object">{filtered.map((object) => <button key={object.name} type="button" aria-pressed={shown.name === object.name} onClick={() => setSelected(object.name)}><span className="oc-object-path">sales · Source</span><strong>{object.name}</strong><small>{object.attributes.length} Attributes{stage >= 2 ? ` · ${object.rows} rows` : ""}</small>{stage >= 1 ? <p>{object.description}</p> : null}{stage >= 3 ? <small>{relationships.filter((r) => r.to === object.name).length} incoming · {relationships.filter((r) => r.from === object.name).length} outgoing</small> : null}</button>)}</div><div className="oc-inspector"><ObjectCard key={shown.name} object={shown} stage={stage} expanded /></div></div> : null}
        {variant === "C" && shown ? <><div className="oc-timeline-picker" aria-label="Choose an Object">{filtered.map((object) => <button className="button button-secondary button-small" type="button" key={object.name} aria-pressed={shown.name === object.name} onClick={() => setSelected(object.name)}>{object.name}</button>)}<span>One Object across its stages</span></div><div className="oc-timeline" role="region" aria-label="Cumulative evidence timeline" tabIndex={0}>{cardStages.slice(0, stage + 1).map((label, index) => <section key={label}><header><span>{index + 1}</span><h2>{label}</h2><small>{["Identity", "+ Descriptions", "+ Profiles", "+ Relationships"][index]}</small></header><ObjectCard object={shown} stage={index} /></section>)}</div></> : null}
        {!shown ? <div className="empty-state"><h2>No Objects match “{query}”</h2><button className="text-action" type="button" onClick={() => setQuery("")}>Clear search</button></div> : null}
      </> : <ModeledCards stage={stage} query={query} onQuery={setQuery} onSource={(name) => { setQuery(name); setSelected(name); onNavigate(variant, 3); }} />}
      <footer className="oc-footer"><span>Design preview · All values are illustrative</span><div><button type="button" className="button button-secondary button-small" disabled={stage === 0} onClick={() => changeStage(stage - 1)}>Previous stage</button><button type="button" className="button button-primary button-small" disabled={stage === 5} onClick={() => changeStage(stage + 1)}>{stage === 5 ? "End of preview" : `Explore ${cardStages[stage + 1]}`}</button></div></footer>
    </main>
    {import.meta.env.DEV && stage < 4 ? <div className="oc-switcher" aria-label="Prototype layouts"><button type="button" aria-label="Previous layout" onClick={() => cycle(-1)}>←</button><span><small>Layout {variants.indexOf(variant) + 1} of 3</small><strong>{variant} · {({ A: "Stacked cards", B: "Cards + inspector", C: "Evidence timeline" })[variant]}</strong></span><button type="button" aria-label="Next layout" onClick={() => cycle(1)}>→</button></div> : null}
  </div>;
}

function ObjectCard({ object, stage, expanded = false }: { object: PhysicalObject; stage: number; expanded?: boolean }) {
  const incoming = relationships.filter((r) => r.to === object.name);
  const outgoing = relationships.filter((r) => r.from === object.name);
  return <article className="oc-card" aria-label={`Object ${object.name}`}>
    <header className="oc-card-head"><span className="oc-object-icon"><DatabaseIcon /></span><div><span className="oc-object-path">DEMO / COMMERCE / sales</span><h2>{object.name}</h2></div><div className="oc-card-meta"><span className="oc-zone">Source</span><span>{object.attributes.length} Attributes</span></div></header>
    {stage >= 1 ? <section className={`oc-description ${stage === 1 ? "oc-added" : ""}`}><div className="oc-section-label"><h3>Description</h3>{stage === 1 ? <small>Added in Enrichment</small> : null}</div><p>{object.description}</p></section> : <p className="oc-scope-note">In Model Input Scope <span>Descriptions appear in Enrichment.</span></p>}
    {stage >= 2 ? <section className={`oc-profiles ${stage === 2 ? "oc-added" : ""}`}><div className="oc-section-label"><h3>Profile results</h3><small>{stage === 2 ? "Added in Profiling" : "Current saved measurements"}</small></div><div className="oc-profile-metrics"><div><strong>{object.rows}</strong><span>Rows measured</span></div><div><strong>{object.attributes.length} / {object.attributes.length}</strong><span>Attributes profiled</span></div><div><strong>All rows</strong><span>21 Sep 2026 · 14:32 UTC</span></div></div><p className="oc-profile-note">{object.note}</p></section> : null}
    {stage >= 3 ? <section className="oc-relationships oc-added"><div className="oc-section-label"><h3>Relationships</h3><small>Added in Analysis</small></div><div className="oc-relationship-grid">{([["Incoming", incoming], ["Outgoing", outgoing]] as const).map(([direction, items]) => <div key={direction}><h4>{direction} <span>{items.length}</span></h4>{items.length ? items.map((r) => <details className="oc-relation" key={`${r.from}-${r.to}`}><summary>{r.from} <span aria-hidden="true">→</span> {r.to}<small>{r.confidence} confidence · Inferred</small></summary><p>DEMO / COMMERCE / sales.{r.from}.{r.key}<br />→ DEMO / COMMERCE / sales.{r.to}.{r.key}</p><p>Supported by names, types, and saved profiles. Referential integrity has not been measured.</p></details>) : <p className="oc-muted">No {direction.toLowerCase()} findings.</p>}</div>)}</div></section> : null}
    <details className="oc-attributes" open={expanded || undefined}><summary><span>Attributes <b>{object.attributes.length}</b></span><span>{stage >= 2 ? "Descriptions & profile results" : stage >= 1 ? "Types & descriptions" : "Names & types"}</span></summary><div className="oc-table-scroll" tabIndex={0} role="region" aria-label={`${object.name} Attributes`}><table><thead><tr><th>Attribute</th><th>Type</th>{stage >= 1 ? <th>Description</th> : null}{stage >= 2 ? <><th>Distinct</th><th>Null %</th></> : null}</tr></thead><tbody>{object.attributes.map((attribute) => <tr key={attribute.name}><th>{attribute.name}</th><td>{attribute.type}</td>{stage >= 1 ? <td>{attribute.description}</td> : null}{stage >= 2 ? <><td>{attribute.distinct}</td><td className={attribute.nulls ? "oc-warning" : ""}>{attribute.nulls}%</td></> : null}</tr>)}</tbody></table></div></details>
  </article>;
}

function ModeledCards({ stage, query, onQuery, onSource }: { stage: number; query: string; onQuery: (query: string) => void; onSource: (name: string) => void }) {
  const cards = (stage === 4 ? concepts : entities).filter((card) => card.name.toLowerCase().includes(query.toLowerCase()));
  return <><div className="oc-toolbar"><label className="oc-search"><span>Find {stage === 4 ? "a concept" : "an Entity"}</span><div><SearchIcon /><input type="search" value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Search by name…" /></div></label><span>{cards.length} {stage === 4 ? "concepts" : "Entities"} · Based on 3 physical Objects</span></div><div className="oc-modeled-list">{cards.map((card) => <article className="oc-card" key={card.name}><header className="oc-card-head"><span className="oc-object-icon"><ModelIcon /></span><div><span className="oc-object-path">{stage === 4 ? "Conceptual Model" : "Logical Model"}</span><h2>{card.name}</h2></div><span className="oc-zone">{stage === 4 ? "Business concept" : "Entity"}</span></header><section className="oc-description"><div className="oc-section-label"><h3>{"description" in card ? "Business meaning" : "Grain"}</h3></div><p>{"description" in card ? card.description : card.grain}</p></section>{"attributes" in card ? <section className="oc-modeled-section"><h3>Attributes & identifiers</h3><ul>{card.attributes.map((attribute) => <li key={attribute}>{attribute}</li>)}</ul>{card.name === "CustomerContact" ? <small>Illustrative modeling assumption: contact methods are modeled separately.</small> : null}</section> : <section className="oc-modeled-section"><h3>Why this concept</h3><p>{card.rationale}</p></section>}<section className="oc-modeled-section"><h3>Relationships</h3><p>{card.relationship}</p>{stage === 4 ? <small>Business cardinality: unknown</small> : null}</section><footer className="oc-source-links"><span>Physical evidence</span>{card.sources.map((name) => <button className="text-action" key={name} type="button" onClick={() => onSource(name)}>sales.{name} <span aria-hidden="true">↗</span></button>)}</footer></article>)}</div>{!cards.length ? <div className="empty-state">No matching cards. <button className="text-action" type="button" onClick={() => onQuery("")}>Clear search</button></div> : null}</>;
}
