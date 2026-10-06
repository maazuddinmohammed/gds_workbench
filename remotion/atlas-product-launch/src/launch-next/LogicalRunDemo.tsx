import {
  AbsoluteFill,
  CanvasImage,
  Interactive,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, Logo } from "../design";
import { motion } from "./MeetLayout";

type RunShot = {
  image: string;
  title: string;
  detail: string;
  step: number;
  focus: [number, number];
  zoom: number;
  box: [number, number, number, number];
  nextImage?: string;
  changeAt?: number;
  pointer?: [number, number];
  clickAt?: number;
};

/** Camera and annotations stay in screenshot coordinates, keeping real controls aligned. */
function RunShot({
  image,
  title,
  detail,
  step,
  focus,
  zoom,
  box,
  nextImage,
  changeAt = 99,
  pointer,
  clickAt = 99,
}: RunShot) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const scale = interpolate(f, [0, 1.2 * fps], [zoom * 0.96, zoom], motion);
  const x = 600 - focus[0] * scale;
  const y = 348 - focus[1] * scale;
  return (
    <AbsoluteFill>
      <Interactive.Div
        name={title}
        style={{
          position: "absolute",
          left: 96,
          top: 280,
          width: 440,
          opacity: interpolate(f, [0, 0.9 * fps], [0, 1], motion),
        }}
      >
        <div style={{ fontSize: 24, color: C.accent, letterSpacing: 2.4 }}>
          LOGICAL MODEL · {step} / 8
        </div>
        <h1
          style={{
            fontSize: 66,
            fontWeight: 600,
            lineHeight: 1.08,
            letterSpacing: -1.6,
            margin: "28px 0 30px",
            whiteSpace: "pre-line",
          }}
        >
          {title}
        </h1>
        <p
          style={{ fontSize: 32, lineHeight: 1.42, color: C.muted, margin: 0 }}
        >
          {detail}
        </p>
      </Interactive.Div>
      <Interactive.Div
        name="Actual Atlas application capture"
        style={{
          position: "absolute",
          left: 624,
          top: 230,
          width: 1200,
          height: 700,
          border: `2px solid ${C.line}`,
          borderRadius: 22,
          overflow: "hidden",
          background: "white",
          boxShadow: "0 24px 70px #233A3412",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: x,
            top: y,
            width: 1707,
            height: 960,
            transform: `scale(${scale})`,
            transformOrigin: "0 0",
          }}
        >
          <CanvasImage
            src={staticFile(`captures/complete/${image}.png`)}
            style={{ position: "absolute", inset: 0, width: 1707, height: 960 }}
          />
          {nextImage ? (
            <CanvasImage
              src={staticFile(`captures/complete/${nextImage}.png`)}
              style={{
                position: "absolute",
                inset: 0,
                width: 1707,
                height: 960,
                opacity: interpolate(
                  f,
                  [changeAt * fps, (changeAt + 0.4) * fps],
                  [0, 1],
                  motion,
                ),
              }}
            />
          ) : null}
          <Interactive.Div
            name="Current control highlight"
            style={{
              position: "absolute",
              left: box[0],
              top: box[1],
              width: box[2],
              height: box[3],
              border: `2px solid ${C.accent}`,
              borderRadius: 9,
              boxSizing: "border-box",
              boxShadow: "0 0 0 5px #BC603E12",
              opacity: interpolate(f, [0.6 * fps, 1.4 * fps], [0, 1], motion),
            }}
          />
          {pointer ? (
            <Interactive.Div
              name="Demonstration pointer"
              style={{
                position: "absolute",
                left: interpolate(
                  f,
                  [(clickAt - 1.4) * fps, (clickAt - 0.35) * fps],
                  [pointer[0] + 100, pointer[0]],
                  motion,
                ),
                top: interpolate(
                  f,
                  [(clickAt - 1.4) * fps, (clickAt - 0.35) * fps],
                  [pointer[1] + 65, pointer[1]],
                  motion,
                ),
                opacity: interpolate(
                  f,
                  [
                    (clickAt - 1.4) * fps,
                    (clickAt - 1.05) * fps,
                    (clickAt + 0.45) * fps,
                    (clickAt + 0.8) * fps,
                  ],
                  [0, 1, 1, 0],
                  motion,
                ),
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: -16,
                  top: -16,
                  width: 32,
                  height: 32,
                  border: `2px solid ${C.accent}`,
                  borderRadius: "50%",
                  transform: `scale(${interpolate(f, [clickAt * fps, (clickAt + 0.5) * fps], [0.4, 1.8], motion)})`,
                  opacity: interpolate(
                    f,
                    [clickAt * fps, (clickAt + 0.5) * fps],
                    [0.9, 0],
                    motion,
                  ),
                }}
              />
              <svg width="27" height="34" viewBox="0 0 27 34">
                <path
                  d="M2 2L24 20L14 21L10 31Z"
                  fill={C.dark}
                  stroke="white"
                  strokeWidth="2"
                />
              </svg>
            </Interactive.Div>
          ) : null}
        </div>
      </Interactive.Div>
      <div
        style={{
          position: "absolute",
          left: 624,
          top: 962,
          fontSize: 23,
          color: C.muted,
        }}
      >
        Actual Atlas UI · Local demo with fictional data · Run time condensed
      </div>
      <div
        style={{
          position: "absolute",
          left: 96,
          top: 927,
          display: "flex",
          gap: 12,
        }}
      >
        {Array.from({ length: 8 }, (_, i) => (
          <div
            key={i}
            style={{
              width: i + 1 === step ? 48 : 14,
              height: 6,
              borderRadius: 4,
              background: i + 1 <= step ? C.accent : C.line,
            }}
          />
        ))}
      </div>
    </AbsoluteFill>
  );
}

