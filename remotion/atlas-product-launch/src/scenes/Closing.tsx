import { C, Frame, Logo, Reveal, Icon, LinkLine } from "../design";

export const Closing = () => (
  <Frame chapter="The complete lifecycle" index={12} dark>
    <div style={{ position: "absolute", left: 100, top: 230 }}>
      <Logo size={87} light />
      <Reveal at={1}>
        <h1
          style={{
            fontSize: 118,
            lineHeight: 1.04,
            letterSpacing: -6,
            fontWeight: 500,
            margin: "36px 0",
          }}
        >
          Design.
          <br />
          Build. <span style={{ color: "#D7AE86" }}>Evolve.</span>
        </h1>
      </Reveal>
      <Reveal at={2.7} style={{ fontSize: 32, color: C.mint }}>
        Your data platform, with context.
      </Reveal>
    </div>
    <LinkLine d="M1275 337V738" at={1} color={C.gold} />
    <LinkLine
      d="M1540 750C1810 750 1810 330 1540 330"
      at={3.2}
      color={C.mint}
      dashed
    />
    {[
      ["layers", "Source metadata", "GDS ingestion"],
      ["model", "Common models", "Atlas authoring"],
      ["code", "Reviewed code", "Delivery + orchestration"],
      ["search", "Ongoing change", "Atlas plugin"],
    ].map(([icon, title, sub], i) => (
      <Reveal
        key={title}
        at={0.5 + i * 0.6}
        style={{
          position: "absolute",
          left: 1180,
          top: 260 + i * 148,
          width: 520,
          padding: "19px 25px",
          display: "flex",
          gap: 25,
          alignItems: "center",
          background: C.dark,
        }}
      >
        <div
          style={{
            width: 70,
            height: 70,
            display: "grid",
            placeItems: "center",
            border: "1px solid #6E897B",
            borderRadius: "50%",
            background: C.dark,
            color: C.gold,
          }}
        >
          <Icon kind={icon} size={33} />
        </div>
        <div>
          <div style={{ fontSize: 35 }}>{title}</div>
          <div style={{ fontSize: 23, color: C.mint, marginTop: 8 }}>{sub}</div>
        </div>
      </Reveal>
    ))}
  </Frame>
);
