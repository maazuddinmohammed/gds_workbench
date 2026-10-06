import { C, Frame, Heading, Reveal, Icon } from "../design";

export const Evolve = () => (
  <Frame chapter="Requirements to reviewed change" index={11}>
    <Heading kicker="ATLAS PLUGIN / COORDINATED CHANGE">
      One request. Connected changes.
    </Heading>
    <Reveal
      at={0.3}
      style={{
        position: "absolute",
        left: 100,
        top: 336,
        right: 100,
        display: "flex",
        alignItems: "center",
        gap: 22,
        padding: "24px 28px",
        background: C.pale,
        borderRadius: 13,
      }}
    >
      <Icon kind="document" color={C.accent} size={39} />
      <span style={{ fontSize: 35 }}>
        “Add customer loyalty tier to sales reporting.”
      </span>
    </Reveal>
    {[
      {
        icon: "model",
        title: "Model",
        base: "DimCustomer",
        lines: ["+ LoyaltyTier", "  Business attribute"],
      },
      {
        icon: "layers",
        title: "Mapping",
        base: "Customers.LoyaltyTier",
        lines: ["→ DimCustomer", "  .LoyaltyTier"],
      },
      {
        icon: "code",
        title: "SQL",
        base: "dim_customer.sql",
        lines: ["+ LoyaltyTier", "  AS LoyaltyTier"],
      },
      {
        icon: "check",
        title: "Validation",
        base: "Allowed membership tiers",
        lines: ["+ Gold · Silver", "  Bronze"],
      },
    ].map(({ icon, title, base, lines }, i) => (
      <Reveal
        key={title}
        at={1 + i * 0.45}
        style={{
          position: "absolute",
          left: 100 + i * 445,
          top: 483,
          width: 385,
          height: 311,
          borderRadius: 13,
          border: `1px solid ${C.line}`,
          background: C.white,
          boxSizing: "border-box",
          padding: "25px 23px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 17 }}>
          <Icon kind={icon} color={C.accent} size={38} />
          <span style={{ fontSize: 35 }}>{title}</span>
        </div>
        <div
          style={{
            fontSize: 21,
            fontFamily: "IBM Plex Mono",
            color: C.muted,
            marginTop: 29,
            paddingBottom: 22,
            borderBottom: `1px solid ${C.line}`,
          }}
        >
          {base}
        </div>
        <Reveal
          at={3.5 + i * 0.5}
          style={{
            marginTop: 21,
            background: "#E9EFE3",
            padding: "13px 11px",
            fontFamily: "IBM Plex Mono",
            color: C.green,
            fontSize: 23,
            lineHeight: 1.5,
          }}
        >
          {lines.map((line) => (
            <div key={line}>{line}</div>
          ))}
        </Reveal>
      </Reveal>
    ))}
    <Reveal
      at={7}
      style={{
        position: "absolute",
        left: 100,
        right: 100,
        top: 852,
        borderTop: `1px solid ${C.line}`,
        paddingTop: 28,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: 28,
      }}
    >
      <span>Review the changes</span>
      <span style={{ color: C.accent }}>→</span>
      <span>Approve Stage</span>
      <span style={{ color: C.accent }}>→</span>
      <span>Server validation</span>
      <span style={{ color: C.accent }}>→</span>
      <span>Approve Apply</span>
    </Reveal>
    <Reveal
      at={8.6}
      style={{
        position: "absolute",
        left: 100,
        top: 943,
        display: "flex",
        gap: 13,
        alignItems: "center",
        fontSize: 25,
        color: C.green,
      }}
    >
      <Icon kind="lock" size={28} />
      Model, mappings, code, and checks reviewed together.
    </Reveal>
  </Frame>
);
