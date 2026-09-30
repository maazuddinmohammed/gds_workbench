import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { Brand, ease, orange, Stage } from "../Design";

export const Close = () => {
  const frame = useCurrentFrame();
  return (
    <Stage chapter="Meet Atlas" demo={false}>
      <svg
        style={{ position: "absolute", top: 190, left: 0, opacity: 0.35 }}
        width="1920"
        height="460"
        viewBox="0 0 1920 460"
        fill="none"
      >
        <path
          d="M0 45H190Q220 45 220 75V150Q220 180 250 180H610M1920 330H1670Q1640 330 1640 300V210Q1640 180 1610 180H1290"
          stroke="#cdb39e"
          strokeWidth="2"
          pathLength="1"
          strokeDasharray="1"
          strokeDashoffset={interpolate(frame, [0, 75], [1, 0], ease)}
        />
        <circle
          cx="610"
          cy="180"
          r="6"
          fill={orange}
          opacity={interpolate(frame, [50, 70], [0, 1], ease)}
        />
        <circle
          cx="1290"
          cy="180"
          r="6"
          fill={orange}
          opacity={interpolate(frame, [60, 80], [0, 1], ease)}
        />
      </svg>
      <Interactive.Div
        name="Atlas closing identity"
        style={{
          position: "absolute",
          top: 294,
          left: 0,
          width: 1920,
          display: "flex",
          justifyContent: "center",
          scale: interpolate(frame, [0, 45], [0.94, 1], ease),
          opacity: interpolate(frame, [0, 28], [0, 1], ease),
        }}
      >
        <Brand size={154} />
      </Interactive.Div>
      <Interactive.Div
        name="Closing headline"
        style={{
          position: "absolute",
          top: 502,
          left: 100,
          width: 1720,
          textAlign: "center",
          fontSize: 111,
          fontWeight: 600,
          letterSpacing: -5.5,
          translate: interpolate(
            frame,
            [17, 50],
            ["0px 35px", "0px 0px"],
            ease,
          ),
          opacity: interpolate(frame, [17, 45], [0, 1], ease),
        }}
      >
        Build with context.
      </Interactive.Div>
      <Interactive.Div
        name="Explore Atlas"
        style={{
          position: "absolute",
          top: 698,
          left: 0,
          width: 1920,
          display: "flex",
          justifyContent: "center",
          opacity: interpolate(frame, [40, 68], [0, 1], ease),
        }}
      >
        <div
          style={{
            fontSize: 36,
            fontWeight: 650,
            color: orange,
            borderBottom: "2px solid #b75c2760",
            paddingBottom: 16,
          }}
        >
          Explore Atlas <span style={{ marginLeft: 20 }}>→</span>
        </div>
      </Interactive.Div>
    </Stage>
  );
};
