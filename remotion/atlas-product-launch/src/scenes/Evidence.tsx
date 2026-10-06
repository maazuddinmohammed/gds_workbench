import {
  interpolate,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  C,
  Chip,
  Entity,
  Frame,
  Heading,
  Icon,
  LinkLine,
  Reveal,
  ease,
} from "../design";

export const Evidence = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const phase = Math.min(2, Math.floor(frame / (8 * fps)));
  const measured = interpolate(frame, [1.3 * fps, 2.8 * fps], [0, 97.4], ease);
  return (
    <Frame chapter="Profile · enrich · analyze" index={5}>
      <Heading kicker="RETAIL SALES / SOURCE UNDERSTANDING">
        {
          [
            "See the quality of every field.",
            "Give technical data meaning.",
            "Discover how sources connect.",
          ][phase]
        }
      </Heading>
      <div
        style={{
          position: "absolute",
          left: 100,
          right: 100,
          top: 328,
          display: "flex",
          gap: 52,
          borderBottom: `1px solid ${C.line}`,
        }}
      >
        {["01  Profile", "02  Enrich", "03  Analyze"].map((label, i) => (
          <div
            key={label}
            style={{
              fontSize: 28,
              padding: "15px 0 20px",
              borderBottom: `3px solid ${phase === i ? C.accent : "transparent"}`,
              color: phase === i ? C.accent : C.muted,
            }}
          >
            {label}
          </div>
        ))}
        <div
          style={{
            marginLeft: "auto",
            alignSelf: "center",
            color: C.muted,
            fontSize: 20,
          }}
        >
          ILLUSTRATIVE RESULTS
        </div>
      </div>
      <Sequence durationInFrames={8 * fps} layout="none">
        <Reveal
          at={0.4}
          style={{ position: "absolute", left: 100, top: 428, width: 990 }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 32,
            }}
          >
            <div>
              <div style={{ fontSize: 37 }}>Customers</div>
              <div style={{ fontSize: 24, color: C.muted, marginTop: 10 }}>
                124,800 rows · 6 scoped sources profiled
              </div>
            </div>
            <Chip>Profile complete</Chip>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.25fr 1fr 1fr",
              padding: "19px 25px",
              fontSize: 21,
              color: C.muted,
            }}
          >
            <span>FIELD</span>
            <span>COMPLETENESS</span>
            <span>UNIQUENESS</span>
          </div>
          {[
            ["CustomerID", "100%", "100%"],
            ["Email", "97.4%", "96.1%"],
            ["LoyaltyTier", "91.2%", "3 values"],
          ].map(([name, present, unique], i) => (
            <Reveal
              key={name}
              at={0.7 + i * 0.35}
              style={{
                display: "grid",
                gridTemplateColumns: "1.25fr 1fr 1fr",
                alignItems: "center",
                height: 91,
                padding: "0 25px",
                background: i === 1 ? C.pale : C.white,
                borderTop: `1px solid ${C.line}`,
                borderLeft: `4px solid ${i === 1 ? C.accent : "transparent"}`,
                fontSize: 29,
              }}
            >
              <span style={{ fontFamily: "IBM Plex Mono" }}>{name}</span>
              <span>{present}</span>
              <span>{unique}</span>
            </Reveal>
          ))}
          <Reveal
            at={4}
            style={{ fontSize: 26, color: C.muted, marginTop: 32 }}
          >
            Find missing values, candidate keys, and unusual distributions.
          </Reveal>
        </Reveal>
        <Reveal
          at={1.1}
          style={{
            position: "absolute",
            left: 1210,
            top: 426,
            width: 580,
            textAlign: "center",
          }}
        >
          <div style={{ fontFamily: "IBM Plex Mono", fontSize: 29 }}>
            Customers.Email
          </div>
          <svg
            width="350"
            height="350"
            viewBox="0 0 350 350"
            style={{ marginTop: 10 }}
          >
            <circle
              cx="175"
              cy="175"
              r="135"
              fill="none"
              stroke={C.pale}
              strokeWidth="24"
            />
            <circle
              cx="175"
              cy="175"
              r="135"
              fill="none"
              stroke={C.green}
              strokeWidth="24"
              pathLength="100"
              strokeDasharray={`${measured} 100`}
              transform="rotate(-90 175 175)"
              strokeLinecap="butt"
            />
            <text
              x="175"
              y="173"
              textAnchor="middle"
              fill={C.ink}
              fontFamily="Inter"
              fontSize="64"
              letterSpacing="-3"
            >
              {measured.toFixed(1)}%
            </text>
            <text
              x="175"
              y="213"
              textAnchor="middle"
              fill={C.muted}
              fontFamily="Inter"
              fontSize="25"
            >
              complete
            </text>
          </svg>
          <Reveal at={3.5}>
            <div style={{ fontSize: 35, color: C.accent }}>
              3,245 missing values
            </div>
            <div style={{ fontSize: 25, color: C.muted, marginTop: 13 }}>
              A finding to address before modeling.
            </div>
          </Reveal>
        </Reveal>
      </Sequence>
      <Sequence from={8 * fps} durationInFrames={8 * fps} layout="none">
        <Reveal
          at={0.2}
          style={{
            position: "absolute",
            left: 100,
            top: 435,
            width: 620,
            height: 453,
            padding: 34,
            border: `1px solid ${C.line}`,
            borderRadius: 14,
            background: C.white,
            boxSizing: "border-box",
          }}
        >
          <div style={{ fontSize: 22, color: C.muted }}>SOURCE METADATA</div>
          <div
            style={{ fontFamily: "IBM Plex Mono", fontSize: 39, marginTop: 37 }}
          >
            LoyaltyTier
          </div>
          <div
            style={{
              fontFamily: "IBM Plex Mono",
              fontSize: 27,
              lineHeight: 1.9,
              marginTop: 24,
              color: C.muted,
            }}
          >
            type: string
            <br />
            nullable: true
            <br />
            values: Gold, Silver, Bronze
          </div>
          <div
            style={{
              borderTop: `1px solid ${C.line}`,
              marginTop: 24,
              paddingTop: 23,
              fontSize: 25,
            }}
          >
            Description: —
          </div>
        </Reveal>
        <Reveal at={1.3} style={{ position: "absolute", left: 792, top: 616 }}>
          <Icon kind="arrow" size={70} color={C.accent} />
        </Reveal>
        <Reveal
          at={1.5}
          style={{
            position: "absolute",
            left: 934,
            top: 435,
            width: 886,
            minHeight: 453,
            padding: "32px 38px",
            borderRadius: 14,
            background: C.ink,
            color: C.paper,
            boxSizing: "border-box",
          }}
        >
          <div style={{ fontSize: 22, letterSpacing: 2, color: C.mint }}>
            ENRICHED IN ATLAS
          </div>
          <div style={{ fontSize: 45, marginTop: 26, letterSpacing: -1 }}>
            Customer membership level
          </div>
          <Reveal
            at={2.2}
            style={{
              fontSize: 28,
              lineHeight: 1.55,
              color: C.mint,
              marginTop: 23,
            }}
          >
            The customer’s loyalty program tier.
            <br />
            Used to compare sales by membership level.
          </Reveal>
          <Reveal at={3.2} style={{ display: "flex", gap: 15, marginTop: 32 }}>
            <Chip dark>Business classification</Chip>
            <Chip dark>Model-owned meaning</Chip>
          </Reveal>
          <Reveal
            at={4}
            style={{
              marginTop: 29,
              borderTop: "1px solid #52665C",
              paddingTop: 23,
              fontSize: 25,
            }}
          >
            Source field retained: Customers.LoyaltyTier
          </Reveal>
        </Reveal>
      </Sequence>
      <Sequence from={16 * fps} durationInFrames={8 * fps} layout="none">
        <LinkLine d="M655 620H1190V564H1265" at={1.5} />
        <Entity
          name="Orders"
          highlightField="CustomerID"
          fields={["OrderID", "CustomerID", "OrderDate"]}
          x={205}
          y={461}
          width={450}
          at={0.2}
        />
        <Entity
          name="Customers"
          highlightField="CustomerID"
          fields={["CustomerID", "CustomerName", "LoyaltyTier"]}
          x={1265}
          y={461}
          width={450}
          at={0.6}
        />
        <Reveal
          at={2.1}
          style={{
            position: "absolute",
            left: 713,
            top: 483,
            width: 493,
            textAlign: "center",
          }}
        >
          <div style={{ color: C.accent, fontSize: 22, letterSpacing: 2 }}>
            PROPOSED RELATIONSHIP
          </div>
          <div style={{ fontSize: 40, marginTop: 27 }}>Many → one</div>
          <div style={{ fontSize: 24, color: C.muted, marginTop: 100 }}>
            Matched on CustomerID
          </div>
        </Reveal>
        <Reveal
          at={3.3}
          style={{
            position: "absolute",
            left: 205,
            right: 205,
            top: 821,
            borderTop: `1px solid ${C.line}`,
            paddingTop: 30,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              fontSize: 27,
            }}
          >
            <Icon kind="search" size={31} color={C.accent} />
            Inferred from source evidence
          </div>
          <Chip>Confidence: high</Chip>
          <Chip color={C.accent}>Measured validation pending</Chip>
        </Reveal>
      </Sequence>
    </Frame>
  );
};
