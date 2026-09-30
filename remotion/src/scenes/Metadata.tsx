import { Interactive, interpolate, useCurrentFrame } from "remotion";
import {
  AppFrame,
  ease,
  ink,
  line,
  muted,
  ObjectLedger,
  orange,
  Stage,
} from "../Design";

export const Metadata = () => {
  const frame = useCurrentFrame();
  return (
    <Stage chapter="01 / Understand">
      <Interactive.Div
        name="Metadata headline"
        style={{
          position: "absolute",
          left: 112,
          top: 162,
          fontSize: 104,
          letterSpacing: -5.5,
          fontWeight: 650,
          opacity: interpolate(frame, [0, 22], [0, 1], ease),
          translate: interpolate(frame, [0, 30], ["0px 30px", "0px 0px"], ease),
        }}
      >
        Know your starting point.
      </Interactive.Div>
      <Interactive.Div
        name="Metadata subtitle"
        style={{
          position: "absolute",
          left: 119,
          top: 299,
          fontSize: 38,
          color: muted,
          opacity: interpolate(frame, [12, 35], [0, 1], ease),
        }}
      >
        Explore metadata. Profile attributes. Enrich context.
      </Interactive.Div>
      <Interactive.Div
        name="Metadata workspace"
        style={{
          position: "absolute",
          left: 120,
          top: 399,
          width: 1680,
          height: 548,
          translate: interpolate(frame, [0, 40], ["0px 80px", "0px 0px"], ease),
          opacity: interpolate(frame, [0, 24], [0, 1], ease),
        }}
      >
        <AppFrame section="Metadata" style={{ height: "100%" }}>
          <div style={{ display: "flex", height: "calc(100% - 57px)" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <ObjectLedger compact />
            </div>
            <div
              style={{
                width: 555,
                borderLeft: `1px solid ${line}`,
                padding: "27px 32px",
                background: "#fdfcfb",
                translate: interpolate(
                  frame,
                  [40, 72],
                  ["70px 0px", "0px 0px"],
                  ease,
                ),
                opacity: interpolate(frame, [40, 62], [0, 1], ease),
              }}
            >
              <div style={{ color: orange, fontSize: 15, letterSpacing: 1.6 }}>
                ATTRIBUTE PROFILE
              </div>
              <div style={{ fontSize: 29, fontWeight: 650, marginTop: 12 }}>
                orders.customer_id
              </div>
              <div style={{ fontSize: 17, color: muted, marginTop: 7 }}>
                Customer placing the order · INTEGER
              </div>
              <div style={{ display: "flex", marginTop: 31, gap: 40 }}>
                <div>
                  <div style={{ fontSize: 16, color: muted }}>
                    Rows profiled
                  </div>
                  <div style={{ fontSize: 42, fontWeight: 600, marginTop: 4 }}>
                    100,000
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 16, color: muted }}>
                    Distinct values
                  </div>
                  <div style={{ fontSize: 42, fontWeight: 600, marginTop: 4 }}>
                    24,860
                  </div>
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginTop: 30,
                  fontSize: 17,
                }}
              >
                <span>Non-null values</span>
                <strong style={{ color: "#187252" }}>100%</strong>
              </div>
              <div
                style={{
                  height: 8,
                  marginTop: 14,
                  background: "#e6ede9",
                  borderRadius: 4,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${interpolate(frame, [70, 115], [0, 100], ease)}%`,
                    background: "#187252",
                  }}
                />
              </div>
              <div style={{ fontSize: 15, color: muted, marginTop: 22 }}>
                Measured profile · All rows · Demo dataset
              </div>
            </div>
          </div>
        </AppFrame>
      </Interactive.Div>
      <div
        style={{
          position: "absolute",
          left: 1658,
          top: 874,
          opacity: interpolate(frame, [95, 111, 140, 160], [0, 1, 1, 0], ease),
          translate: interpolate(
            frame,
            [95, 140],
            ["20px 35px", "0px 0px"],
            ease,
          ),
        }}
      >
        <svg width="40" height="47" viewBox="0 0 32 40">
          <path
            d="M3 2 28 24 16 26 11 37Z"
            fill={ink}
            stroke="white"
            strokeWidth="2"
          />
        </svg>
      </div>
    </Stage>
  );
};
