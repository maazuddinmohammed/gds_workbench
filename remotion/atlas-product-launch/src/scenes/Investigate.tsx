import { C, Frame, Heading, Reveal, Chip, Icon } from "../design";

export const Investigate = () => (
  <Frame chapter="Investigate with the plugin" index={10}>
    <Heading kicker="ATLAS / COPILOT + CODEX">
      Bring the problem into context.
    </Heading>
    <Reveal
      at={0.7}
      style={{
        position: "absolute",
        left: 100,
        top: 400,
        width: 645,
        height: 470,
        borderTop: `3px solid ${C.accent}`,
        background: C.white,
        padding: "28px 34px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 22,
          color: C.muted,
        }}
      >
        <span>ILLUSTRATIVE PIPELINE ISSUE</span>
        <Chip color={C.accent}>Failed</Chip>
      </div>
      <h2
        style={{
          fontSize: 45,
          lineHeight: 1.2,
          fontWeight: 500,
          margin: "38px 0 24px",
          letterSpacing: -1,
        }}
      >
        Sales amount
        <br />
        conversion failed.
      </h2>
      <div
        style={{
          fontFamily: "IBM Plex Mono",
          fontSize: 25,
          lineHeight: 1.6,
          color: C.muted,
        }}
      >
        Affected artifact
        <br />
        <span style={{ color: C.ink }}>fact_sales.sql</span>
      </div>
      <div style={{ fontSize: 24, color: C.accent, marginTop: 28 }}>
        Supplied error → affected artifact
      </div>
    </Reveal>
    <Reveal
      at={1.5}
      style={{
        position: "absolute",
        left: 890,
        top: 400,
        width: 856,
        height: 470,
        border: `1px solid ${C.line}`,
        borderRadius: 14,
        background: C.white,
        padding: "28px 34px",
      }}
    >
      <div
        style={{
          fontSize: 22,
          color: C.muted,
          display: "flex",
          gap: 14,
          alignItems: "center",
        }}
      >
        <Icon kind="search" size={28} /> ATLAS PLUGIN · ILLUSTRATIVE
        CONVERSATION
      </div>
      <div
        style={{
          fontSize: 31,
          lineHeight: 1.4,
          background: C.pale,
          borderRadius: 10,
          padding: 23,
          marginTop: 24,
        }}
      >
        Investigate this failed sales load.
        <br />
        Explain the cause and proposed fix.
      </div>
      <div style={{ fontSize: 27, lineHeight: 1.5, marginTop: 25 }}>
        <Reveal at={3}>Trace source → mapping → SQL.</Reveal>
        <Reveal at={4.7}>Inspect the conversion and expected type.</Reveal>
        <Reveal at={6.4}>
          <span style={{ color: C.green }}>
            Prepare the correction for review.
          </span>
        </Reveal>
      </div>
    </Reveal>
  </Frame>
);
