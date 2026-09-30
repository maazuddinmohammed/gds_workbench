import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { AppFrame, ease, ink, line, muted, orange, Stage } from "../Design";

export const Review = () => {
  const frame = useCurrentFrame();
  const applied = frame >= 164;
  const confirming = frame >= 118 && !applied;
  return (
    <Stage chapter="04 / Stay in control">
      <Interactive.Div
        name="Review headline"
        style={{
          position: "absolute",
          left: 112,
          top: 162,
          fontSize: 96,
          letterSpacing: -5,
          fontWeight: 650,
          opacity: interpolate(frame, [0, 22], [0, 1], ease),
          translate: interpolate(frame, [0, 30], ["0px 30px", "0px 0px"], ease),
        }}
      >
        Every change. Yours to review.
      </Interactive.Div>
      <Interactive.Div
        name="Review subtitle"
        style={{
          position: "absolute",
          left: 119,
          top: 295,
          fontSize: 38,
          color: muted,
          opacity: interpolate(frame, [12, 35], [0, 1], ease),
        }}
      >
        Validate. Review. Apply.
      </Interactive.Div>
      <div style={{ position: "absolute", left: 122, top: 435, width: 570 }}>
        <div
          style={{
            position: "absolute",
            top: 32,
            left: 28,
            height: 310,
            width: 2,
            background: "#d9d4cd",
          }}
        />
        <div
          style={{
            position: "absolute",
            top: 32,
            left: 28,
            height: interpolate(frame, [25, 165], [0, 310], ease),
            width: 2,
            background: orange,
          }}
        />
        {["Validate candidate", "Review changes", "Apply explicitly"].map(
          (label, i) => (
            <div
              key={label}
              style={{
                position: "relative",
                display: "flex",
                alignItems: "center",
                gap: 27,
                height: 148,
                opacity: interpolate(
                  frame,
                  [12 + i * 37, 30 + i * 37],
                  [0.3, 1],
                  ease,
                ),
              }}
            >
              <div
                style={{
                  width: 58,
                  height: 58,
                  border: `1px solid ${i === 2 && applied ? "#187252" : "#cdb39e"}`,
                  background: i === 2 && applied ? "#187252" : "#f7f5f2",
                  color: i === 2 && applied ? "#fff" : orange,
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  fontSize: 22,
                  flexShrink: 0,
                }}
              >
                {i === 2 && applied ? "✓" : `0${i + 1}`}
              </div>
              <div
                style={{ fontSize: 31, fontWeight: 600, letterSpacing: -0.7 }}
              >
                {label}
              </div>
            </div>
          ),
        )}
      </div>
      <Interactive.Div
        name="Review workspace"
        style={{
          position: "absolute",
          left: 746,
          top: 406,
          width: 1054,
          height: 523,
          translate: interpolate(frame, [0, 40], ["90px 0px", "0px 0px"], ease),
          opacity: interpolate(frame, [0, 24], [0, 1], ease),
        }}
      >
        <AppFrame
          section="Logical"
          sidebar={false}
          revision={applied ? 13 : 12}
          style={{ height: "100%" }}
        >
          <div style={{ padding: "27px 34px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span style={{ fontSize: 25, fontWeight: 650 }}>
                Logical · {applied ? "Applied" : "Results available"}
              </span>
              <span
                style={{
                  fontSize: 16,
                  color: "#187252",
                  background: "#eaf6f1",
                  padding: "8px 13px",
                  borderRadius: 5,
                }}
              >
                Candidate validated
              </span>
            </div>
            <div style={{ fontSize: 17, color: muted, margin: "17px 0 24px" }}>
              Commerce / Draft based on revision 12
            </div>
            {["2 Logical Entities", "8 Attributes", "1 Relationship"].map(
              (item, i) => (
                <div
                  key={item}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "13px 0",
                    borderTop: `1px solid ${line}`,
                    fontSize: 21,
                    opacity: interpolate(
                      frame,
                      [30 + i * 12, 47 + i * 12],
                      [0, 1],
                      ease,
                    ),
                  }}
                >
                  <span>{item}</span>
                  <span style={{ color: "#187252", fontSize: 17 }}>
                    Ready for review
                  </span>
                </div>
              ),
            )}
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                marginTop: 18,
              }}
            >
              <div
                style={{
                  background: orange,
                  color: "#fff",
                  padding: "13px 25px",
                  fontSize: 19,
                  borderRadius: 6,
                }}
              >
                Apply draft
              </div>
            </div>
          </div>
        </AppFrame>
        {confirming && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "#17202a2e",
              borderRadius: 15,
              display: "grid",
              placeItems: "center",
              opacity: interpolate(frame, [118, 128], [0, 1], ease),
            }}
          >
            <div
              style={{
                width: 695,
                padding: "34px 38px",
                background: "#fff",
                border: `1px solid ${line}`,
                borderRadius: 12,
                boxShadow: "0 18px 70px #17202a20",
              }}
            >
              <div style={{ fontSize: 31, fontWeight: 650 }}>
                Apply this draft?
              </div>
              <div
                style={{
                  fontSize: 21,
                  color: muted,
                  lineHeight: 1.55,
                  margin: "18px 0 28px",
                }}
              >
                Save the reviewed Logical changes
                <br />
                to Commerce at revision 12.
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: 14,
                  fontSize: 19,
                }}
              >
                <div
                  style={{
                    border: `1px solid ${line}`,
                    borderRadius: 6,
                    padding: "13px 22px",
                  }}
                >
                  Cancel
                </div>
                <div
                  style={{
                    background: orange,
                    color: "#fff",
                    borderRadius: 6,
                    padding: "13px 22px",
                  }}
                >
                  Confirm Apply
                </div>
              </div>
            </div>
          </div>
        )}
        {applied && (
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: 132,
              bottom: 0,
              background: "#fff",
              padding: "37px 44px",
              opacity: interpolate(frame, [164, 175], [0, 1], ease),
            }}
          >
            <div style={{ color: "#187252", fontSize: 18, letterSpacing: 2 }}>
              APPLY RECEIPT
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 25,
                marginTop: 20,
              }}
            >
              <div
                style={{
                  width: 55,
                  height: 55,
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  color: "#187252",
                  background: "#eaf6f1",
                  fontSize: 28,
                }}
              >
                ✓
              </div>
              <div style={{ fontSize: 36, fontWeight: 650 }}>
                Changes applied.
              </div>
            </div>
            <div
              style={{
                marginTop: 26,
                paddingTop: 23,
                borderTop: `1px solid ${line}`,
                display: "flex",
                alignItems: "center",
                gap: 25,
              }}
            >
              <span style={{ fontSize: 21, color: muted }}>Model revision</span>
              <span style={{ fontSize: 37, color: muted }}>12</span>
              <span style={{ color: orange, fontSize: 31 }}>→</span>
              <span style={{ fontSize: 46, color: ink, fontWeight: 650 }}>
                13
              </span>
            </div>
          </div>
        )}
        <svg
          style={{
            position: "absolute",
            left: interpolate(
              frame,
              [97, 113, 140, 157],
              [900, 960, 850, 809],
              ease,
            ),
            top: interpolate(
              frame,
              [97, 113, 140, 157],
              [400, 470, 407, 365],
              ease,
            ),
            opacity: interpolate(
              frame,
              [97, 105, 160, 171],
              [0, 1, 1, 0],
              ease,
            ),
          }}
          width="35"
          height="45"
          viewBox="0 0 32 40"
        >
          <path
            d="M3 2 28 24 16 26 11 37Z"
            fill={ink}
            stroke="white"
            strokeWidth="2"
          />
        </svg>
      </Interactive.Div>
    </Stage>
  );
};
