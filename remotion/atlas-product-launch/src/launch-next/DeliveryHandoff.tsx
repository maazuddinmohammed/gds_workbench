import { useId } from "react";
import {
  AbsoluteFill,
  Interactive,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, Icon, Logo } from "../design";
import { motion } from "./MeetLayout";

/** Platform deployment is an explicit handoff, separate from Atlas Apply. */
export const DeliveryHandoff = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const markerId = useId();
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
          top: 72,
          color: C.accent,
          fontSize: 24,
          letterSpacing: 2.2,
        }}
      >
        THE DELIVERY LIFECYCLE
      </div>
      <Interactive.Div
        name="Explain the platform handoff"
        style={{
          position: "absolute",
          left: 96,
          top: 170,
          right: 96,
          opacity: interpolate(
            f,
            [2.2 * fps, 3.3 * fps, 8.3 * fps, 9 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <h1
          style={{
            margin: 0,
            fontSize: 76,
            fontWeight: 650,
            letterSpacing: -2,
            lineHeight: 1.08,
          }}
        >
          From artifacts to platform.
        </h1>
        <p style={{ margin: "20px 0 0", fontSize: 36, color: C.muted }}>
          Deploy SQL files. Register targets and Process metadata.
        </p>
      </Interactive.Div>
      <Interactive.Div
        name="Explain the ongoing GDS lifecycle"
        style={{
          position: "absolute",
          left: 96,
          top: 170,
          right: 96,
          opacity: interpolate(f, [10.5 * fps, 11.7 * fps], [0, 1], motion),
        }}
      >
        <h1
          style={{
            margin: 0,
            fontSize: 76,
            fontWeight: 650,
            letterSpacing: -2,
            lineHeight: 1.08,
          }}
        >
          Keep the lifecycle connected.
        </h1>
        <p style={{ margin: "20px 0 0", fontSize: 36, color: C.muted }}>
          GDS uses Process metadata to run and maintain pipelines.
        </p>
      </Interactive.Div>
      <Interactive.Div
        name="Reviewed artifacts move through a separate platform handoff"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [0, 0.8 * fps, 8.3 * fps, 9.1 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <Interactive.Div
          name="Reviewed Atlas artifacts"
          style={{
            position: "absolute",
            left: 130,
            top: 420,
            width: 420,
            height: 280,
            border: `2px solid ${C.line}`,
            borderRadius: 26,
            background: C.white,
            boxSizing: "border-box",
            padding: "30px 34px",
          }}
        >
          <Icon kind="code" size={58} color={C.accent} />
          <div style={{ fontSize: 35, fontWeight: 650, marginTop: 22 }}>
            Reviewed artifacts
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              fontSize: 28,
              color: C.muted,
              marginTop: 17,
            }}
          >
            <Icon kind="file" size={26} color={C.green} />
            SQL files
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              fontSize: 28,
              color: C.muted,
              marginTop: 8,
            }}
          >
            <Icon kind="model" size={26} color={C.green} />
            Model metadata
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Platform deployment and target registration"
          style={{
            position: "absolute",
            left: 750,
            top: 420,
            width: 420,
            height: 280,
            border: "2px solid #D4B79E",
            borderRadius: 26,
            background: "#FBF5EE",
            boxSizing: "border-box",
            padding: "30px 34px",
            opacity: interpolate(f, [0.6 * fps, 1.6 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="layers" size={58} color={C.accent} />
          <div style={{ fontSize: 35, fontWeight: 650, marginTop: 22 }}>
            Platform handoff
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 17 }}>
            Deploy SQL files
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 8 }}>
            Register targets
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Register Process metadata for GDS"
          style={{
            position: "absolute",
            left: 1370,
            top: 420,
            width: 420,
            height: 280,
            border: "2px solid #B7C9B8",
            borderRadius: 26,
            background: C.white,
            boxSizing: "border-box",
            padding: "30px 34px",
            opacity: interpolate(f, [1.2 * fps, 2.2 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="document" size={58} color={C.green} />
          <div style={{ fontSize: 35, fontWeight: 650, marginTop: 22 }}>
            Process metadata
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 17 }}>
            Execution order
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 8 }}>
            Pipeline configuration
          </div>
        </Interactive.Div>
      </Interactive.Div>
      <Interactive.Div
        name="The ongoing review, metadata and pipeline lifecycle"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(f, [9.3 * fps, 10.5 * fps], [0, 1], motion),
        }}
      >
        <Interactive.Div
          name="Review and update the definitions in Atlas"
          style={{
            position: "absolute",
            left: 130,
            top: 420,
            width: 420,
            height: 280,
            border: "2px solid #D4B79E",
            borderRadius: 26,
            background: C.white,
            boxSizing: "border-box",
            padding: "30px 34px",
          }}
        >
          <Logo size={58} word={false} />
          <div style={{ fontSize: 35, fontWeight: 650, marginTop: 22 }}>
            Review &amp; update
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 17 }}>
            Model · Mapping · SQL
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 8 }}>
            Validation definitions
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Maintain the platform Process metadata"
          style={{
            position: "absolute",
            left: 750,
            top: 420,
            width: 420,
            height: 280,
            border: "2px solid #B7C9B8",
            borderRadius: 26,
            background: C.white,
            boxSizing: "border-box",
            padding: "30px 34px",
          }}
        >
          <Icon kind="document" size={58} color={C.green} />
          <div style={{ fontSize: 35, fontWeight: 650, marginTop: 22 }}>
            Process metadata
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 17 }}>
            Execution order
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 8 }}>
            Pipeline configuration
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="GDS runs and maintains the pipelines"
          style={{
            position: "absolute",
            left: 1370,
            top: 420,
            width: 420,
            height: 280,
            border: "2px solid #7CA18C",
            borderRadius: 26,
            background: "#ECF2E9",
            boxSizing: "border-box",
            padding: "30px 34px",
          }}
        >
          <Icon kind="layers" size={58} color={C.green} />
          <div style={{ fontSize: 35, fontWeight: 650, marginTop: 22 }}>
            GDS Framework
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 17 }}>
            Runs pipelines
          </div>
          <div style={{ fontSize: 28, color: C.muted, marginTop: 8 }}>
            Maintains lakehouse data
          </div>
        </Interactive.Div>
      </Interactive.Div>
      <svg
        width={1920}
        height={1080}
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      >
        <defs>
          <marker
            id={markerId}
            viewBox="0 0 12 12"
            refX="10"
            refY="6"
            markerWidth="6"
            markerHeight="6"
            orient="auto"
          >
            <path
              d="M2 2L10 6L2 10"
              fill="none"
              stroke={C.green}
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </marker>
        </defs>
        <g
          style={{
            opacity: interpolate(
              f,
              [
                2.2 * fps,
                3.4 * fps,
                8.3 * fps,
                9.1 * fps,
                11 * fps,
                12.3 * fps,
              ],
              [0, 1, 1, 0, 0, 1],
              motion,
            ),
          }}
        >
          <path
            d="M586 560H714"
            fill="none"
            stroke={C.green}
            strokeWidth={3}
            strokeLinecap="round"
            markerEnd={`url(#${markerId})`}
          />
          <path
            d="M1206 560H1334"
            fill="none"
            stroke={C.green}
            strokeWidth={3}
            strokeLinecap="round"
            markerEnd={`url(#${markerId})`}
          />
        </g>
        <path
          d="M1580 738V780Q1580 810 1550 810H370Q340 810 340 780V738"
          fill="none"
          stroke={C.green}
          strokeWidth={3}
          strokeLinecap="round"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={interpolate(
            f,
            [13 * fps, 15.5 * fps],
            [1, 0],
            motion,
          )}
          markerEnd={`url(#${markerId})`}
          opacity={interpolate(f, [13 * fps, 14 * fps], [0, 1], motion)}
        />
      </svg>
      <Interactive.Div
        name="Platform handoff remains explicit in the lifecycle"
        style={{
          position: "absolute",
          left: 570,
          top: 508,
          width: 160,
          textAlign: "center",
          fontSize: 25,
          color: C.green,
          opacity: interpolate(f, [11 * fps, 12.3 * fps], [0, 1], motion),
        }}
      >
        Handoff
      </Interactive.Div>
      <Interactive.Div
        name="The next change returns to review"
        style={{
          position: "absolute",
          left: 520,
          right: 520,
          top: 845,
          textAlign: "center",
          fontSize: 31,
          fontWeight: 600,
          color: C.green,
          opacity: interpolate(f, [14.5 * fps, 15.7 * fps], [0, 1], motion),
        }}
      >
        Review the next change.
      </Interactive.Div>
      <Interactive.Div
        name="Deployment and registration boundary"
        style={{
          position: "absolute",
          left: 96,
          right: 96,
          top: 971,
          textAlign: "center",
          fontSize: 28,
          color: C.muted,
          opacity: interpolate(f, [3.2 * fps, 4.5 * fps], [0, 1], motion),
        }}
      >
        Deployment and registration are platform steps.
      </Interactive.Div>
    </AbsoluteFill>
  );
};
