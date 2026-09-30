# Atlas launch video

40 seconds · 1920 × 1080 · 30 fps · six editable scenes.

The film follows Atlas from physical metadata through model design, source
mapping, generated SQL, and governed review. It uses Atlas's real logo and color
tokens, recreated product interfaces, and clearly labeled fictional metadata.
The model diagram illustrates outputs; it does not imply a graph editor.

## Preview

From this folder:

```bash
npm ci
npm run dev
```

Open the URL printed by Studio and choose **AtlasLaunch**. The **Scenes** folder
lets you edit and preview one scene at a time. Set `soundtrack` to `false` in the
composition's props for silent playback.

## Export

```bash
npm run render
npm run still
```

Outputs: `out/atlas-launch.mp4` and `out/atlas-poster.png`. The MP4 command exports
H.264 at CRF 18. A browser may be downloaded by Remotion on first export.
The Studio preview and poster are created during authoring; video export is a
separate command.

## Editing

- `storyboard.json`: creative brief, exact copy, timing, and product accuracy.
- `src/scenes/`: one file per scene.
- `src/Design.tsx`: Atlas identity, product frame, and shared metadata ledger.
- `src/AtlasLaunch.tsx`: scene order, transitions, and optional soundtrack.
- `src/Root.tsx`: video dimensions and individually editable compositions.

The timeline contains 1,260 scene frames, with five 12-frame overlaps: 1,200
frames, exactly 40 seconds. Entry frames are 0, 168, 366, 594, 822, and 1,020.
Animation is frame-driven, so scrubbing and export produce consistent results.

Checks:

```bash
npm run check
npm run build
```

No application code, database, live service, or deployment is used by the film.
The SQL is an illustrative SELECT artifact; the video does not claim it has run.
Candidate validation does not imply validation of physical business results.

## Research decision — September 30, 2026

Best fit found: **Remotion's own skills plus its official prompt showcase**.
The installed official skills cover creation, layout, frame-based motion,
transitions, editable scenes, audio, and preview. Dependencies are pinned to
Remotion 4.0.530, the official starter's version at creation.

| Source                                                                                                                                            | Assessment and use                                                                                                                                                                      |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Official Remotion skills](https://www.remotion.dev/docs/ai/skills) / [source](https://github.com/remotion-dev/skills)                            | Primary implementation guidance. Maintained by Remotion; source showed approximately 4.8k GitHub stars. Already available locally, so no duplicate skill installation.                  |
| [Official product-demo prompt example](https://www.remotion.dev/prompts/product-demo-for-presscut) / [showcase](https://www.remotion.dev/prompts) | Most relevant prompting reference: recreate product UI and choose a focused, plain-language demonstration.                                                                              |
| [Amplitude launch-video guide](https://github.com/amplitude/builder-skills/blob/main/launch-skills/skills/launch-video/SKILL.md)                  | Useful complementary planning guidance: scene beats, clean demo data, readable silent playback, preview and iteration.                                                                  |
| [Memex product-launch-video skill](https://github.com/memex-lab/product-launch-video-skill)                                                       | Detailed creative workflow, but only 12 GitHub stars when checked. Reviewed as a secondary reference; insufficient evidence to call it the best or install it over the official skills. |

Adoption is only supporting evidence. Selection is based primarily on official
maintenance, direct relevance, readable instructions, and compatibility with
the installed Remotion version. Search cannot establish a universal best skill.

## Assets

- Atlas logo: copied from `web_app/frontend/public/assets/atlas.svg`.
- Manrope: local font from `@fontsource-variable/manrope`, SIL Open Font License;
  license included in `public/fonts/OFL.txt`.
- Instrumental: original local synthesis, no sampled recordings. Recreate with
  `node scripts/make-score.mjs`. No voiceover or external audio service.
- All product records and measurements are fictional demonstration material.

`node_modules/`, `build/`, and `out/` are ignored. No publish or deployment action
is included.