export const LogicalRunDemo = () => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{
        background: C.paper,
        color: C.ink,
        fontFamily: '"Source Sans 3", sans-serif',
      }}
    >
      <div style={{ position: "absolute", left: 96, top: 62 }}>
        <Logo size={48} />
      </div>
      <div
        style={{
          position: "absolute",
          right: 96,
          top: 76,
          fontSize: 23,
          letterSpacing: 2.3,
          color: C.muted,
        }}
      >
        03 / ONE SHOT, STEP BY STEP
      </div>
      <Sequence durationInFrames={5 * fps}>
        <RunShot
          image="logical"
          title={"Let’s build\na model."}
          detail="Start a Logical run from the shared workspace."
          step={1}
          focus={[1370, 350]}
          zoom={1.65}
          box={[1578, 286, 104, 47]}
          pointer={[1630, 310]}
          clickAt={4.3}
        />
      </Sequence>
      <Sequence from={5 * fps} durationInFrames={7 * fps}>
        <RunShot
          image="run-config-default"
          nextImage="run-config-oneshot"
          changeAt={2.8}
          title={"Choose\nOne shot."}
          detail="Choose how Atlas will create the candidate design."
          step={2}
          focus={[850, 331]}
          zoom={1.55}
          box={[510, 298, 230, 73]}
          pointer={[624, 344]}
          clickAt={2.7}
        />
      </Sequence>
      <Sequence from={12 * fps} durationInFrames={6 * fps}>
        <RunShot
          image="run-config-oneshot"
          nextImage="run-config-ready"
          changeAt={2}
          title={"Select a model.\nConfirm scope."}
          detail="Choose the AI model and the Bronze objects in scope."
          step={3}
          focus={[850, 469]}
          zoom={1.55}
          box={[501, 295, 704, 357]}
          pointer={[850, 344]}
          clickAt={1.9}
        />
      </Sequence>
      <Sequence from={18 * fps} durationInFrames={5 * fps}>
        <RunShot
          image="run-config-ready"
          title={"Run with\nyour scope."}
          detail="Atlas creates a tracked authoring run."
          step={4}
          focus={[850, 647]}
          zoom={1.55}
          box={[569, 772, 169, 53]}
          pointer={[652, 798]}
          clickAt={4.3}
        />
      </Sequence>
      <Sequence from={23 * fps} durationInFrames={6 * fps}>
        <RunShot
          image="logical-running"
          nextImage="logical-completed"
          changeAt={2.5}
          title={"Follow\nthe progress."}
          detail="Track activity, then open the proposed draft."
          step={5}
          focus={[1337, 291]}
          zoom={1.55}
          box={[1008, 179, 687, 249]}
        />
      </Sequence>
      <Sequence from={29 * fps} durationInFrames={6 * fps}>
        <RunShot
          image="logical-review"
          title={"Review\nbefore Apply."}
          detail="Inspect the validated candidate and its staged changes."
          step={6}
          focus={[1340, 390]}
          zoom={1.55}
          box={[1014, 283, 678, 259]}
          pointer={[1604, 506]}
          clickAt={5.3}
        />
      </Sequence>
      <Sequence from={35 * fps} durationInFrames={5 * fps}>
        <RunShot
          image="logical-approve"
          title={"Approve the\nexact draft."}
          detail="Atlas checks the current revision and saves the approved change."
          step={7}
          focus={[853, 481]}
          zoom={1.85}
          box={[978, 525, 148, 52]}
          pointer={[1050, 551]}
          clickAt={3.6}
        />
      </Sequence>
      <Sequence from={40 * fps} durationInFrames={5 * fps}>
        <RunShot
          image="logical-applied"
          title={"Now part of\nthe model."}
          detail="The approved entities are available in the shared workspace."
          step={8}
          focus={[741, 485]}
          zoom={1.55}
          box={[485, 480, 310, 129]}
        />
      </Sequence>
    </AbsoluteFill>
  );
};
