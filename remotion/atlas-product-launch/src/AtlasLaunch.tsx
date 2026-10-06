import { Audio } from "@remotion/media";
import { AbsoluteFill, Series, staticFile, useVideoConfig } from "remotion";
import { Opening } from "./scenes/Opening";
import { Sources } from "./scenes/Sources";
import { Ingestion } from "./scenes/Ingestion";
import { Scope } from "./scenes/Scope";
import { Evidence } from "./scenes/Evidence";
import { Models } from "./scenes/Models";
import { Mapping } from "./scenes/Mapping";
import { Code } from "./scenes/Code";
import { Execution } from "./scenes/Execution";
import { Investigate } from "./scenes/Investigate";
import { Evolve } from "./scenes/Evolve";
import { Closing } from "./scenes/Closing";

export type LaunchProps = { musicVolume: number };
export const AtlasLaunch = ({ musicVolume }: LaunchProps) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: "#F5F2EB" }}>
      <Audio
        name="Original ambient score"
        src={staticFile("audio/score.wav")}
        volume={musicVolume}
        premountFor={fps}
      />
      <Series>
        <Series.Sequence
          name="01 — Meet Atlas"
          durationInFrames={8 * fps}
          premountFor={fps}
        >
          <Opening />
        </Series.Sequence>
        <Series.Sequence
          name="02 — Source landscape"
          durationInFrames={16 * fps}
          premountFor={fps}
        >
          <Sources />
        </Series.Sequence>
        <Series.Sequence
          name="03 — Metadata-driven ingestion"
          durationInFrames={12 * fps}
          premountFor={fps}
        >
          <Ingestion />
        </Series.Sequence>
        <Series.Sequence
          name="04 — Create and scope a model"
          durationInFrames={13 * fps}
          premountFor={fps}
        >
          <Scope />
        </Series.Sequence>
        <Series.Sequence
          name="05 — Profile, enrich, analyze"
          durationInFrames={24 * fps}
          premountFor={fps}
        >
          <Evidence />
        </Series.Sequence>
        <Series.Sequence
          name="06 — Common models"
          durationInFrames={15 * fps}
          premountFor={fps}
        >
          <Models />
        </Series.Sequence>
        <Series.Sequence
          name="07 — Mapping documents"
          durationInFrames={11 * fps}
          premountFor={fps}
        >
          <Mapping />
        </Series.Sequence>
        <Series.Sequence
          name="08 — SQL and validation"
          durationInFrames={12 * fps}
          premountFor={fps}
        >
          <Code />
        </Series.Sequence>
        <Series.Sequence
          name="09 — Delivery and orchestration"
          durationInFrames={13 * fps}
          premountFor={fps}
        >
          <Execution />
        </Series.Sequence>
        <Series.Sequence
          name="10 — Investigate a failure"
          durationInFrames={10 * fps}
          premountFor={fps}
        >
          <Investigate />
        </Series.Sequence>
        <Series.Sequence
          name="11 — Evolve the model"
          durationInFrames={14 * fps}
          premountFor={fps}
        >
          <Evolve />
        </Series.Sequence>
        <Series.Sequence
          name="12 — Complete lifecycle"
          durationInFrames={8 * fps}
          premountFor={fps}
        >
          <Closing />
        </Series.Sequence>
      </Series>
    </AbsoluteFill>
  );
};
