import type { CSSProperties, ReactNode } from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";

// Brand values mirror Atlas foundation.css and tenant-workspace.css.
export const ink = "#17202a";
export const orange = "#b75c27";
export const muted = "#66727e";
export const line = "#dfe4e8";
export const ease = {
  easing: Easing.bezier(0.2, 0.8, 0.2, 1),
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;

export const Brand = ({ size = 40 }: { size?: number }) => (
  <div style={{ display: "flex", gap: size * 0.24, alignItems: "center" }}>
    <Img src={staticFile("atlas.svg")} style={{ width: size, height: size }} />
    <span
      style={{
        fontSize: size * 0.8,
        fontWeight: 750,
        letterSpacing: -size * 0.045,
      }}
    >
      Atlas
    </span>
  </div>
);

export const Stage = ({
  children,
  chapter,
  demo = true,
}: {
  children: ReactNode;
  chapter: string;
  demo?: boolean;
}) => (
  <AbsoluteFill
    style={{
      background: "#f7f5f2",
      color: ink,
      fontFamily: "Manrope, -apple-system, BlinkMacSystemFont, sans-serif",
      overflow: "hidden",
    }}
  >
    <div
      style={{
        position: "absolute",
        width: 1040,
        height: 1040,
        right: -280,
        top: 140,
        borderRadius: "50%",
        background: "radial-gradient(circle, #e9d7c833 0%, #e9d7c800 68%)",
      }}
    />
    <div style={{ position: "absolute", left: 110, top: 58 }}>
      <Brand />
    </div>
    <div
      style={{
        position: "absolute",
        right: 112,
        top: 68,
        color: muted,
        fontSize: 20,
        letterSpacing: 3,
        textTransform: "uppercase",
      }}
    >
      {chapter}
    </div>
    {children}
    <div
      style={{
        position: "absolute",
        left: 112,
        right: 112,
        bottom: 48,
        display: "flex",
        justifyContent: "space-between",
        borderTop: "1px solid #dcd9d4",
        paddingTop: 18,
        fontSize: 18,
        color: muted,
      }}
    >
      <span>ATLAS / GOVERNED DATA MODELING</span>
      <span>
        {demo
          ? "Illustrated interface · Demo data"
          : "FROM SOURCE TO STRUCTURE"}
      </span>
    </div>
  </AbsoluteFill>
);

export const AppFrame = ({
  children,
  section,
  style,
  revision = 12,
  sidebar = true,
}: {
  children: ReactNode;
  section: string;
  style?: CSSProperties;
  revision?: number;
  sidebar?: boolean;
}) => (
  <div
    style={{
      background: "#fff",
      border: "1px solid #d9dedf",
      borderRadius: 15,
      boxShadow: "0 28px 70px #17202a12, 0 3px 8px #17202a08",
      overflow: "hidden",
      ...style,
    }}
  >
    <div
      style={{
        height: 74,
        padding: "0 28px",
        borderBottom: `1px solid ${line}`,
        display: "flex",
        alignItems: "center",
        gap: 34,
      }}
    >
      <Brand size={32} />
      <span style={{ width: 1, height: 28, background: line }} />
      <div style={{ fontSize: 17 }}>
        <span style={{ color: muted, fontSize: 12, letterSpacing: 1 }}>
          TENANT
        </span>
        <div style={{ fontWeight: 650 }}>Northstar Demo</div>
      </div>
      <div style={{ fontSize: 17 }}>
        <span style={{ color: muted, fontSize: 12, letterSpacing: 1 }}>
          MODEL
        </span>
        <div style={{ fontWeight: 650 }}>
          Commerce{" "}
          <span style={{ color: muted, fontWeight: 450, marginLeft: 10 }}>
            r{revision}
          </span>
        </div>
      </div>
      <div
        style={{
          marginLeft: "auto",
          color: "#187252",
          fontSize: 15,
          whiteSpace: "nowrap",
        }}
      >
        Tenant Lock held by you
      </div>
    </div>
    <div style={{ display: "flex", height: "calc(100% - 74px)" }}>
      {sidebar && (
        <div
          style={{
            width: 174,
            flexShrink: 0,
            borderRight: `1px solid ${line}`,
            padding: "27px 15px",
            background: "#fbfcfc",
          }}
        >
          {["Home", "Metadata", "Models", "Prompts"].map((name, i) => (
            <div
              key={name}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "15px 12px",
                marginBottom: 5,
                fontSize: 17,
                borderRadius: 7,
                color:
                  name === (section === "Metadata" ? "Metadata" : "Models")
                    ? orange
                    : muted,
                background:
                  name === (section === "Metadata" ? "Metadata" : "Models")
                    ? "#fff1e8"
                    : "transparent",
              }}
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <path
                  d={
                    [
                      "M3 11 12 3 21 11V21H3Z",
                      "M4 6C4 2 20 2 20 6V18C20 22 4 22 4 18ZM4 6C4 10 20 10 20 6M4 12C4 16 20 16 20 12",
                      "M3 3H9V9H3ZM15 15H21V21H15ZM15 3H21V9H15ZM9 6H15M6 9V18H15",
                      "M4 4H20V17H10L5 21V17H4Z",
                    ][i]
                  }
                />
              </svg>
              {name}
            </div>
          ))}
          <div
            style={{
              margin: "42px 12px 0",
              borderTop: `1px solid ${line}`,
              paddingTop: 21,
              color: muted,
              fontSize: 13,
            }}
          >
            OPEN MODEL
            <div
              style={{
                color: ink,
                fontSize: 18,
                fontWeight: 650,
                marginTop: 8,
              }}
            >
              Commerce
            </div>
          </div>
        </div>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            height: 57,
            display: "flex",
            gap: 26,
            alignItems: "center",
            padding: "0 28px",
            borderBottom: `1px solid ${line}`,
            whiteSpace: "nowrap",
            overflow: "hidden",
            fontSize: 16,
          }}
        >
          {(section === "Metadata"
            ? ["Physical metadata", "Objects", "Attributes"]
            : [
                "Overview",
                "Input scope",
                "Profiling",
                "Logical",
                "Dimensional",
                "Mapping",
                "Code generation",
              ]
          ).map((label) => (
            <span
              key={label}
              style={{
                color:
                  label === section ||
                  (section === "Metadata" && label === "Physical metadata")
                    ? orange
                    : muted,
                fontWeight: 650,
                borderBottom:
                  label === section ||
                  (section === "Metadata" && label === "Physical metadata")
                    ? `2px solid ${orange}`
                    : "2px solid transparent",
                height: 57,
                display: "flex",
                alignItems: "center",
              }}
            >
              {label}
            </span>
          ))}
        </div>
        {children}
      </div>
    </div>
  </div>
);

