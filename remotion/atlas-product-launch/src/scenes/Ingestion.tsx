import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { C, Frame, Heading, Reveal, Icon, LinkLine, ease } from "../design";
import { SourceObject } from "../objects";

export const Ingestion = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <Frame chapter="Metadata-driven ingestion" index={3}>
      <Heading kicker="GLOBAL DATA STORE">
        Metadata tells data where to go.
      </Heading>
      <Reveal
        at={0.7}
        style={{
          position: "absolute",
          left: 662,
          top: 328,
          width: 590,
          background: C.white,
          border: `1px solid ${C.line}`,
          borderRadius: 14,
          padding: "26px 34px",
        }}
      >
        <div
          style={{
            fontSize: 24,
            color: C.accent,
            letterSpacing: 2,
            marginBottom: 18,
          }}
        >
          INGESTION CONFIGURATION
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontFamily: "IBM Plex Mono",
            fontSize: 26,
          }}
        >
          <span>Source: Orders</span>
          <span>Target: Bronze</span>
        </div>
      </Reveal>
      <LinkLine d="M958 457V558" at={1.7} dashed />
      <LinkLine d="M488 687H746" at={2.1} />
      <LinkLine d="M1165 687H1460" at={3.5} />
      <div style={{ position: "absolute", left: 85, top: 565 }}>
        <SourceObject kind="sql" width={350} />
      </div>
      <Reveal
        at={1}
        style={{ position: "absolute", left: 98, top: 830, fontSize: 32 }}
      >
        Orders · SQL source
      </Reveal>
      <Reveal
        at={2}
        style={{
          position: "absolute",
          left: 750,
          top: 563,
          width: 420,
          height: 250,
          background: C.ink,
          zIndex: 1,
          color: C.paper,
          borderRadius: 20,
          padding: 35,
          boxShadow: "0 24px 55px #233A3420",
        }}
      >
        <Icon kind="layers" size={57} color={C.mint} />
        <div style={{ fontSize: 40, marginTop: 18 }}>GDS orchestration</div>
        <div style={{ fontSize: 27, marginTop: 17, color: C.mint }}>
          Read metadata → ingest
        </div>
      </Reveal>
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: interpolate(
              f,
              [(3 + i * 0.65) * fps, (5.4 + i * 0.65) * fps],
              [475, 1460],
              ease,
            ),
            top: 674,
            width: 27,
            height: 27,
            borderRadius: 5,
            background: i % 2 ? C.green : C.accent,
            opacity: interpolate(
              f,
              [
                (3 + i * 0.65) * fps,
                (3.1 + i * 0.65) * fps,
                (5.3 + i * 0.65) * fps,
                (5.4 + i * 0.65) * fps,
              ],
              [0, 1, 1, 0],
              ease,
            ),
          }}
        />
      ))}
      <Reveal
        at={4}
        style={{
          position: "absolute",
          left: 1455,
          top: 554,
          width: 355,
          height: 265,
        }}
      >
        <svg width="350" height="265" viewBox="0 0 350 265">
          <path
            d="M20 47V215C20 257 330 257 330 215V47"
            fill="#DCC5A8"
            stroke="#AA855F"
            strokeWidth="2"
          />
          <ellipse
            cx="175"
            cy="47"
            rx="155"
            ry="38"
            fill="#F2E3CD"
            stroke="#AA855F"
            strokeWidth="2"
          />
          <path
            d="M20 156C20 198 330 198 330 156"
            fill="none"
            stroke="#AA855F"
            strokeWidth="2"
          />
          <text x="82" y="128" fill={C.ink} fontSize="45" fontFamily="Inter">
            Bronze
          </text>
          <text x="70" y="221" fill="#7C674F" fontSize="24" fontFamily="Inter">
            Ingested sources
          </text>
        </svg>
      </Reveal>
      <Reveal
        at={8}
        style={{
          position: "absolute",
          left: 630,
          top: 919,
          fontSize: 32,
          color: C.muted,
        }}
      >
        A shared foundation for the Atlas model.
      </Reveal>
    </Frame>
  );
};
