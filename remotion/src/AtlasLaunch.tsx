import { Audio } from "@remotion/media";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { AbsoluteFill, staticFile } from "remotion";
import { Reveal } from "./scenes/Reveal";
import { Metadata } from "./scenes/Metadata";
import { Models } from "./scenes/Models";
import { Code } from "./scenes/Code";
import { Review } from "./scenes/Review";
import { Close } from "./scenes/Close";

export const AtlasLaunch = ({ soundtrack }: { soundtrack: boolean }) => (
  <AbsoluteFill>
    {soundtrack && <Audio src={staticFile("atlas-score.wav")} volume={0.55} />}
    <TransitionSeries>
      <TransitionSeries.Sequence durationInFrames={180} name="Meet Atlas">
        <Reveal />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        durationInFrames={210}
        name="Understand metadata"
      >
        <Metadata />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        durationInFrames={240}
        name="Give data structure"
      >
        <Models />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        durationInFrames={240}
        name="Carry the logic through"
      >
        <Code />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence durationInFrames={210} name="Review and apply">
        <Review />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        durationInFrames={180}
        name="Build with context"
      >
        <Close />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  </AbsoluteFill>
);
