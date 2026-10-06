import { Audio } from "@remotion/media";
import {
  AbsoluteFill,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C } from "../design";
import { motion } from "./MeetLayout";
import { AtlasIdentity } from "./AtlasIdentity";
import { GdsFoundation } from "./GdsFoundation";
import { AtlasModeling } from "./AtlasModeling";
import { WorkspaceTour } from "./WorkspaceTour";
import { LogicalRunDemo } from "./LogicalRunDemo";
import { ExportArtifacts } from "./ExportArtifacts";
import { DeliveryHandoff } from "./DeliveryHandoff";
import { PluginLifecycle } from "./PluginLifecycle";
import { Safeguards } from "./Safeguards";
import { LaunchClosing } from "./LaunchClosing";
export {
  AtlasIdentity,
  GdsFoundation,
  AtlasModeling,
  WorkspaceTour,
  LogicalRunDemo,
  ExportArtifacts,
  DeliveryHandoff,
  PluginLifecycle,
  Safeguards,
  LaunchClosing,
};
export const COMPLETE_SECONDS = 261;

/** Complete product story, with independently editable chapters. Voice is deferred. */
export const MeetAtlas = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <Audio
        name="Original instrumental score"
        src={staticFile("audio/score-complete.wav")}
        volume={interpolate(
          f,
          [0, fps, 258 * fps, 261 * fps],
          [0, 0.7, 0.7, 0],
          motion,
        )}
        premountFor={fps}
      />
      <Sequence name="Meet Atlas" durationInFrames={7 * fps}>
        <AtlasIdentity />
      </Sequence>
      <Sequence
        name="Sources, metadata and GDS Framework"
        from={7 * fps}
        durationInFrames={51 * fps}
      >
        <GdsFoundation />
      </Sequence>
      <Sequence
        name="Scope, evidence and common models"
        from={58 * fps}
        durationInFrames={32 * fps}
      >
        <AtlasModeling />
      </Sequence>
      <Sequence
        name="The Atlas workspace"
        from={90 * fps}
        durationInFrames={28 * fps}
      >
        <WorkspaceTour />
      </Sequence>
      <Sequence
        name="Logical One shot run"
        from={118 * fps}
        durationInFrames={45 * fps}
      >
        <LogicalRunDemo />
      </Sequence>
      <Sequence
        name="Review and export artifacts"
        from={163 * fps}
        durationInFrames={14 * fps}
      >
        <ExportArtifacts />
      </Sequence>
      <Sequence
        name="Delivery into the GDS lifecycle"
        from={177 * fps}
        durationInFrames={18 * fps}
      >
        <DeliveryHandoff />
      </Sequence>
      <Sequence
        name="Ticket to governed plugin change"
        from={195 * fps}
        durationInFrames={36 * fps}
      >
        <PluginLifecycle />
      </Sequence>
      <Sequence
        name="Shared security and concurrency safeguards"
        from={231 * fps}
        durationInFrames={22 * fps}
      >
        <Safeguards />
      </Sequence>
      <Sequence
        name="From ticket to governed change"
        from={253 * fps}
        durationInFrames={8 * fps}
      >
        <LaunchClosing />
      </Sequence>
    </AbsoluteFill>
  );
};
