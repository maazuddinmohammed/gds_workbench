import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, Frame, Heading, Reveal } from "../design";
import { SourceObject } from "../objects";

export const Sources = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const active = Math.min(5, Math.floor(Math.max(0, f / fps - 1) / 2));
  const sources = [
    ["sql", "SQL databases", "Orders + transactions"],
    ["nosql", "NoSQL stores", "Product documents"],
    ["stream", "Streaming", "Order events"],
    ["folder", "File systems", "Store extracts"],
    ["api", "APIs", "Customer profiles"],
    ["files", "Files", "Supplier feeds"],
  ] as const;
  return (
    <Frame chapter="The source landscape" index={2}>
      <Heading kicker="SIX INPUTS. ONE RETAIL BUSINESS.">
        Different formats. Connected.
      </Heading>
      {sources.map(([kind, title, detail], i) => (
        <Reveal
          key={kind}
          at={0.5 + i * 0.22}
          style={{
            position: "absolute",
            left: 100 + (i % 3) * 580,
            top: 340 + Math.floor(i / 3) * 335,
            width: 500,
            height: 295,
          }}
        >
          <div
            style={{
              display: "flex",
              gap: 14,
              alignItems: "center",
              fontSize: 33,
              fontWeight: 500,
            }}
          >
            <span
              style={{
                height: 9,
                width: 9,
                borderRadius: "50%",
                background: active === i ? C.accent : C.line,
              }}
            />
            {title}
          </div>
          <div
            style={{
              position: "absolute",
              left: 52,
              top: 55,
              scale: active === i ? 1.025 : 1,
            }}
          >
            <SourceObject kind={kind} width={350} />
          </div>
          <div
            style={{
              position: "absolute",
              left: 0,
              bottom: 0,
              fontSize: 25,
              color: C.muted,
            }}
          >
            {detail}
          </div>
        </Reveal>
      ))}
    </Frame>
  );
};
