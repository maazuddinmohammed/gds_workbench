import { C, Frame, Heading, Icon, LinkLine, Reveal } from "../design";

export const Execution = () => (
  <Frame chapter="Delivery and orchestration" index={9} dark>
    <Heading kicker="ATLAS → GLOBAL DATA STORE" dark>
      Power the GDS lifecycle.
    </Heading>
    <Reveal
      at={0.4}
      style={{
        position: "absolute",
        left: 100,
        top: 325,
        fontSize: 31,
        color: C.mint,
      }}
    >
      Delivery handoff → Process registration → GDS orchestration
    </Reveal>
    <LinkLine d="M560 592H705M1305 592H1455" at={2.2} color={C.gold} />
    <LinkLine d="M1630 708V769H913V816M1120 900H1270" at={7} color={C.gold} />
    <Reveal
      at={0.7}
      style={{
        position: "absolute",
        left: 100,
        top: 426,
        width: 460,
        height: 319,
        padding: 33,
        borderRadius: 13,
        boxSizing: "border-box",
        color: C.ink,
        background: C.paper,
      }}
    >
      <Icon kind="file" size={57} color={C.accent} />
      <div style={{ fontSize: 35, marginTop: 20 }}>Reviewed SQL artifact</div>
      <div style={{ fontFamily: "IBM Plex Mono", fontSize: 29, marginTop: 25 }}>
        fact_sales.sql
      </div>
      <div style={{ fontSize: 24, color: C.muted, marginTop: 21 }}>
        Publish to the delivery location
      </div>
    </Reveal>
    <Reveal
      at={2.7}
      style={{
        position: "absolute",
        left: 705,
        top: 426,
        width: 600,
        height: 319,
        borderRadius: 13,
        background: C.pale,
        color: C.ink,
        padding: "29px 32px",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          fontSize: 23,
          color: C.accent,
          letterSpacing: 2,
          marginBottom: 23,
        }}
      >
        PROCESS METADATA
      </div>
      {[
        ["Artifact", "fact_sales.sql"],
        ["Target", "gold.FactSales"],
        ["Location", "Delivery path"],
        ["Depends on", "Required Silver processes"],
      ].map(([key, value], i) => (
        <Reveal
          key={key}
          at={3 + i * 0.4}
          style={{
            display: "flex",
            borderTop: "1px solid #D8C5B3",
            padding: "13px 0",
            fontSize: 24,
          }}
        >
          <span style={{ width: 155, color: C.muted }}>{key}</span>
          <span>{value}</span>
        </Reveal>
      ))}
    </Reveal>
    <Reveal
      at={5.3}
      style={{
        position: "absolute",
        left: 1455,
        top: 460,
        width: 365,
        height: 248,
        boxSizing: "border-box",
        background: "#31574A",
        border: "1px solid #738D7E",
        borderRadius: 17,
        padding: 30,
      }}
    >
      <Icon kind="layers" size={49} color={C.gold} />
      <div style={{ fontSize: 42, marginTop: 20 }}>GDS engine</div>
      <div style={{ fontSize: 25, color: C.mint, marginTop: 16 }}>
        Run dependencies
      </div>
    </Reveal>
    <Reveal
      at={7.4}
      style={{
        position: "absolute",
        left: 100,
        top: 845,
        fontSize: 32,
        lineHeight: 1.5,
      }}
    >
      Run. Maintain. Repeat.
      <div style={{ fontSize: 24, color: C.mint, marginTop: 13 }}>
        Execution lives in GDS.
      </div>
    </Reveal>
    {[
      ["Silver", "Operational tables", "#C7D7C8"],
      ["Gold", "Dimensional tables", "#E7CCA0"],
    ].map(([name, detail, color], i) => (
      <Reveal
        key={name}
        at={7.7 + i * 1}
        style={{
          position: "absolute",
          left: 705 + i * 565,
          top: 816,
          width: 415,
          height: 176,
          borderRadius: 12,
          border: `1px solid ${color}`,
          background: "#264B40",
          boxSizing: "border-box",
          padding: "23px 29px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ fontSize: 38, color }}>{name}</span>
          <Icon kind="database" size={37} color={color} />
        </div>
        <div style={{ fontSize: 25, color: C.mint, marginTop: 13 }}>
          {detail}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
          {[0, 1, 2, 3, 4].map((n) => (
            <div
              key={n}
              style={{ flex: 1, height: 5, background: color, opacity: 0.45 }}
            />
          ))}
        </div>
      </Reveal>
    ))}
  </Frame>
);
