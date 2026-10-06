import { Audio } from "@remotion/media";
import { AbsoluteFill, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { Backdrop, clampOpts, Rail, T } from "./kit";
import { SCENES, START, TOTAL_FRAMES, type SceneId } from "./timeline";
import { Bronze, Metadata, Open, Sources } from "./ActFoundation";
import { Dimensional, Evidence, Logical, Scope } from "./ActModel";
import { Code, Lakehouse, Mapping } from "./ActBuild";
import { PluginChange, PluginConnect, TwoWays } from "./ActPlugin";
import { Close, Locks, Security } from "./ActGovern";

export const SCENE_COMPONENTS: Record<SceneId, () => React.ReactNode> = {
  Open,
  Sources,
  Metadata,
  Bronze,
  Scope,
  Evidence,
  Logical,
  Dimensional,
  Mapping,
  Code,
  Lakehouse,
  TwoWays,
  PluginConnect,
  PluginChange,
  Security,
  Locks,
  Close,
};

/** Rail position over time; the Evidence scene advances through Profile, Enrich and Analyze. */
function railAt(frame: number) {
  let current: (typeof SCENES)[number] = SCENES[0];
  for (const s of SCENES) if (frame >= START[s.id]) current = s;
  if (current.id === "Evidence") {
    const local = frame - START.Evidence;
    return local < 300 ? 4 : local < 570 ? 5 : 6;
  }
  return current.rail;
}

function backdropHue(frame: number) {
  if (frame >= START.Security && frame < START.Close) return T.gold;
  if (frame >= START.TwoWays && frame < START.Security) return T.violet;
  return T.copper;
}

export const AtlasFilm = ({ musicVolume = 0.75 }: { musicVolume?: number }) => {
  const f = useCurrentFrame();
  const rail = railAt(f);
  const railOpacity = interpolate(
    f,
    [START.Sources - 10, START.Sources + 20, START.Security - 20, START.Security],
    [0, 1, 1, 0],
    clampOpts,
  );
  return (
    <AbsoluteFill style={{ background: T.bg0 }}>
      <Backdrop hue={backdropHue(f)} />
      <Audio
        name="Score"
        src={staticFile("audio/atlas-film-score.wav")}
        volume={(fr) =>
          interpolate(fr, [0, 20, TOTAL_FRAMES - 60, TOTAL_FRAMES], [0, musicVolume, musicVolume, 0], clampOpts)
        }
      />
      {SCENES.map((s) => {
        const C = SCENE_COMPONENTS[s.id];
        return (
          <Sequence key={s.id} name={s.id} from={START[s.id]} durationInFrames={s.frames}>
            <C />
          </Sequence>
        );
      })}
      <Rail active={rail < 0 ? 11 : rail} opacity={railOpacity} />
    </AbsoluteFill>
  );
};

/** Single-scene preview with the shared backdrop, for Studio editing. */
export function makeScenePreview(id: SceneId) {
  const C = SCENE_COMPONENTS[id];
  const scene = SCENES.find((s) => s.id === id)!;
  const Preview = () => (
    <AbsoluteFill style={{ background: T.bg0 }}>
      <Backdrop />
      <C />
      {scene.rail >= 0 ? <Rail active={scene.rail} /> : null}
    </AbsoluteFill>
  );
  return Preview;
}
