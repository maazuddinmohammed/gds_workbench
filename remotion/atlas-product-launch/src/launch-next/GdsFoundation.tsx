import {
  CanvasImage,
  Interactive,
  interpolate,
  interpolateColors,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, Logo } from "../design";
import { SourceObject } from "../objects";
import {
  Arrow,
  motion,
  SourceGlyph,
  SplitStage,
  StoryCopy,
} from "./MeetLayout";

/** Four held beats: source landscape, metadata, framework, then moving data. */
export const GdsFoundation = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <SplitStage
      copy={
        <>
          <StoryCopy
            name="Describe the source landscape"
            label="SOURCE SYSTEMS"
            title={"Many sources.\nOne foundation."}
            at={12}
            until={18}
          >
            SQL, NoSQL, streams, APIs,
            <br />
            file systems and files.
          </StoryCopy>
          <StoryCopy
            name="Locate the metadata in Atlas"
            label="METADATA IN ATLAS"
            title={"Metadata lives\nin Atlas."}
            at={18.5}
            until={28}
          >
            Describe the sources and
            <br />
            their ingestion rules.
          </StoryCopy>
          <StoryCopy
            name="Explain the GDS Framework"
            label="GDS FRAMEWORK"
            title={"GDS makes\nmetadata work."}
            at={32.5}
            until={40}
          >
            <span
              style={{
                color: interpolateColors(
                  f,
                  [33 * fps, 34 * fps, 36 * fps, 37 * fps],
                  [C.muted, "#0078D4", "#0078D4", C.muted],
                ),
              }}
            >
              ADF runs triggers and pipelines.
            </span>
            <br />
            <span
              style={{
                color: interpolateColors(
                  f,
                  [36.5 * fps, 37.5 * fps, 39.5 * fps, 40 * fps],
                  [C.muted, "#C93122", "#C93122", C.muted],
                ),
              }}
            >
              Databricks notebooks
              <br />
              use the metadata.
            </span>
          </StoryCopy>
          <StoryCopy
            name="Follow data into the lakehouse"
            label="DATA LAKEHOUSE"
            title={"Source data.\nOne lakehouse."}
            at={42.5}
            until={51.4}
          >
            GDS brings source data
            <br />
            into the Bronze layer.
          </StoryCopy>
        </>
      }
    >
      <Interactive.Div
        name="Source systems expand, close, then move into place"
        style={{
          position: "absolute",
          left: interpolate(
            f,
            [
              0,
              1.5 * fps,
              3 * fps,
              7.5 * fps,
              9.5 * fps,
              11.5 * fps,
              20 * fps,
              21.5 * fps,
            ],
            [5, 5, -295, -295, 5, 500, 500, 40],
            motion,
          ),
          top: interpolate(
            f,
            [0, 1.5 * fps, 3 * fps, 7.5 * fps, 9.5 * fps, 20 * fps, 21.5 * fps],
            [235, 235, 75, 75, 235, 235, 70],
            motion,
          ),
          width: interpolate(
            f,
            [0, 1.5 * fps, 3 * fps, 7.5 * fps, 9.5 * fps, 20 * fps, 21.5 * fps],
            [330, 330, 930, 930, 330, 330, 220],
            motion,
          ),
          height: interpolate(
            f,
            [0, 1.5 * fps, 3 * fps, 7.5 * fps, 9.5 * fps, 20 * fps, 21.5 * fps],
            [230, 230, 550, 550, 230, 230, 180],
            motion,
          ),
          borderRadius: 26,
          border: `2px solid ${C.line}`,
          background: C.white,
          overflow: "hidden",
          boxSizing: "border-box",
          opacity: interpolate(f, [0, 0.8 * fps], [0, 1], motion),
        }}
      >
        <Interactive.Div
          name="Collapsed source database"
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 15,
            opacity: interpolate(
              f,
              [0, 1.5 * fps, 2.3 * fps, 8.2 * fps, 9.3 * fps],
              [1, 1, 0, 0, 1],
              motion,
            ),
          }}
        >
          <SourceGlyph size={100} />
          <div style={{ fontSize: 26, fontWeight: 600, whiteSpace: "nowrap" }}>
            Source Systems
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Expanded source types"
          style={{
            position: "absolute",
            width: 930,
            height: 550,
            padding: 38,
            boxSizing: "border-box",
            opacity: interpolate(
              f,
              [2.3 * fps, 3.3 * fps, 7.5 * fps, 8.2 * fps],
              [0, 1, 1, 0],
              motion,
            ),
          }}
        >
          <div
            style={{
              fontSize: 29,
              fontWeight: 600,
              textAlign: "center",
              color: C.muted,
            }}
          >
            Source Systems
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              columnGap: 36,
              rowGap: 35,
              marginTop: 32,
            }}
          >
            {(
              [
                ["sql", "SQL"],
                ["nosql", "NoSQL"],
                ["stream", "Streams"],
                ["api", "APIs"],
                ["folder", "File systems"],
                ["files", "Files"],
              ] as const
            ).map(([kind, label]) => (
              <div key={kind} style={{ textAlign: "center" }}>
                <SourceObject kind={kind} width={200} />
                <div style={{ fontSize: 32, marginTop: 9 }}>{label}</div>
              </div>
            ))}
          </div>
        </Interactive.Div>
      </Interactive.Div>

      <Arrow d="M292 160H608" at={23} until={51.5} dashed />
      <Interactive.Div
        name="Source metadata connector label"
        style={{
          position: "absolute",
          left: 390,
          top: 97,
          width: 130,
          height: 40,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 23,
          fontWeight: 600,
          borderRadius: 9,
          border: "1px solid #DFC4AE",
          color: C.accent,
          background: C.white,
          opacity: interpolate(f, [23.2 * fps, 24.2 * fps], [0, 1], motion),
        }}
      >
        Metadata
      </Interactive.Div>
      <Interactive.Div
        name="Atlas holds source metadata"
        style={{
          position: "absolute",
          left: 640,
          top: 70,
          width: 220,
          height: 180,
          borderRadius: 26,
          border: "2px solid",
          borderColor: interpolateColors(
            f,
            [21.5 * fps, 22.5 * fps, 26.5 * fps, 28 * fps],
            [C.line, C.accent, C.accent, C.line],
          ),
          background: C.white,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxSizing: "border-box",
          opacity: interpolate(f, [21.5 * fps, 22.5 * fps], [0, 1], motion),
        }}
      >
        <div
          style={{
            position: "absolute",
            bottom: 20,
            width: 122,
            height: 19,
            borderRadius: "50%",
            background: "#EAB998",
            filter: "blur(10px)",
            opacity: interpolate(
              f,
              [21.8 * fps, 22.8 * fps, 27 * fps, 28.5 * fps],
              [0, 0.85, 0.85, 0.3],
              motion,
            ),
          }}
        />
        <Logo size={114} word={false} />
        <div
          style={{
            position: "absolute",
            bottom: 23,
            width: 84,
            height: 5,
            borderRadius: 5,
            background: C.accent,
            opacity: interpolate(f, [21.8 * fps, 22.8 * fps], [0, 1], motion),
          }}
        />
      </Interactive.Div>
      <Arrow
        d={`M750 282V295Q750 315 730 315H550Q530 315 530 335V${interpolate(f, [40 * fps, 41.5 * fps], [353, 398], motion)}`}
        at={30}
        until={51.5}
        dashed
      />
      <Interactive.Div
        name="Atlas metadata connector label"
        style={{
          position: "absolute",
          left: 790,
          top: 282,
          width: 130,
          height: 40,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 23,
          fontWeight: 600,
          borderRadius: 9,
          border: "1px solid #DFC4AE",
          color: C.accent,
          background: C.white,
          opacity: interpolate(f, [30.5 * fps, 31.5 * fps], [0, 1], motion),
        }}
      >
        Metadata
      </Interactive.Div>

      <Interactive.Div
        name="GDS Framework expands its infrastructure then becomes one box"
        style={{
          position: "absolute",
          left: interpolate(f, [40 * fps, 41.5 * fps], [350, 390], motion),
          top: interpolate(f, [40 * fps, 41.5 * fps], [385, 430], motion),
          width: interpolate(f, [40 * fps, 41.5 * fps], [360, 280], motion),
          height: interpolate(f, [40 * fps, 41.5 * fps], [300, 160], motion),
          borderRadius: 26,
          border: `2px solid ${C.line}`,
          background: C.white,
          boxSizing: "border-box",
          padding: "25px 22px",
          overflow: "hidden",
          opacity: interpolate(f, [28.3 * fps, 29.5 * fps], [0, 1], motion),
        }}
      >
        <div
          style={{
            fontSize: 29,
            fontWeight: 650,
            textAlign: "center",
            whiteSpace: "nowrap",
          }}
        >
          GDS Framework
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            gap: 20,
            marginTop: 30,
            opacity: interpolate(f, [40 * fps, 41 * fps], [1, 0], motion),
          }}
        >
          <div style={{ width: 133, textAlign: "center", flexShrink: 0 }}>
            <div
              style={{
                width: 90,
                height: 90,
                margin: "0 auto",
                borderRadius: 20,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: interpolateColors(
                  f,
                  [33 * fps, 34 * fps, 36 * fps, 37 * fps],
                  [C.white, "#D2EAFE", "#D2EAFE", C.white],
                ),
                border: "2px solid #0078D4",
              }}
            >
              <svg
                width={62}
                height={62}
                viewBox="0 0 18 18"
                aria-label="Azure Data Factory"
                dangerouslySetInnerHTML={{
                  __html: `<defs><linearGradient id="f710a364-083f-494c-9d96-89b92ee2d5a8" x1="0.5" y1="9.77" x2="9" y2="9.77" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#005ba1" /><stop offset="0.07" stop-color="#0060a9" /><stop offset="0.36" stop-color="#0071c8" /><stop offset="0.52" stop-color="#0078d4" /><stop offset="0.64" stop-color="#0074cd" /><stop offset="0.81" stop-color="#006abb" /><stop offset="0.99" stop-color="#005ba1" /></linearGradient></defs><title>Icon-databases-126</title><g><path d="M13.25,10.48V6.57a.14.14,0,0,0-.24-.1l-4,4L4.85,14.63V17.5H16.93a.56.56,0,0,0,.57-.57V6.57a.14.14,0,0,0-.24-.1Z" fill="#005ba1" /><path d="M4.75,3.58C2.4,3.58.5,2.89.5,2V7.67h0v9.26a.56.56,0,0,0,.57.57H9V2C9,2.89,7.1,3.58,4.75,3.58Z" fill="url(#f710a364-083f-494c-9d96-89b92ee2d5a8)" /><rect x="12.91" y="12.97" width="2.27" height="2.27" rx="0.28" fill="#fff" /><rect x="8.97" y="12.97" width="2.27" height="2.27" rx="0.28" fill="#fff" /><rect x="5.03" y="12.97" width="2.27" height="2.27" rx="0.28" fill="#fff" /><path d="M9,2c0,.85-1.9,1.54-4.25,1.54S.5,2.89.5,2,2.4.5,4.75.5,9,1.19,9,2" fill="#eaeaea" /><path d="M8,1.91c0,.55-1.46,1-3.26,1s-3.26-.43-3.26-1S3,.94,4.75.94,8,1.37,8,1.91" fill="#50e6ff" /><path d="M4.75,2.14a8.07,8.07,0,0,0-2.58.37,7.64,7.64,0,0,0,2.58.38,7.64,7.64,0,0,0,2.58-.38A8.07,8.07,0,0,0,4.75,2.14Z" fill="#198ab3" /></g>`,
                }}
              />
            </div>
            <div
              style={{
                fontSize: 26,
                fontWeight: 600,
                color: "#005BA1",
                marginTop: 16,
              }}
            >
              ADF
            </div>
          </div>
          <div style={{ width: 133, textAlign: "center", flexShrink: 0 }}>
            <div
              style={{
                width: 90,
                height: 90,
                margin: "0 auto",
                borderRadius: 20,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: interpolateColors(
                  f,
                  [36.5 * fps, 37.5 * fps, 39.5 * fps, 40 * fps],
                  [C.white, "#FFE3D7", "#FFE3D7", C.white],
                ),
                border: "2px solid #FF3621",
              }}
            >
              <CanvasImage
                src={staticFile("brands/databricks.svg")}
                style={{ width: 60, height: 62 }}
              />
            </div>
            <div style={{ fontSize: 25, fontWeight: 600, marginTop: 16 }}>
              Databricks
            </div>
          </div>
        </div>
      </Interactive.Div>
      <Arrow
        d="M150 282V525Q150 550 175 550H358"
        at={41.5}
        until={51.5}
        color={C.green}
      />
      <Interactive.Div
        name="Source data connector label"
        style={{
          position: "absolute",
          left: 184,
          top: 407,
          width: 92,
          height: 42,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 9,
          background: C.white,
          border: "1px solid #BCD0BA",
          color: C.green,
          fontSize: 24,
          fontWeight: 600,
          opacity: interpolate(f, [41.5 * fps, 42.5 * fps], [0, 1], motion),
        }}
      >
        Data
      </Interactive.Div>
      <Arrow d="M422 550H638" at={41.5} until={51.5} color={C.green} />
      <Arrow d="M702 550H758" at={41.5} until={51.5} color={C.green} />
      <Interactive.Div
        name="Databricks Lakehouse and Bronze layer"
        style={{
          position: "absolute",
          left: 790,
          top: 340,
          width: 250,
          height: 285,
          borderRadius: 26,
          border: "2px solid #D3C5B7",
          background: C.white,
          padding: "22px 18px",
          boxSizing: "border-box",
          textAlign: "center",
          opacity: interpolate(f, [40.3 * fps, 41.5 * fps], [0, 1], motion),
        }}
      >
        <CanvasImage
          src={staticFile("brands/databricks.svg")}
          style={{ width: 52, height: 56 }}
        />
        <div style={{ fontSize: 24, fontWeight: 600, marginTop: 8 }}>
          Databricks
        </div>
        <div style={{ fontSize: 31, fontWeight: 600, marginTop: 3 }}>
          Lakehouse
        </div>
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 166,
            height: 1,
            background: "#D3C5B7",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 20,
            right: 20,
            top: 185,
            height: 50,
            boxSizing: "border-box",
            fontSize: 28,
            fontWeight: 650,
            lineHeight: "46px",
            background: interpolateColors(
              f,
              [
                45.4 * fps,
                45.8 * fps,
                46.3 * fps,
                47 * fps,
                49.1 * fps,
                49.5 * fps,
                50 * fps,
                50.7 * fps,
              ],
              [
                "#F0DFD1",
                "#DEB389",
                "#DEB389",
                "#F0DFD1",
                "#F0DFD1",
                "#DEB389",
                "#DEB389",
                "#F0DFD1",
              ],
            ),
            border: "2px solid #B88A5B",
            borderRadius: 11,
            boxShadow: `0 0 ${interpolate(
              f,
              [
                45.4 * fps,
                45.8 * fps,
                46.3 * fps,
                47 * fps,
                49.1 * fps,
                49.5 * fps,
                50 * fps,
                50.7 * fps,
              ],
              [0, 22, 22, 0, 0, 22, 22, 0],
              motion,
            )}px #C89B6C66`,
          }}
        >
          Bronze
        </div>
      </Interactive.Div>
      <Interactive.Div
        name="Two batches of data travel through GDS into Bronze"
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      >
        {[0, 1, 2, 3, 4, 5].map((packet) => {
          const start =
            42.8 + Math.floor(packet / 3) * 3.7 + (packet % 3) * 0.12;
          return (
            <div
              key={packet}
              style={{
                position: "absolute",
                left: 0,
                top: 0,
                width: 20,
                height: 16,
                borderRadius: 5,
                border: "2px solid #F5F2EB",
                background: C.green,
                boxShadow: "0 2px 8px #487D643D",
                offsetPath: 'path("M150 282V525Q150 550 175 550H830")',
                offsetRotate: "0deg",
                offsetDistance: interpolate(
                  f,
                  [start * fps, (start + 2.96) * fps],
                  ["0%", "100%"],
                  { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                ),
                opacity: interpolate(
                  f,
                  [
                    start * fps,
                    (start + 0.16) * fps,
                    (start + 2.8) * fps,
                    (start + 2.96) * fps,
                  ],
                  [0, 1, 1, 0],
                  motion,
                ),
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: 5,
                  right: 5,
                  top: 5,
                  height: 2,
                  background: "#E5F0E3",
                  borderRadius: 2,
                }}
              />
              <div
                style={{
                  position: "absolute",
                  left: 5,
                  right: 5,
                  top: 9,
                  height: 2,
                  background: "#E5F0E3",
                  borderRadius: 2,
                }}
              />
            </div>
          );
        })}
      </Interactive.Div>
    </SplitStage>
  );
};
