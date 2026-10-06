import { C, Frame, Heading, Reveal, Icon, LinkLine, Chip } from "../design";

export const Mapping = () => (
  <Frame chapter="Source-to-target mapping" index={7}>
    <Heading kicker="MAPPING DOCUMENTS">Follow every transformation.</Heading>
    <div
      style={{
        position: "absolute",
        left: 100,
        right: 100,
        top: 336,
        borderBottom: `1px solid ${C.line}`,
        paddingBottom: 25,
        display: "flex",
        justifyContent: "space-between",
        fontSize: 28,
      }}
    >
      <span>OrderLine → FactSales</span>
      <Chip>Source · expression · target</Chip>
    </div>
    <LinkLine d="M551 606H740M551 734H659V606H740M1194 606H1372" at={2} />
    <Reveal
      at={0.6}
      style={{ position: "absolute", left: 100, top: 462, width: 451 }}
    >
      <div
        style={{
          fontSize: 22,
          color: C.muted,
          letterSpacing: 2,
          marginBottom: 28,
        }}
      >
        SOURCE FIELDS
      </div>
      {["Quantity", "UnitPrice"].map((field, i) => (
        <Reveal
          key={field}
          at={0.8 + i * 0.5}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 21,
            background: C.white,
            border: `1px solid ${C.line}`,
            borderRadius: 12,
            padding: "28px 27px",
            marginBottom: 28,
          }}
        >
          <Icon kind="database" color={C.green} size={41} />
          <div>
            <div style={{ fontSize: 35, fontFamily: "IBM Plex Mono" }}>
              {field}
            </div>
            <div style={{ fontSize: 23, color: C.muted, marginTop: 9 }}>
              OrderLine
            </div>
          </div>
        </Reveal>
      ))}
    </Reveal>
    <Reveal
      at={2.8}
      style={{
        position: "absolute",
        left: 740,
        top: 512,
        width: 454,
        height: 242,
        borderRadius: 14,
        background: C.pale,
        boxSizing: "border-box",
        padding: "30px 25px",
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: 22, color: C.accent, letterSpacing: 2 }}>
        EXPRESSION
      </div>
      <div style={{ fontSize: 29, fontFamily: "IBM Plex Mono", marginTop: 30 }}>
        Quantity × UnitPrice
      </div>
      <div style={{ fontSize: 24, color: C.muted, marginTop: 28 }}>
        Calculate the line amount
      </div>
    </Reveal>
    <Reveal
      at={4.1}
      style={{
        position: "absolute",
        left: 1372,
        top: 512,
        width: 448,
        height: 242,
        borderRadius: 14,
        background: C.ink,
        color: C.paper,
        padding: "30px 30px",
        boxSizing: "border-box",
      }}
    >
      <div style={{ fontSize: 22, color: C.mint, letterSpacing: 2 }}>
        TARGET FIELD
      </div>
      <div style={{ fontSize: 36, fontFamily: "IBM Plex Mono", marginTop: 30 }}>
        SalesAmount
      </div>
      <div style={{ fontSize: 26, color: C.mint, marginTop: 26 }}>
        FactSales · decimal
      </div>
    </Reveal>
    <Reveal
      at={5.2}
      style={{
        position: "absolute",
        left: 100,
        right: 100,
        top: 868,
        borderTop: `1px solid ${C.line}`,
        paddingTop: 29,
        display: "flex",
        gap: 74,
        fontSize: 27,
        color: C.muted,
      }}
    >
      <span>Join customer + product keys</span>
      <span>Keep completed sales</span>
      <span>One row per sales line</span>
    </Reveal>
  </Frame>
);
