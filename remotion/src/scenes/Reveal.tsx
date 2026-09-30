import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { AppFrame, ease, ObjectLedger, orange, Stage } from "../Design";

export const Reveal = () => {
  const frame = useCurrentFrame();
  return (
    <Stage chapter="Introducing Atlas" demo>
      <Interactive.Div
        name="Opening headline"
        style={{
          position: "absolute",
          left: 112,
          top: 278,
          width: 810,
          fontSize: 139,
          lineHeight: 1.02,
          fontWeight: 650,
          letterSpacing: -8,
          translate: interpolate(frame, [0, 35], ["0px 30px", "0px 0px"], ease),
          opacity: interpolate(frame, [0, 20], [0, 1], ease),
        }}
      >
        From source
        <br />
        <span style={{ color: orange }}>to structure.</span>
      </Interactive.Div>
      <Interactive.Div
        name="Atlas introduction"
        style={{
          position: "absolute",
          left: 120,
          top: 635,
          width: 670,
          fontSize: 38,
          lineHeight: 1.45,
          color: "#66727e",
          opacity: interpolate(frame, [18, 45], [0, 1], ease),
        }}
      >
        Meet Atlas.
        <br />
        Your workspace for governed
        <br />
        data modeling.
      </Interactive.Div>
      <Interactive.Div
        name="Product window"
        style={{
          position: "absolute",
          left: 990,
          top: 226,
          width: 1130,
          height: 665,
          rotate: interpolate(frame, [0, 90], ["3deg", "0deg"], ease),
          translate: interpolate(
            frame,
            [0, 70],
            ["190px 100px", "0px 0px"],
            ease,
          ),
          opacity: interpolate(frame, [8, 35], [0, 1], ease),
        }}
      >
        <AppFrame section="Metadata" style={{ height: "100%" }}>
          <ObjectLedger compact />
        </AppFrame>
      </Interactive.Div>
      <div
        style={{
          position: "absolute",
          left: 120,
          top: 859,
          width: interpolate(frame, [40, 90], [0, 570], ease),
          height: 3,
          background: orange,
        }}
      />
    </Stage>
  );
};
