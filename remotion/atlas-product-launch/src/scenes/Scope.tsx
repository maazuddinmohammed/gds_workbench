import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, Frame, Heading, Icon } from "../design";
import { Pointer, SourceObject } from "../objects";

export const Scope = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = f / fps;
  const times = [2.5, 3.7, 4.9, 6.1, 7.3, 8.5];
  const count = times.filter((x) => t >= x).length;
  const saved = t >= 10.6;
  const inputs = [
    ["sql", "Orders"],
    ["api", "Customers"],
    ["nosql", "Products"],
    ["stream", "Order events"],
    ["folder", "Store extracts"],
    ["files", "Supplier feeds"],
  ] as const;
  return (
    <Frame chapter="Create and scope a model" index={4}>
      <Heading kicker="ATLAS / MODEL INPUT SCOPE">Choose what belongs.</Heading>
      <div
        style={{
          position: "absolute",
          left: 100,
          top: 340,
          width: 1720,
          height: 625,
          background: C.white,
          border: `1px solid ${C.line}`,
          borderRadius: 18,
          overflow: "hidden",
          boxShadow: "0 20px 60px #233A3410",
        }}
      >
        <div
          style={{
            padding: "25px 36px",
            borderBottom: `1px solid ${C.line}`,
            fontSize: 24,
            color: C.muted,
            display: "flex",
            justifyContent: "space-between",
          }}
        >
          <span>Models / Create model</span>
          <span>ILLUSTRATIVE DEMO</span>
        </div>
        <div style={{ position: "absolute", left: 36, top: 121, width: 510 }}>
          <div style={{ fontSize: 24, color: C.muted }}>MODEL NAME</div>
          <div
            style={{
              fontSize: 46,
              marginTop: 17,
              padding: "17px 22px",
              border: `1px solid ${C.line}`,
              borderRadius: 9,
            }}
          >
            Retail Sales
          </div>
          <div style={{ fontSize: 24, color: C.accent, marginTop: 40 }}>
            BUSINESS REQUIREMENT
          </div>
          <div style={{ fontSize: 34, lineHeight: 1.4, marginTop: 15 }}>
            Sales by customer,
            <br />
            product, and date.
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 15,
              marginTop: 35,
            }}
          >
            <span style={{ fontSize: 67, color: C.green }}>{count}</span>
            <span style={{ fontSize: 28, color: C.muted }}>
              sources selected
            </span>
          </div>
        </div>
        <div style={{ position: "absolute", left: 650, top: 102, width: 1025 }}>
          {inputs.map(([kind, name], i) => (
            <div
              key={kind}
              style={{
                height: 69,
                display: "flex",
                alignItems: "center",
                gap: 22,
                borderBottom: `1px solid ${C.line}`,
                background: t >= times[i] ? "#EEF2E9" : "transparent",
                padding: "0 17px",
              }}
            >
              <div
                style={{
                  width: 29,
                  height: 29,
                  border: `2px solid ${t >= times[i] ? C.green : "#C3CABE"}`,
                  borderRadius: 6,
                  background: t >= times[i] ? C.green : "white",
                  color: "white",
                  display: "grid",
                  placeItems: "center",
                }}
              >
                {t >= times[i] ? <Icon kind="check" size={25} /> : null}
              </div>
              <SourceObject kind={kind} width={68} />
              <span style={{ fontSize: 31 }}>{name}</span>
              <span
                style={{ marginLeft: "auto", fontSize: 23, color: C.muted }}
              >
                Bronze
              </span>
            </div>
          ))}
        </div>
        <div
          style={{
            position: "absolute",
            right: 44,
            bottom: 28,
            display: "flex",
            alignItems: "center",
            gap: 30,
          }}
        >
          {saved ? (
            <span style={{ fontSize: 28, color: C.green }}>Scope saved</span>
          ) : null}
          <div
            style={{
              padding: "16px 29px",
              borderRadius: 9,
              background: saved ? C.green : C.accent,
              color: "white",
              fontSize: 27,
            }}
          >
            {saved ? "6 sources in scope" : "Save scope"}
          </div>
        </div>
      </div>
      <Pointer
        times={[1.7, 2.5, 3.7, 4.9, 6.1, 7.3, 8.5, 9.4, 10.6]}
        x={[970, 782, 782, 782, 782, 782, 782, 1590, 1630]}
        y={[422, 478, 547, 616, 685, 754, 823, 905, 905]}
        clicks={[2.5, 3.7, 4.9, 6.1, 7.3, 8.5, 10.6]}
      />
    </Frame>
  );
};
