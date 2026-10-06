import { C, Frame, Heading, Reveal, Chip } from "../design";

export const Code = () => (
  <Frame chapter="Generate SQL and checks" index={8}>
    <Heading kicker="AUTOMATED AUTHORING WORKFLOWS">
      From mapping to implementation.
    </Heading>
    <Reveal
      at={0.8}
      style={{
        position: "absolute",
        left: 100,
        top: 388,
        width: 1040,
        height: 490,
        borderRadius: 15,
        background: C.ink,
        color: C.paper,
        overflow: "hidden",
        boxShadow: "0 18px 50px #173C3518",
      }}
    >
      <div
        style={{
          padding: "24px 32px",
          borderBottom: "1px solid #496057",
          fontSize: 24,
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>fact_sales.sql</span>
        <span style={{ color: C.mint, fontSize: 20 }}>
          SQL ARTIFACT · EXCERPT
        </span>
      </div>
      <div
        style={{
          fontFamily: "IBM Plex Mono",
          fontSize: 30,
          lineHeight: 1.8,
          padding: "28px 34px",
        }}
      >
        <div>
          <span style={{ color: "#E2AF85" }}>SELECT</span> CustomerKey,
          ProductKey,
        </div>
        <div style={{ paddingLeft: 110 }}>DateKey,</div>
        <Reveal at={2.5}>
          <div
            style={{
              paddingLeft: 110,
              background: "#35544A",
              borderLeft: `3px solid ${C.accent}`,
            }}
          >
            Quantity * UnitPrice
          </div>
          <div style={{ paddingLeft: 110 }}>
            <span style={{ color: "#E2AF85" }}>AS</span> SalesAmount
          </div>
        </Reveal>
        <div>
          <span style={{ color: "#E2AF85" }}>FROM</span> mapped_sales_lines;
        </div>
      </div>
    </Reveal>
    <Reveal
      at={4}
      style={{ position: "absolute", left: 1200, top: 392, width: 610 }}
    >
      <div style={{ fontSize: 22, color: C.accent, letterSpacing: 2 }}>
        VALIDATION DEFINITION
      </div>
      <h2
        style={{
          fontSize: 44,
          lineHeight: 1.2,
          fontWeight: 500,
          letterSpacing: -1,
          margin: "25px 0",
        }}
      >
        Every sale needs
        <br />a customer reference.
      </h2>
      <div style={{ fontSize: 28, lineHeight: 1.55, color: C.muted }}>
        Expected result
        <br />
        <strong style={{ fontSize: 37, fontWeight: 500, color: C.ink }}>
          0 missing customer keys
        </strong>
      </div>
      <div style={{ marginTop: 28 }}>
        <Chip color={C.accent}>Authored check · not executed</Chip>
      </div>
      <Reveal at={7} style={{ marginTop: 29, fontSize: 27, color: C.green }}>
        Ready for review
      </Reveal>
    </Reveal>
  </Frame>
);
