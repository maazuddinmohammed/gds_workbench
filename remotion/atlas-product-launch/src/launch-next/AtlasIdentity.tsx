import {
  Interactive,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Logo, C } from "../design";
import { motion, SplitStage, StoryCopy } from "./MeetLayout";
export const AtlasIdentity = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <SplitStage
      dark
      copy={
        <StoryCopy
          name="Introduce Atlas"
          label="THE PLATFORM"
          title={"Meet\nAtlas."}
          at={2.1}
          until={7.3}
          dark
        >
          <strong style={{ fontWeight: 700 }}>
            AI-Assisted Data Engineering
            <br />
            For Global Data Store.
          </strong>
        </StoryCopy>
      }
    >
      <Interactive.Div
        name="Atlas identity"
        style={{
          position: "absolute",
          left: 150,
          top: 205,
          width: 750,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          opacity: interpolate(f, [0.4 * fps, 1.2 * fps], [0, 1], motion),
          scale: interpolate(f, [0.4 * fps, 1.4 * fps], [0.96, 1], {
            ...motion,
            output: "perceptual-scale",
          }),
        }}
      >
        <Logo size={150} light />
        <div style={{ marginTop: 54, color: C.mint, fontSize: 31 }}>
          Metadata. Lakehouse. Models.
        </div>
      </Interactive.Div>
    </SplitStage>
  );
};
