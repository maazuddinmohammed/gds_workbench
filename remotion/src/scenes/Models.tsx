import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { ease, ink, line, muted, orange, Stage } from "../Design";

export const Models = () => {
  const frame = useCurrentFrame();
  return (
    <Stage chapter="02 / Model">
      <Interactive.Div
        name="Modeling headline"
        style={{
          position: "absolute",
          left: 112,
          top: 161,
          fontSize: 104,
          letterSpacing: -5.5,
          fontWeight: 650,
          opacity: interpolate(frame, [0, 22], [0, 1], ease),
          translate: interpolate(frame, [0, 30], ["0px 30px", "0px 0px"], ease),
        }}
      >
        Give your data structure.
      </Interactive.Div>
      <Interactive.Div
        name="Modeling subtitle"
        style={{
          position: "absolute",
          left: 119,
          top: 299,
          fontSize: 38,
          color: muted,
          opacity: interpolate(frame, [12, 35], [0, 1], ease),
        }}
      >
        Conceptual. Logical. Dimensional.
      </Interactive.Div>
      <div
        style={{
          position: "absolute",
          left: 120,
          top: 399,
          width: 1680,
          height: 543,
        }}
      >
        <svg
          style={{ position: "absolute", inset: 0 }}
          width="1680"
          height="543"
          viewBox="0 0 1680 543"
          fill="none"
        >
          <path
            d="M430 235H635M1045 235H1245"
            stroke="#ded8d0"
            strokeWidth="2"
          />
          <path
            d="M430 235H635M1045 235H1245"
            stroke={orange}
            strokeWidth="3"
            pathLength="1"
            strokeDasharray="1"
            strokeDashoffset={interpolate(frame, [25, 115], [1, 0], ease)}
          />
          <path
            d="m625 228 10 7-10 7M1235 228l10 7-10 7"
            stroke={orange}
            strokeWidth="2"
            opacity={interpolate(frame, [70, 100], [0, 1], ease)}
          />
        </svg>
        {[
          {
            title: "CONCEPTUAL",
            note: "Business concepts",
            x: 0,
            delay: 12,
            nodes: [
              ["Customer", "A person who places orders"],
              ["Order", "A purchase made by a customer"],
            ],
            width: 430,
          },
          {
            title: "LOGICAL",
            note: "Normalized entities",
            x: 625,
            delay: 42,
            nodes: [
              ["core.Customer", "customer_id · name"],
              ["core.Order", "order_id · customer_id"],
              ["core.OrderItem", "order_id · product_id"],
            ],
            width: 420,
          },
          {
            title: "DIMENSIONAL",
            note: "Analytics-ready design",
            x: 1240,
            delay: 88,
            nodes: [
              ["mart.dim_customer", "Customer dimension"],
              ["mart.fact_sales", "Sales at order-item grain"],
              ["mart.dim_product", "Product dimension"],
            ],
            width: 440,
          },
        ].map((group, column) => (
          <div
            key={group.title}
            style={{
              position: "absolute",
              left: group.x,
              top: 0,
              width: group.width,
              opacity: interpolate(
                frame,
                [group.delay, group.delay + 28],
                [0, 1],
                ease,
              ),
              translate: interpolate(
                frame,
                [group.delay, group.delay + 36],
                ["0px 40px", "0px 0px"],
                ease,
              ),
            }}
          >
            <div
              style={{
                fontSize: 18,
                letterSpacing: 2.5,
                color: orange,
                marginBottom: 9,
              }}
            >
              {String(column + 1).padStart(2, "0")} / {group.title}
            </div>
            <div style={{ fontSize: 24, color: muted, marginBottom: 26 }}>
              {group.note}
            </div>
            <div style={{ position: "relative" }}>
              <div
                style={{
                  position: "absolute",
                  width: 2,
                  background: "#cdb39e",
                  left: 27,
                  top: 40,
                  bottom: 40,
                }}
              />
              {group.nodes.map(([name, details], i) => (
                <div
                  key={name}
                  style={{
                    position: "relative",
                    marginBottom: 18,
                    padding: "18px 24px",
                    background: column === 2 && i === 1 ? "#fff1e8" : "#fff",
                    border: `1px solid ${column === 2 && i === 1 ? "#d7aa8f" : line}`,
                    borderRadius: 10,
                    boxShadow: "0 8px 24px #17202a05",
                    opacity: interpolate(
                      frame,
                      [group.delay + i * 9, group.delay + i * 9 + 22],
                      [0, 1],
                      ease,
                    ),
                  }}
                >
                  <div
                    style={{
                      fontSize: 28,
                      lineHeight: 1.25,
                      fontWeight: 650,
                      color: column === 2 && i === 1 ? orange : ink,
                      letterSpacing: -0.8,
                    }}
                  >
                    {name}
                  </div>
                  <div
                    style={{
                      fontSize: 19,
                      lineHeight: 1.3,
                      color: muted,
                      marginTop: 8,
                    }}
                  >
                    {details}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 493,
            color: muted,
            fontSize: 19,
            opacity: interpolate(frame, [138, 163], [0, 1], ease),
          }}
        >
          Grounded in physical evidence and modeling assertions.
        </div>
        <div
          style={{
            position: "absolute",
            right: 0,
            top: 493,
            color: muted,
            fontSize: 19,
          }}
        >
          Illustrated model progression
        </div>
      </div>
    </Stage>
  );
};
