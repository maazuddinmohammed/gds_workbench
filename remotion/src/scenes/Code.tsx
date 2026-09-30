import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { AppFrame, ease, ink, line, muted, orange, Stage } from "../Design";

export const Code = () => {
  const frame = useCurrentFrame();
  const code = [
    ["SELECT", "keyword"],
    ["  o.order_id,", "plain"],
    ["  o.customer_id,", "highlight"],
    ["  i.product_id,", "plain"],
    ["  i.quantity * i.unit_price AS revenue", "plain"],
    ["FROM bronze.orders AS o", "keyword"],
    ["JOIN bronze.order_items AS i", "keyword"],
    ["  ON o.order_id = i.order_id;", "plain"],
  ];
  return (
    <Stage chapter="03 / Connect">
      <Interactive.Div
        name="Code headline"
        style={{
          position: "absolute",
          left: 112,
          top: 221,
          width: 680,
          fontSize: 108,
          lineHeight: 1.05,
          letterSpacing: -6,
          fontWeight: 650,
          opacity: interpolate(frame, [0, 22], [0, 1], ease),
          translate: interpolate(frame, [0, 30], ["0px 30px", "0px 0px"], ease),
        }}
      >
        Carry the
        <br />
        <span style={{ color: orange }}>logic through.</span>
      </Interactive.Div>
      <Interactive.Div
        name="Code subtitle"
        style={{
          position: "absolute",
          left: 119,
          top: 514,
          width: 620,
          fontSize: 37,
          lineHeight: 1.45,
          color: muted,
          opacity: interpolate(frame, [12, 35], [0, 1], ease),
        }}
      >
        From source mappings
        <br />
        to reviewable SQL.
      </Interactive.Div>
      <div
        style={{
          position: "absolute",
          left: 124,
          top: 728,
          display: "flex",
          alignItems: "center",
          gap: 18,
          fontSize: 23,
          color: muted,
          opacity: interpolate(frame, [110, 137], [0, 1], ease),
        }}
      >
        <span style={{ width: 36, height: 2, background: orange }} />
        Trace the intent into every field.
      </div>
      <Interactive.Div
        name="Mapping and code workspace"
        style={{
          position: "absolute",
          left: 801,
          top: 197,
          width: 1000,
          height: 724,
          translate: interpolate(
            frame,
            [0, 40],
            ["110px 0px", "0px 0px"],
            ease,
          ),
          opacity: interpolate(frame, [0, 24], [0, 1], ease),
        }}
      >
        <AppFrame
          section={frame < 100 ? "Mapping" : "Code generation"}
          sidebar={false}
          style={{ height: "100%" }}
        >
          <div
            style={{
              padding: "23px 30px",
              background: "#fff",
              borderBottom: `1px solid ${line}`,
            }}
          >
            <div
              style={{
                fontSize: 15,
                color: muted,
                letterSpacing: 1.5,
                marginBottom: 14,
              }}
            >
              ATTRIBUTE MAPPING / COMMERCE
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 50px 1fr",
                fontSize: 24,
                alignItems: "center",
              }}
            >
              <span style={{ fontWeight: 650 }}>orders.customer_id</span>
              <span style={{ color: orange }}>→</span>
              <span style={{ fontWeight: 650, color: orange }}>
                customer_id
              </span>
            </div>
            <div
              style={{
                height: 3,
                width: `${interpolate(frame, [40, 85], [0, 100], ease)}%`,
                background: "#b75c2770",
                marginTop: 20,
              }}
            />
          </div>
          <div
            style={{
              background: "#f9fafb",
              minHeight: 465,
              opacity: interpolate(frame, [56, 82], [0, 1], ease),
            }}
          >
            <div
              style={{
                padding: "15px 30px",
                display: "flex",
                justifyContent: "space-between",
                borderBottom: `1px solid ${line}`,
                fontSize: 16,
                color: muted,
              }}
            >
              <span>fact_sales.sql</span>
              <span>Generated artifact · Review before use</span>
            </div>
            <div
              style={{
                padding: "18px 0",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: 24,
                lineHeight: 1.58,
              }}
            >
              {code.map(([text, kind], i) => (
                <div
                  key={text}
                  style={{
                    display: "flex",
                    minHeight: 38,
                    whiteSpace: "pre",
                    background:
                      kind === "highlight"
                        ? `rgba(183,92,39,${interpolate(frame, [95, 125], [0, 0.1], ease)})`
                        : "transparent",
                    opacity: interpolate(
                      frame,
                      [69 + i * 7, 79 + i * 7],
                      [0, 1],
                      ease,
                    ),
                  }}
                >
                  <span
                    style={{
                      width: 68,
                      flexShrink: 0,
                      textAlign: "right",
                      paddingRight: 25,
                      color: "#9ba3a9",
                      userSelect: "none",
                    }}
                  >
                    {i + 1}
                  </span>
                  <span
                    style={{
                      color:
                        kind === "keyword"
                          ? "#956038"
                          : kind === "highlight"
                            ? orange
                            : ink,
                    }}
                  >
                    {text}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </AppFrame>
      </Interactive.Div>
    </Stage>
  );
};
