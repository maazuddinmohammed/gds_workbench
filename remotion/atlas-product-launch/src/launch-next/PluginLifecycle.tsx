import {
  AbsoluteFill,
  CanvasImage,
  Interactive,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, Icon, Logo } from "../design";
import { motion } from "./MeetLayout";

/** Illustrative conversations; Stage, validation and Apply remain separate checkpoints. */
export const PluginLifecycle = () => {
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
          top: 69,
          fontSize: 26,
          letterSpacing: 2.2,
          color: C.accent,
        }}
      >
        ILLUSTRATIVE WORKFLOW · AT-142
      </div>

      <Interactive.Div
        name="A ticket becomes a focused Atlas request"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [0, 0.8 * fps, 8.35 * fps, 9 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <Interactive.Div
          name="Ticket headline"
          style={{
            position: "absolute",
            left: 96,
            top: 173,
            opacity: interpolate(f, [1.1 * fps, 2.3 * fps], [0, 1], motion),
            translate: interpolate(
              f,
              [1.1 * fps, 2.3 * fps],
              ["0px 18px", "0px 0px"],
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
            Start with the change you need.
          </h1>
          <p style={{ fontSize: 36, margin: "12px 0 0", color: C.muted }}>
            Investigate an issue. Evolve a requirement.
          </p>
        </Interactive.Div>
        <Interactive.Div
          name="Illustrated Copilot request"
          style={{
            position: "absolute",
            left: 96,
            top: 375,
            width: 1050,
            height: 564,
            borderRadius: 24,
            background: "#192B29",
            boxShadow: "0 24px 70px #233A3418",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: 75,
              borderBottom: "1px solid #3C514B",
              display: "flex",
              alignItems: "center",
              padding: "0 34px",
              gap: 16,
              color: "#CADAD2",
              fontSize: 26,
            }}
          >
            <Icon kind="code" size={30} color="#A2C2D5" /> VS CODE{" "}
            <span style={{ color: "#6A837B" }}> / </span> Copilot Chat{" "}
            <span style={{ marginLeft: "auto", color: "#D7B48C" }}>
              Atlas Plugin
            </span>
          </div>
          <Interactive.Div
            name="Ticket request text"
            style={{
              margin: "32px 34px 0",
              border: "1px solid #5C7066",
              borderRadius: 16,
              background: "#243F36",
              padding: "25px 30px",
              opacity: interpolate(f, [0.5 * fps, 1.5 * fps], [0, 1], motion),
            }}
          >
            <div style={{ fontSize: 24, color: "#BFCFC4", marginBottom: 9 }}>
              YOU · TICKET AT-142
            </div>
            <div
              style={{
                fontSize: 37,
                lineHeight: 1.28,
                fontWeight: 600,
                color: C.white,
              }}
            >
              Add customer segment.
            </div>
            <div
              style={{
                fontSize: 35,
                lineHeight: 1.3,
                color: C.paper,
                marginTop: 9,
              }}
            >
              Keep model, mapping, SQL
              <br />
              and checks aligned.
            </div>
          </Interactive.Div>
          <Interactive.Div
            name="Atlas investigates the relevant evidence"
            style={{
              margin: "30px 64px 0",
              opacity: interpolate(f, [3.9 * fps, 5.1 * fps], [0, 1], motion),
            }}
          >
            <div style={{ fontSize: 24, color: "#D7B48C", marginBottom: 9 }}>
              ATLAS
            </div>
            <div style={{ color: C.paper, fontSize: 33, lineHeight: 1.34 }}>
              Reviewing the saved model and metadata.
              <br />
              Tracing the affected dependencies.
            </div>
          </Interactive.Div>
        </Interactive.Div>
        <Interactive.Div
          name="A focused evidence review"
          style={{
            position: "absolute",
            left: 1240,
            top: 375,
            width: 584,
            height: 564,
            border: `2px solid ${C.line}`,
            boxSizing: "border-box",
            borderRadius: 24,
            background: C.white,
            padding: "42px 46px",
            opacity: interpolate(f, [4.4 * fps, 5.6 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="search" size={62} color={C.accent} />
          <h2
            style={{
              fontSize: 43,
              lineHeight: 1.1,
              margin: "28px 0 30px",
              fontWeight: 650,
            }}
          >
            Ground the change.
          </h2>
          <div style={{ fontSize: 34, lineHeight: 1.55 }}>
            Applied model
            <br />
            Source metadata
            <br />
            Affected artifacts
          </div>
          <div
            style={{
              borderTop: `1px solid ${C.line}`,
              marginTop: 33,
              paddingTop: 23,
              fontSize: 28,
              color: C.muted,
            }}
          >
            Preserve existing decisions
            <br />
            and protected records.
          </div>
        </Interactive.Div>
      </Interactive.Div>

      <Interactive.Div
        name="Changes follow applied dependencies"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [9 * fps, 9.8 * fps, 17.35 * fps, 18 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <Interactive.Div
          name="Dependency-aware authoring headline"
          style={{
            position: "absolute",
            left: 96,
            top: 173,
            opacity: interpolate(f, [10.2 * fps, 11.4 * fps], [0, 1], motion),
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
            Keep the artifacts connected.
          </h1>
          <p style={{ fontSize: 36, margin: "12px 0 0", color: C.muted }}>
            Review each dependency. Carry approved inputs forward.
          </p>
        </Interactive.Div>
        <Interactive.Div
          name="Applied model input"
          style={{
            position: "absolute",
            left: 96,
            top: 414,
            width: 390,
            height: 400,
            padding: 34,
            boxSizing: "border-box",
            borderRadius: 22,
            background: C.white,
            border: `2px solid ${C.green}`,
            opacity: interpolate(f, [9.3 * fps, 10.4 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="model" size={59} color={C.green} />
          <h2 style={{ fontSize: 42, margin: "20px 0 22px" }}>Model</h2>
          <div
            style={{
              borderLeft: `4px solid ${C.accent}`,
              paddingLeft: 17,
              fontSize: 33,
              lineHeight: 1.3,
            }}
          >
            Customer
            <br />
            <strong>segment</strong>
          </div>
          <div
            style={{
              position: "absolute",
              bottom: 31,
              fontSize: 27,
              color: C.green,
            }}
          >
            Applied input
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Model to mapping connection"
          style={{
            position: "absolute",
            left: 494,
            top: 583,
            opacity: interpolate(f, [11.5 * fps, 12.3 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="arrow" size={39} color={C.accent} />
        </Interactive.Div>
        <Interactive.Div
          name="Applied mapping input"
          style={{
            position: "absolute",
            left: 542,
            top: 414,
            width: 390,
            height: 400,
            padding: 34,
            boxSizing: "border-box",
            borderRadius: 22,
            background: C.white,
            border: `2px solid ${C.green}`,
            opacity: interpolate(f, [11.2 * fps, 12.4 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="layers" size={59} color={C.green} />
          <h2 style={{ fontSize: 42, margin: "20px 0 22px" }}>Mapping</h2>
          <div style={{ fontSize: 33, lineHeight: 1.35 }}>
            Source rule
            <br />
            <span style={{ color: C.accent }}>↓</span> Target attribute
          </div>
          <div
            style={{
              position: "absolute",
              bottom: 31,
              fontSize: 27,
              color: C.green,
            }}
          >
            Applied input
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Mapping to SQL connection"
          style={{
            position: "absolute",
            left: 940,
            top: 583,
            opacity: interpolate(f, [13.2 * fps, 14 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="arrow" size={39} color={C.accent} />
        </Interactive.Div>
        <Interactive.Div
          name="SQL draft matches mapping"
          style={{
            position: "absolute",
            left: 988,
            top: 414,
            width: 390,
            height: 400,
            padding: 34,
            boxSizing: "border-box",
            borderRadius: 22,
            background: C.white,
            border: `2px solid ${C.line}`,
            opacity: interpolate(f, [13 * fps, 14.2 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="code" size={59} color={C.accent} />
          <h2 style={{ fontSize: 42, margin: "20px 0 22px" }}>SQL</h2>
          <div style={{ fontSize: 33, lineHeight: 1.35 }}>
            Saved rules
            <br />
            become code.
          </div>
          <div
            style={{
              position: "absolute",
              bottom: 31,
              fontSize: 27,
              color: C.accent,
            }}
          >
            Draft for review
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="SQL and validation alignment"
          style={{
            position: "absolute",
            left: 1386,
            top: 583,
            opacity: interpolate(f, [14.6 * fps, 15.4 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="arrow" size={39} color={C.accent} />
        </Interactive.Div>
        <Interactive.Div
          name="Validation definitions for the change"
          style={{
            position: "absolute",
            left: 1434,
            top: 414,
            width: 390,
            height: 400,
            padding: 34,
            boxSizing: "border-box",
            borderRadius: 22,
            background: C.white,
            border: `2px solid ${C.line}`,
            opacity: interpolate(f, [14.4 * fps, 15.6 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="check" size={59} color={C.accent} />
          <h2 style={{ fontSize: 42, margin: "20px 0 22px" }}>Checks</h2>
          <div style={{ fontSize: 33, lineHeight: 1.35 }}>
            Validation
            <br />
            for the change.
          </div>
          <div
            style={{
              position: "absolute",
              bottom: 31,
              fontSize: 27,
              color: C.accent,
            }}
          >
            Draft for review
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Dependency checkpoints explanation"
          style={{
            position: "absolute",
            left: 96,
            right: 96,
            top: 865,
            textAlign: "center",
            fontSize: 30,
            color: C.muted,
            opacity: interpolate(f, [14.8 * fps, 15.8 * fps], [0, 1], motion),
          }}
        >
          Model and mapping changes are applied before dependent work continues.
        </Interactive.Div>
      </Interactive.Div>

      <Interactive.Div
        name="Governed review and approval"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [18 * fps, 18.8 * fps, 26.35 * fps, 27 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <Interactive.Div
          name="Approval headline"
          style={{
            position: "absolute",
            left: 96,
            top: 173,
            opacity: interpolate(f, [19 * fps, 20.1 * fps], [0, 1], motion),
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
            You stay in control.
          </h1>
          <p style={{ fontSize: 36, margin: "12px 0 0", color: C.muted }}>
            Review locally. Validate on the server. Approve Apply.
          </p>
        </Interactive.Div>
        <Interactive.Div
          name="Review checkpoint"
          style={{
            position: "absolute",
            left: 96,
            top: 413,
            width: 390,
            height: 276,
            boxSizing: "border-box",
            padding: 34,
            borderRadius: 22,
            border: `2px solid ${C.line}`,
            background: C.white,
          }}
        >
          <div style={{ fontSize: 27, color: C.accent }}>01</div>
          <h2 style={{ fontSize: 46, margin: "20px 0 10px" }}>Review</h2>
          <div style={{ fontSize: 31, color: C.muted }}>Local Workbench</div>
        </Interactive.Div>
        <Interactive.Div
          name="Approved Stage checkpoint"
          style={{
            position: "absolute",
            left: 542,
            top: 413,
            width: 390,
            height: 276,
            boxSizing: "border-box",
            padding: 34,
            borderRadius: 22,
            border: `2px solid ${C.line}`,
            background: C.white,
            opacity: interpolate(f, [19.8 * fps, 20.8 * fps], [0, 1], motion),
          }}
        >
          <div style={{ fontSize: 27, color: C.accent }}>02</div>
          <h2 style={{ fontSize: 46, margin: "20px 0 10px" }}>Stage</h2>
          <div style={{ fontSize: 31, color: C.muted }}>
            Reviewed server draft
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Server validation checkpoint"
          style={{
            position: "absolute",
            left: 988,
            top: 413,
            width: 390,
            height: 276,
            boxSizing: "border-box",
            padding: 34,
            borderRadius: 22,
            border: `2px solid ${C.line}`,
            background: C.white,
            opacity: interpolate(f, [21.1 * fps, 22.1 * fps], [0, 1], motion),
          }}
        >
          <div style={{ fontSize: 27, color: C.accent }}>03</div>
          <h2 style={{ fontSize: 46, margin: "20px 0 10px" }}>Validate</h2>
          <div style={{ fontSize: 31, color: C.muted }}>
            Authoritative checks
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Explicit Apply checkpoint"
          style={{
            position: "absolute",
            left: 1434,
            top: 413,
            width: 390,
            height: 276,
            boxSizing: "border-box",
            padding: 34,
            borderRadius: 22,
            border: `2px solid ${C.green}`,
            background: "#E6EDE3",
            opacity: interpolate(f, [22.3 * fps, 23.3 * fps], [0, 1], motion),
          }}
        >
          <div style={{ fontSize: 27, color: C.green }}>04 · YOUR APPROVAL</div>
          <h2 style={{ fontSize: 46, margin: "20px 0 10px" }}>Apply</h2>
          <div style={{ fontSize: 31, color: C.ink }}>Save current records</div>
        </Interactive.Div>
        <Interactive.Div
          name="Explicit user approval for Stage"
          style={{
            position: "absolute",
            left: 96,
            right: 96,
            top: 757,
            borderLeft: `5px solid ${C.accent}`,
            padding: "24px 32px",
            background: C.white,
            fontSize: 35,
            opacity: interpolate(
              f,
              [18.6 * fps, 19.5 * fps, 21.5 * fps, 22.15 * fps],
              [0, 1, 1, 0],
              motion,
            ),
          }}
        >
          <span style={{ color: C.muted, marginRight: 28, fontSize: 27 }}>
            YOU
          </span>
          I approve these changes for Stage.
        </Interactive.Div>
        <Interactive.Div
          name="Separate user approval for Apply"
          style={{
            position: "absolute",
            left: 96,
            right: 96,
            top: 757,
            borderLeft: `5px solid ${C.green}`,
            padding: "24px 32px",
            background: C.white,
            fontSize: 35,
            opacity: interpolate(f, [22.2 * fps, 23.2 * fps], [0, 1], motion),
          }}
        >
          <span style={{ color: C.muted, marginRight: 28, fontSize: 27 }}>
            YOU
          </span>
          Apply the validated changes.
        </Interactive.Div>
        <div
          style={{
            position: "absolute",
            left: 96,
            top: 922,
            fontSize: 28,
            color: C.muted,
          }}
        >
          Apply saves Atlas records. Deployment remains a separate handoff.
        </div>
      </Interactive.Div>

      <Interactive.Div
        name="Copilot and the web share approved Atlas records"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [27 * fps, 27.9 * fps, 35.45 * fps, 36 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <Interactive.Div
          name="Shared workspace headline"
          style={{
            position: "absolute",
            left: 96,
            top: 173,
            opacity: interpolate(f, [28.2 * fps, 29.5 * fps], [0, 1], motion),
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
            One model. Two ways to work.
          </h1>
          <p style={{ fontSize: 36, margin: "12px 0 0", color: C.muted }}>
            Copilot and the web application use the same governed records.
          </p>
        </Interactive.Div>
        <Interactive.Div
          name="Copilot confirms the approved change"
          style={{
            position: "absolute",
            left: 96,
            top: 377,
            width: 560,
            height: 212,
            boxSizing: "border-box",
            padding: "28px 34px",
            borderRadius: 20,
            background: "#192B29",
            color: C.paper,
          }}
        >
          <div style={{ fontSize: 26, color: "#D7B48C", marginBottom: 14 }}>
            COPILOT + ATLAS PLUGIN
          </div>
          <div style={{ fontSize: 35, lineHeight: 1.3 }}>
            Approved changes saved.
            <br />
            Refresh the workspace.
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Approved changes reach shared storage"
          style={{
            position: "absolute",
            left: 357,
            top: 603,
            rotate: "90deg",
            opacity: interpolate(f, [28 * fps, 29.2 * fps], [0, 1], motion),
          }}
        >
          <Icon kind="arrow" size={42} color={C.green} />
        </Interactive.Div>
        <Interactive.Div
          name="Shared metadata and model store"
          style={{
            position: "absolute",
            left: 96,
            top: 666,
            width: 560,
            height: 238,
            padding: "30px 34px",
            boxSizing: "border-box",
            border: `2px solid ${C.green}`,
            borderRadius: 20,
            background: C.white,
            opacity: interpolate(f, [28.3 * fps, 29.5 * fps], [0, 1], motion),
          }}
        >
          <div style={{ display: "flex", gap: 22, alignItems: "center" }}>
            <Icon kind="database" size={52} color={C.green} />
            <div style={{ fontSize: 37, fontWeight: 650 }}>
              Shared Atlas Records
            </div>
          </div>
          <div
            style={{
              fontSize: 31,
              color: C.muted,
              lineHeight: 1.4,
              marginTop: 25,
            }}
          >
            Metadata · Model · Artifacts
            <br />
            Authoritative applied state
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Web reads applied state on refresh"
          style={{
            position: "absolute",
            left: 683,
            top: 748,
            width: 100,
            height: 46,
            opacity: interpolate(f, [30.3 * fps, 31.4 * fps], [0, 1], motion),
          }}
        >
          <svg width="100" height="46" viewBox="0 0 100 46">
            <path
              d="M3 23H88m-12-12 12 12-12 12"
              fill="none"
              stroke={C.green}
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </Interactive.Div>
        <Interactive.Div
          name="Actual Atlas web application preview"
          style={{
            position: "absolute",
            left: 810,
            top: 377,
            width: 1014,
            height: 570,
            border: `2px solid ${C.line}`,
            borderRadius: 20,
            overflow: "hidden",
            boxShadow: "0 25px 65px #233A3414",
            background: C.white,
            opacity: interpolate(f, [29.3 * fps, 30.6 * fps], [0, 1], motion),
          }}
        >
          <div
            style={{
              height: 64,
              padding: "0 28px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              background: C.white,
              borderBottom: `1px solid ${C.line}`,
              fontSize: 26,
            }}
          >
            <span>Atlas Web · Demo Capture</span>
            <span
              style={{
                color: C.green,
                opacity: interpolate(
                  f,
                  [31.2 * fps, 32.1 * fps],
                  [0, 1],
                  motion,
                ),
              }}
            >
              ↻ Refresh after Apply
            </span>
          </div>
          <Interactive.Div
            name="Inspect the actual applied model revision and saved entities"
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: 65,
              bottom: 0,
              overflow: "hidden",
            }}
          >
            <CanvasImage
              src={staticFile("captures/complete/logical-applied.png")}
              style={{
                position: "absolute",
                width: 1877.7,
                height: 1056,
                left: interpolate(
                  f,
                  [31.9 * fps, 33.1 * fps],
                  [-854, -285],
                  motion,
                ),
                top: interpolate(
                  f,
                  [31.9 * fps, 33.1 * fps],
                  [-35, -230],
                  motion,
                ),
              }}
            />
          </Interactive.Div>
          <Interactive.Div
            name="Shared applied model confirmation"
            style={{
              position: "absolute",
              left: 26,
              right: 26,
              bottom: 26,
              background: C.dark,
              color: C.paper,
              padding: "22px 26px",
              borderRadius: 13,
              display: "flex",
              gap: 17,
              alignItems: "center",
              fontSize: 31,
              opacity: interpolate(f, [32.1 * fps, 33.2 * fps], [0, 1], motion),
            }}
          >
            <Icon kind="check" size={32} color={C.mint} />
            Refresh the approved model revision.
          </Interactive.Div>
        </Interactive.Div>
        <div
          style={{
            position: "absolute",
            left: 810,
            top: 966,
            fontSize: 23,
            color: C.muted,
          }}
        >
          Actual local demo capture · Illustrative workflow continuity
        </div>
      </Interactive.Div>
    </AbsoluteFill>
  );
};
