import {
  AbsoluteFill,
  Interactive,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, Icon, Logo } from "../design";
import { motion } from "./MeetLayout";

export const Safeguards = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{
        background: C.dark,
        color: C.paper,
        fontFamily: '"Source Sans 3", sans-serif',
        overflow: "hidden",
      }}
    >
      <div style={{ position: "absolute", left: 96, top: 62 }}>
        <Logo size={48} light />
      </div>
      <div
        style={{
          position: "absolute",
          right: 96,
          top: 70,
          color: C.mint,
          fontSize: 26,
          letterSpacing: 2.2,
        }}
      >
        GOVERNANCE, THROUGHOUT
      </div>
      <Interactive.Div
        name="Access and roles"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [0, 0.9 * fps, 10.4 * fps, 11 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <Interactive.Div
          name="Role-based access headline"
          style={{
            position: "absolute",
            left: 96,
            top: 173,
            opacity: interpolate(f, [1 * fps, 2.3 * fps], [0, 1], motion),
          }}
        >
          <h1
            style={{
              margin: 0,
              fontSize: 74,
              lineHeight: 1.1,
              fontWeight: 650,
              letterSpacing: -1.8,
            }}
          >
            Access follows your role.
          </h1>
          <p style={{ fontSize: 36, color: C.mint, margin: "19px 0 0" }}>
            The same protections apply in the web and the plugin.
          </p>
        </Interactive.Div>
        <Interactive.Div
          name="Tenant scoped authorization boundary"
          style={{
            position: "absolute",
            left: 96,
            top: 411,
            width: 516,
            height: 480,
            padding: "47px 42px",
            boxSizing: "border-box",
            border: "2px solid #5E7A6A",
            borderRadius: 24,
            background: "#21483E",
          }}
        >
          <div
            style={{
              width: 110,
              height: 110,
              borderRadius: 28,
              background: "#365C48",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Icon kind="lock" size={64} color="#D8BB87" />
          </div>
          <h2 style={{ fontSize: 45, lineHeight: 1.14, margin: "36px 0 21px" }}>
            Tenant-Scoped
            <br />
            Access
          </h2>
          <div style={{ fontSize: 32, lineHeight: 1.42, color: C.mint }}>
            Identity and permissions
            <br />
            are checked on the server.
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Atlas tenant roles"
          style={{
            position: "absolute",
            left: 709,
            top: 411,
            width: 1115,
            height: 480,
            padding: "12px 40px",
            boxSizing: "border-box",
            borderRadius: 24,
            background: C.paper,
            color: C.ink,
            opacity: interpolate(f, [2.8 * fps, 4 * fps], [0, 1], motion),
          }}
        >
          <Interactive.Div
            name="Viewer permission"
            style={{
              height: 113,
              display: "flex",
              alignItems: "center",
              borderBottom: `1px solid ${C.line}`,
              opacity: interpolate(f, [3 * fps, 4.1 * fps], [0, 1], motion),
            }}
          >
            <span style={{ fontSize: 38, fontWeight: 650, width: 325 }}>
              Viewer
            </span>
            <span style={{ fontSize: 33, color: C.muted }}>
              Read authorized records
            </span>
          </Interactive.Div>
          <Interactive.Div
            name="Developer permission"
            style={{
              height: 113,
              display: "flex",
              alignItems: "center",
              borderBottom: `1px solid ${C.line}`,
              opacity: interpolate(f, [4.3 * fps, 5.4 * fps], [0, 1], motion),
            }}
          >
            <span style={{ fontSize: 38, fontWeight: 650, width: 325 }}>
              Developer
            </span>
            <span style={{ fontSize: 33, color: C.muted }}>
              Maintain metadata
            </span>
          </Interactive.Div>
          <Interactive.Div
            name="Architect permission"
            style={{
              height: 113,
              display: "flex",
              alignItems: "center",
              borderBottom: `1px solid ${C.line}`,
              opacity: interpolate(f, [5.6 * fps, 6.7 * fps], [0, 1], motion),
            }}
          >
            <span style={{ fontSize: 38, fontWeight: 650, width: 325 }}>
              Architect
            </span>
            <span style={{ fontSize: 33, color: C.muted }}>
              Develop governed models
            </span>
          </Interactive.Div>
          <Interactive.Div
            name="Tenant Admin permission"
            style={{
              height: 113,
              display: "flex",
              alignItems: "center",
              opacity: interpolate(f, [6.9 * fps, 8 * fps], [0, 1], motion),
            }}
          >
            <span style={{ fontSize: 38, fontWeight: 650, width: 325 }}>
              Tenant Admin
            </span>
            <span style={{ fontSize: 33, color: C.muted }}>
              Administer the Tenant
            </span>
          </Interactive.Div>
        </Interactive.Div>
      </Interactive.Div>

      <Interactive.Div
        name="Write coordination and audit"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [11 * fps, 11.9 * fps, 21.45 * fps, 22 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <Interactive.Div
          name="Coordinated changes headline"
          style={{
            position: "absolute",
            left: 96,
            top: 173,
            opacity: interpolate(f, [12 * fps, 13.2 * fps], [0, 1], motion),
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
            Changes stay coordinated.
          </h1>
          <p style={{ fontSize: 36, color: C.mint, margin: "12px 0 0" }}>
            Ownership, run protection and revision checks work together.
          </p>
        </Interactive.Div>
        <Interactive.Div
          name="Tenant Lock protects writes"
          style={{
            position: "absolute",
            left: 96,
            top: 390,
            width: 837,
            height: 242,
            boxSizing: "border-box",
            padding: "32px 37px",
            borderRadius: 22,
            border: "2px solid #658274",
            background: "#21483E",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <Icon kind="lock" size={45} color="#D8BB87" />
            <h2 style={{ fontSize: 40, margin: 0 }}>Tenant Lock</h2>
          </div>
          <div style={{ fontSize: 32, color: C.mint, marginTop: 22 }}>
            Only the lock owner can write.
          </div>
          <div style={{ fontSize: 27, marginTop: 17, color: "#D8BB87" }}>
            Ownership is checked again at save.
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Conflicting workflow cannot overwrite an active run"
          style={{
            position: "absolute",
            left: 987,
            top: 390,
            width: 837,
            height: 242,
            boxSizing: "border-box",
            padding: "32px 37px",
            borderRadius: 22,
            border: "2px solid #658274",
            background: "#21483E",
            opacity: interpolate(f, [13.5 * fps, 14.7 * fps], [0, 1], motion),
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <Icon kind="stream" size={45} color="#D8BB87" />
            <h2 style={{ fontSize: 40, margin: 0 }}>Run Exclusivity</h2>
          </div>
          <div style={{ fontSize: 32, color: C.mint, marginTop: 22 }}>
            One running workflow per Tenant.
          </div>
          <div
            style={{ display: "flex", gap: 21, marginTop: 17, fontSize: 27 }}
          >
            <span style={{ color: "#B6DFB5" }}>Run A · active</span>
            <span style={{ color: "#E4B7A1" }}>Run B · conflict blocked</span>
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Revision fence rejects stale changes"
          style={{
            position: "absolute",
            left: 96,
            top: 683,
            width: 837,
            height: 242,
            boxSizing: "border-box",
            padding: "32px 37px",
            borderRadius: 22,
            border: "2px solid #658274",
            background: "#21483E",
            opacity: interpolate(f, [15.4 * fps, 16.6 * fps], [0, 1], motion),
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <Icon kind="layers" size={45} color="#D8BB87" />
            <h2 style={{ fontSize: 40, margin: 0 }}>Revision Checks</h2>
          </div>
          <div style={{ fontSize: 32, color: C.mint, marginTop: 22 }}>
            Stale updates are rejected.
          </div>
          <div style={{ fontSize: 27, marginTop: 17, color: "#D8BB87" }}>
            Refresh and reconcile before continuing.
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Reviewed Apply keeps the change auditable"
          style={{
            position: "absolute",
            left: 987,
            top: 683,
            width: 837,
            height: 242,
            boxSizing: "border-box",
            padding: "32px 37px",
            borderRadius: 22,
            border: "2px solid #658274",
            background: "#21483E",
            opacity: interpolate(f, [17.3 * fps, 18.5 * fps], [0, 1], motion),
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <Icon kind="check" size={45} color="#D8BB87" />
            <h2 style={{ fontSize: 40, margin: 0 }}>Reviewed Apply</h2>
          </div>
          <div style={{ fontSize: 32, color: C.mint, marginTop: 22 }}>
            Validated changes. Explicit approval.
          </div>
          <div style={{ fontSize: 27, marginTop: 17, color: "#D8BB87" }}>
            Protected records and auditable outcomes.
          </div>
        </Interactive.Div>
      </Interactive.Div>
    </AbsoluteFill>
  );
};
