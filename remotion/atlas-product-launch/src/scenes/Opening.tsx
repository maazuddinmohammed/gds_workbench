import {
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  Interactive,
} from "remotion";
import { C, Frame, Logo, Reveal, ease } from "../design";

export const Opening = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <Frame chapter="Introducing Atlas" index={1}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          flexDirection: "column",
          paddingTop: 200,
        }}
      >
        <Reveal at={0.1}>
          <div style={{ fontSize: 25, letterSpacing: 5, color: C.accent }}>
            FOR GLOBAL DATA STORE
          </div>
        </Reveal>
        <Interactive.Div
          name="Atlas product mark"
          style={{
            marginTop: 45,
            scale: interpolate(f, [0, 1.5 * fps], [0.93, 1], ease),
          }}
        >
          <Logo size={250} />
        </Interactive.Div>
        <Reveal
          at={1}
          style={{ fontSize: 54, letterSpacing: -1.5, marginTop: 33 }}
        >
          AI-assisted data engineering.
        </Reveal>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 58,
            marginTop: 90,
          }}
        >
          <Reveal at={2.2} style={{ fontSize: 37 }}>
            Understand sources
          </Reveal>
          <Reveal at={2.8} style={{ color: C.accent, fontSize: 40 }}>
            →
          </Reveal>
          <Reveal at={3.1} style={{ fontSize: 37 }}>
            Build common models
          </Reveal>
          <Reveal at={3.7} style={{ color: C.accent, fontSize: 40 }}>
            →
          </Reveal>
          <Reveal at={4} style={{ fontSize: 37 }}>
            Evolve with control
          </Reveal>
        </div>
        <Reveal
          at={5}
          style={{
            marginTop: 58,
            width: 1150,
            height: 2,
            background: `linear-gradient(90deg,transparent,${C.accent},transparent)`,
          }}
        >
          <span />
        </Reveal>
      </div>
    </Frame>
  );
};