export const ObjectLedger = ({ compact = false }: { compact?: boolean }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ padding: compact ? 28 : 36 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 27,
        }}
      >
        <span style={{ fontSize: 26, fontWeight: 650 }}>
          Physical Objects{" "}
          <span style={{ fontWeight: 450, color: muted, fontSize: 19 }}>
            {" "}
            / 4
          </span>
        </span>
        <span
          style={{
            fontSize: 15,
            padding: "10px 18px",
            border: `1px solid ${line}`,
            borderRadius: 6,
          }}
        >
          Source + Bronze
        </span>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.6fr 1fr 1fr",
          color: muted,
          padding: "15px 16px",
          fontSize: 15,
          borderBottom: `1px solid ${line}`,
        }}
      >
        <span>Object</span>
        <span>System</span>
        <span>Zone</span>
      </div>
      {["customers", "orders", "order_items", "products"].map((name, i) => (
        <div
          key={name}
          style={{
            display: "grid",
            gridTemplateColumns: "1.6fr 1fr 1fr",
            padding: "19px 16px",
            borderBottom: `1px solid ${line}`,
            fontSize: 19,
            background: i === 1 ? "#fff1e8" : "#fff",
            opacity: interpolate(frame, [10 + i * 5, 28 + i * 5], [0, 1], ease),
          }}
        >
          <span style={{ fontWeight: 650, color: i === 1 ? orange : ink }}>
            {name}
          </span>
          <span style={{ color: muted }}>Commerce</span>
          <span style={{ color: muted }}>Bronze</span>
        </div>
      ))}
    </div>
  );
};
