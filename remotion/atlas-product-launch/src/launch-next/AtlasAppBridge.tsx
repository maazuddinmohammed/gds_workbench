import {
  CanvasImage,
  Interactive,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { motion, SplitStage, StoryCopy } from "./MeetLayout";
export const AtlasAppBridge = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <SplitStage
      dark
      copy={
        <StoryCopy
          name="Enter the real workspace"
          label="THE WORKSPACE"
          title={"This is\nAtlas."}
          at={1.4}
          until={6.4}
          dark
        >
          A shared workspace for metadata
          <br />
          and data modeling.
        </StoryCopy>
      }
    >
      <Interactive.Div
        name="Real Atlas overview"
        style={{
          position: "absolute",
          left: 0,
          top: 90,
          width: 1050,
          height: 590,
          borderRadius: 17,
          overflow: "hidden",
          boxShadow: "0 24px 70px #071F2240",
          opacity: interpolate(f, [0.25 * fps, 1 * fps], [0, 1], motion),
          scale: interpolate(f, [0.25 * fps, 1.3 * fps], [0.97, 1], {
            ...motion,
            output: "perceptual-scale",
          }),
        }}
      >
        <CanvasImage
          src={staticFile("captures/meet-atlas/overview.jpg")}
          style={{ width: "100%", height: "auto" }}
        />
      </Interactive.Div>
    </SplitStage>
  );
};
