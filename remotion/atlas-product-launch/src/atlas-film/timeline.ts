export type SceneId =
  | "Open" | "Sources" | "Metadata" | "Bronze" | "Scope" | "Evidence" | "Logical" | "Dimensional"
  | "Mapping" | "Code" | "Lakehouse" | "TwoWays" | "PluginConnect" | "PluginChange" | "Security" | "Locks" | "Close";

/** Scene order and lengths (frames at 30 fps). Edit here to retime the film. */
export const FPS = 30;

export const SCENES: readonly { id: SceneId; frames: number; rail: number }[] = [
  { id: "Open", frames: 240, rail: -1 },
  { id: "Sources", frames: 300, rail: 0 },
  { id: "Metadata", frames: 420, rail: 1 },
  { id: "Bronze", frames: 480, rail: 2 },
  { id: "Scope", frames: 300, rail: 3 },
  { id: "Evidence", frames: 900, rail: 4 },
  { id: "Logical", frames: 420, rail: 7 },
  { id: "Dimensional", frames: 300, rail: 7 },
  { id: "Mapping", frames: 360, rail: 8 },
  { id: "Code", frames: 360, rail: 9 },
  { id: "Lakehouse", frames: 360, rail: 10 },
  { id: "TwoWays", frames: 240, rail: 11 },
  { id: "PluginConnect", frames: 480, rail: 11 },
  { id: "PluginChange", frames: 960, rail: 11 },
  { id: "Security", frames: 420, rail: -1 },
  { id: "Locks", frames: 480, rail: -1 },
  { id: "Close", frames: 270, rail: -1 },
];

export const START: Record<SceneId, number> = (() => {
  const out = {} as Record<SceneId, number>;
  let t = 0;
  for (const s of SCENES) {
    out[s.id] = t;
    t += s.frames;
  }
  return out;
})();

export const TOTAL_FRAMES = SCENES.reduce((n, s) => n + s.frames, 0);

export function len(id: SceneId) {
  return SCENES.find((s) => s.id === id)!.frames;
}
