import {
  AbsoluteFill,
  CanvasImage,
  Interactive,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, Logo } from "../design";
import { motion } from "./MeetLayout";

/** Camera and annotations use the real navigation bounds in nav-boxes.json. */
export const WorkspaceTour = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{
        background: C.paper,
        color: C.ink,
        fontFamily: '"Source Sans 3", sans-serif',
        overflow: "hidden",
      }}
    >
      <div style={{ position: "absolute", left: 96, top: 62 }}>
        <Logo size={48} />
      </div>
      <div
        style={{
          position: "absolute",
          right: 100,
          top: 76,
          color: C.muted,
          fontSize: 22,
          letterSpacing: 2.5,
        }}
      >
        02 / THE WORKSPACE
      </div>

      <Interactive.Div
        name="Introduce the actual Atlas workspace"
        style={{
          position: "absolute",
          left: 96,
          top: 150,
          right: 96,
          opacity: interpolate(
            f,
            [0.3 * fps, 1.2 * fps, 2.8 * fps, 3.6 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <div
          style={{
            fontSize: 68,
            lineHeight: 1.05,
            fontWeight: 600,
            letterSpacing: -1.7,
          }}
        >
          One connected workspace.
        </div>
        <div style={{ fontSize: 32, color: C.muted, marginTop: 20 }}>
          Your model, its evidence, and the work ahead.
        </div>
      </Interactive.Div>
      <Interactive.Div
        name="Explain the context and scope sections"
        style={{
          position: "absolute",
          left: 96,
          top: 150,
          right: 96,
          opacity: interpolate(
            f,
            [4.5 * fps, 5.4 * fps, 8.4 * fps, 9.1 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <div
          style={{
            fontSize: 68,
            lineHeight: 1.05,
            fontWeight: 600,
            letterSpacing: -1.7,
          }}
        >
          Set context and scope.
        </div>
        <div style={{ fontSize: 34, color: C.muted, marginTop: 20 }}>
          Overview, settings, input scope, and assertions.
        </div>
      </Interactive.Div>
      <Interactive.Div
        name="Explain the evidence sections"
        style={{
          position: "absolute",
          left: 96,
          top: 150,
          right: 96,
          opacity: interpolate(
            f,
            [10 * fps, 10.9 * fps, 14.4 * fps, 15.1 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <div
          style={{
            fontSize: 68,
            lineHeight: 1.05,
            fontWeight: 600,
            letterSpacing: -1.7,
          }}
        >
          Turn sources into understanding.
        </div>
        <div style={{ fontSize: 34, color: C.muted, marginTop: 20 }}>
          Profile, enrich, analyze, and establish the business concepts.
        </div>
      </Interactive.Div>
      <Interactive.Div
        name="Explain the model design sections"
        style={{
          position: "absolute",
          left: 96,
          top: 150,
          right: 96,
          opacity: interpolate(
            f,
            [16 * fps, 16.9 * fps, 20.4 * fps, 21.1 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <div
          style={{
            fontSize: 68,
            lineHeight: 1.05,
            fontWeight: 600,
            letterSpacing: -1.7,
          }}
        >
          Design the connected models.
        </div>
        <div style={{ fontSize: 34, color: C.muted, marginTop: 20 }}>
          Operational structure, followed by dimensional design.
        </div>
      </Interactive.Div>
      <Interactive.Div
        name="Explain the delivery sections"
        style={{
          position: "absolute",
          left: 96,
          top: 150,
          right: 96,
          opacity: interpolate(f, [22 * fps, 22.9 * fps], [0, 1], motion),
        }}
      >
        <div
          style={{
            fontSize: 68,
            lineHeight: 1.05,
            fontWeight: 600,
            letterSpacing: -1.7,
          }}
        >
          Carry the design into delivery.
        </div>
        <div style={{ fontSize: 34, color: C.muted, marginTop: 20 }}>
          Transformation mappings, SQL artifacts, and validation definitions.
        </div>
      </Interactive.Div>

      <Interactive.Div
        name="Actual workspace camera viewport"
        style={{
          position: "absolute",
          left: interpolate(f, [3 * fps, 4.8 * fps], [370, 96], motion),
          top: interpolate(f, [3 * fps, 4.8 * fps], [300, 330], motion),
          width: interpolate(f, [3 * fps, 4.8 * fps], [1180, 1728], motion),
          height: interpolate(f, [3 * fps, 4.8 * fps], [664, 600], motion),
          borderRadius: 22,
          border: `1px solid ${C.line}`,
          boxShadow: "0 24px 60px #233A3418",
          overflow: "hidden",
          background: C.white,
          opacity: interpolate(f, [0, 0.8 * fps], [0, 1], motion),
        }}
      >
        <Interactive.Div
          name="Pan across the actual model navigation"
          style={{
            position: "absolute",
            width: 1707,
            height: 960,
            transformOrigin: "0 0",
            scale: interpolate(f, [3 * fps, 4.8 * fps], [1180 / 1707, 1.9], {
              ...motion,
              output: "perceptual-scale",
            }),
            left: interpolate(
              f,
              [
                3 * fps,
                4.8 * fps,
                8.5 * fps,
                10.2 * fps,
                14.5 * fps,
                16.2 * fps,
                20.5 * fps,
                22.2 * fps,
              ],
              [
                0, -46.45, -46.45, -831.03, -831.03, -1443.28, -1443.28,
                -1515.3,
              ],
              motion,
            ),
            top: interpolate(f, [3 * fps, 4.8 * fps], [0, -236.2], motion),
          }}
        >
          <CanvasImage
            src={staticFile("captures/complete/overview.png")}
            style={{ position: "absolute", inset: 0, width: 1707, height: 960 }}
          />
          <Interactive.Div
            name="Highlight each connected group of actual tabs"
            style={{
              position: "absolute",
              top: 155,
              height: 128,
              left: interpolate(
                f,
                [
                  8.5 * fps,
                  10.2 * fps,
                  14.5 * fps,
                  16.2 * fps,
                  20.5 * fps,
                  22.2 * fps,
                ],
                [279.59, 665.16, 665.16, 1092.68, 1092.68, 1322.43],
                motion,
              ),
              width: interpolate(
                f,
                [
                  8.5 * fps,
                  10.2 * fps,
                  14.5 * fps,
                  16.2 * fps,
                  20.5 * fps,
                  22.2 * fps,
                ],
                [399.18, 453.93, 453.93, 243.36, 243.36, 379.46],
                motion,
              ),
              border: `2px solid ${C.accent}`,
              boxSizing: "border-box",
              borderRadius: 12,
              boxShadow: "0 0 0 2400px #233A3430, 0 6px 16px #BC603E18",
              background: "#BC603E06",
              opacity: interpolate(f, [3.4 * fps, 4.8 * fps], [0, 1], motion),
            }}
          />
          <Interactive.Div
            name="Follow the highlighted workspace progression"
            style={{
              position: "absolute",
              top: 294,
              left: interpolate(
                f,
                [
                  4.8 * fps,
                  7.8 * fps,
                  8.5 * fps,
                  10.2 * fps,
                  13.8 * fps,
                  14.5 * fps,
                  16.2 * fps,
                  19.8 * fps,
                  20.5 * fps,
                  22.2 * fps,
                  27 * fps,
                ],
                [303, 647, 647, 689, 1087, 1087, 1117, 1305, 1305, 1346, 1671],
                motion,
              ),
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: C.accent,
              boxShadow: "0 0 0 4px #BC603E18",
              opacity: interpolate(f, [4.8 * fps, 5.6 * fps], [0, 1], motion),
            }}
          />
        </Interactive.Div>
      </Interactive.Div>
      <Interactive.Div
        name="Workspace progression legend"
        style={{
          position: "absolute",
          left: 96,
          right: 96,
          top: 970,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 24,
          fontSize: 28,
          color: C.muted,
          opacity: interpolate(f, [4.8 * fps, 5.7 * fps], [0, 1], motion),
        }}
      >
        {[
          ["Context", 3, 8.5],
          ["Evidence", 8.5, 14.5],
          ["Models", 14.5, 20.5],
          ["Delivery", 20.5, 28.5],
        ].map(([label, start, end], index) => (
          <div
            key={label}
            style={{ display: "flex", alignItems: "center", gap: 24 }}
          >
            {index ? <span style={{ color: "#ACB5AD" }}>→</span> : null}
            <span
              style={{
                color:
                  f >= Number(start) * fps && f < Number(end) * fps
                    ? C.accent
                    : C.muted,
                fontWeight:
                  f >= Number(start) * fps && f < Number(end) * fps ? 700 : 400,
              }}
            >
              {label}
            </span>
          </div>
        ))}
      </Interactive.Div>
    </AbsoluteFill>
  );
};
