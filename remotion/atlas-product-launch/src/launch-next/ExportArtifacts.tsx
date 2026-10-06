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

export const ExportArtifacts = () => {
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
          right: 96,
          top: 70,
          fontSize: 26,
          letterSpacing: 2.2,
          color: C.accent,
        }}
      >
        REVIEW & HANDOFF
      </div>

      <Interactive.Div
        name="Metadata workbook export"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [0, 0.8 * fps, 6.45 * fps, 7 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <Interactive.Div
          name="Excel export headline"
          style={{
            position: "absolute",
            left: 96,
            top: 173,
            opacity: interpolate(f, [1.1 * fps, 2.3 * fps], [0, 1], motion),
            translate: interpolate(
              f,
              [1.1 * fps, 2.3 * fps],
              ["0px 16px", "0px 0px"],
              motion,
            ),
          }}
        >
          <h1
            style={{
              margin: 0,
              fontSize: 74,
              fontWeight: 650,
              letterSpacing: -1.8,
            }}
          >
            Export metadata to Excel.
          </h1>
          <p style={{ fontSize: 36, color: C.muted, margin: "12px 0 0" }}>
            Take your model forward as a structured workbook.
          </p>
        </Interactive.Div>
        <Interactive.Div
          name="XLSX workbook artifact"
          style={{
            position: "absolute",
            left: 96,
            top: 394,
            width: 354,
            height: 487,
            borderRadius: 24,
            border: `2px solid ${C.line}`,
            background: C.white,
            display: "flex",
            alignItems: "center",
            flexDirection: "column",
            boxSizing: "border-box",
            padding: "52px 25px 36px",
            opacity: interpolate(f, [2.5 * fps, 3.7 * fps], [0, 1], motion),
          }}
        >
          <svg
            width="148"
            height="183"
            viewBox="0 0 148 183"
            fill="none"
            aria-label="Excel workbook file"
          >
            <path
              d="M14 3h83l37 37v137H14Z"
              fill="#E6EEE4"
              stroke={C.green}
              strokeWidth="3"
              strokeLinejoin="round"
            />
            <path
              d="M97 3v37h37"
              stroke={C.green}
              strokeWidth="3"
              strokeLinejoin="round"
            />
            <rect x="0" y="68" width="103" height="59" rx="9" fill={C.green} />
            <text
              x="51"
              y="107"
              textAnchor="middle"
              fill={C.white}
              fontSize="28"
              fontWeight="700"
              fontFamily="Source Sans 3"
            >
              XLSX
            </text>
            <path
              d="M35 146h76M35 160h50"
              stroke={C.green}
              strokeWidth="3"
              strokeLinecap="round"
            />
          </svg>
          <div style={{ marginTop: 31, fontSize: 36, fontWeight: 650 }}>
            Metadata.xlsx
          </div>
          <div
            style={{
              color: C.muted,
              fontSize: 28,
              marginTop: 17,
              textAlign: "center",
              lineHeight: 1.4,
            }}
          >
            Objects and Attributes
            <br />
            Ready for review
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Actual Excel export dialog camera"
          style={{
            position: "absolute",
            left: 526,
            top: 362,
            width: 1298,
            height: 580,
            borderRadius: 24,
            border: `2px solid ${C.line}`,
            overflow: "hidden",
            background: "#DDDFD9",
            boxShadow: "0 24px 65px #233A3419",
          }}
        >
          <Interactive.Div
            name="Zoomed real metadata export"
            style={{
              position: "absolute",
              inset: 0,
              scale: interpolate(f, [0.15 * fps, 2.1 * fps], [0.96, 1], {
                ...motion,
                output: "perceptual-scale",
              }),
            }}
          >
            <CanvasImage
              src={staticFile("captures/complete/export-excel.png")}
              style={{
                position: "absolute",
                width: 2765.34,
                height: 1555.2,
                left: -733.67,
                top: -487.6,
              }}
            />
          </Interactive.Div>
        </Interactive.Div>
      </Interactive.Div>

      <Interactive.Div
        name="SQL file export"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [7 * fps, 7.8 * fps, 13.45 * fps, 14 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <Interactive.Div
          name="SQL handoff headline"
          style={{
            position: "absolute",
            left: 96,
            top: 173,
            opacity: interpolate(f, [8.1 * fps, 9.3 * fps], [0, 1], motion),
            translate: interpolate(
              f,
              [8.1 * fps, 9.3 * fps],
              ["0px 16px", "0px 0px"],
              motion,
            ),
          }}
        >
          <h1
            style={{
              margin: 0,
              fontSize: 74,
              fontWeight: 650,
              letterSpacing: -1.8,
            }}
          >
            Review context. Export SQL.
          </h1>
          <p style={{ fontSize: 36, color: C.muted, margin: "12px 0 0" }}>
            See when inputs have changed. Review before reuse.
          </p>
        </Interactive.Div>
        <Interactive.Div
          name="SQL file artifact"
          style={{
            position: "absolute",
            left: 96,
            top: 394,
            width: 354,
            height: 487,
            borderRadius: 24,
            border: `2px solid ${C.line}`,
            background: C.white,
            display: "flex",
            alignItems: "center",
            flexDirection: "column",
            boxSizing: "border-box",
            padding: "52px 25px 36px",
            opacity: interpolate(f, [9.5 * fps, 10.7 * fps], [0, 1], motion),
          }}
        >
          <svg
            width="148"
            height="183"
            viewBox="0 0 148 183"
            fill="none"
            aria-label="SQL source file"
          >
            <path
              d="M14 3h83l37 37v137H14Z"
              fill={C.pale}
              stroke={C.accent}
              strokeWidth="3"
              strokeLinejoin="round"
            />
            <path
              d="M97 3v37h37"
              stroke={C.accent}
              strokeWidth="3"
              strokeLinejoin="round"
            />
            <rect x="0" y="68" width="103" height="59" rx="9" fill={C.accent} />
            <text
              x="51"
              y="107"
              textAnchor="middle"
              fill={C.white}
              fontSize="30"
              fontWeight="700"
              fontFamily="Source Sans 3"
            >
              SQL
            </text>
            <path
              d="M35 146h76M35 160h50"
              stroke={C.accent}
              strokeWidth="3"
              strokeLinecap="round"
            />
          </svg>
          <div style={{ marginTop: 31, fontSize: 36, fontWeight: 650 }}>
            Generated SQL
          </div>
          <div
            style={{
              color: C.muted,
              fontSize: 28,
              marginTop: 17,
              textAlign: "center",
              lineHeight: 1.4,
            }}
          >
            Portable source files
            <br />
            Review before reuse
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Actual saved SQL files camera"
          style={{
            position: "absolute",
            left: 526,
            top: 362,
            width: 1298,
            height: 580,
            borderRadius: 24,
            border: `2px solid ${C.line}`,
            overflow: "hidden",
            background: C.white,
            boxShadow: "0 24px 65px #233A3419",
          }}
        >
          <Interactive.Div
            name="Zoomed real SQL file workspace"
            style={{
              position: "absolute",
              inset: 0,
              scale: interpolate(f, [7.15 * fps, 9.1 * fps], [0.96, 1], {
                ...motion,
                output: "perceptual-scale",
              }),
            }}
          >
            <CanvasImage
              src={staticFile("captures/complete/export-code.png")}
              style={{
                position: "absolute",
                width: 2475.15,
                height: 1392,
                left: interpolate(
                  f,
                  [10.4 * fps, 11.8 * fps],
                  [-345, -1170],
                  motion,
                ),
                top: -385,
              }}
            />
            <Interactive.Div
              name="Actual SQL download control emphasis"
              style={{
                position: "absolute",
                left: 923,
                top: 98,
                width: 161,
                height: 61,
                boxSizing: "border-box",
                border: `3px solid ${C.accent}`,
                borderRadius: 13,
                boxShadow: "0 0 0 6px #BC603E15",
                opacity: interpolate(
                  f,
                  [11.8 * fps, 12.5 * fps],
                  [0, 1],
                  motion,
                ),
              }}
            />
          </Interactive.Div>
        </Interactive.Div>
      </Interactive.Div>
    </AbsoluteFill>
  );
};
