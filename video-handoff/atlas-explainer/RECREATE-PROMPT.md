# Prompt: recreate the exact Atlas v9 video

Provide this file together with `atlas-exact-recreation-v9.zip`. Copy the prompt below into the receiving agent's chat. The ZIP contains `RECREATE.md` and every required authored source/media file; the guide alone is not enough for exact recreation.

---

Recreate the **exact saved Atlas v9 explainer** from the attached frozen kit. Do not redesign it or generate a merely similar video.

Extract the kit into a local standalone directory outside Git, or an already ignored directory. Preserve that exclusion. Do not initialize a repository, force-add, publish, upload, push, deploy or access any database/cloud workspace. Follow the local repository instructions if applicable.

Read `RECREATE.md`, then `brief/v9/STORYBOARD.md`, `NARRATION.md`, `ART-DIRECTION.md`, `DESIGN-SPEC.md` and `REPRODUCTION-MANIFEST.json`. Use the bundled source/assets as the authority. Keep every file, cue, image, icon, font, layout value, highlight, transition and narration sample unchanged. Do not run TTS generators, recapture the workbench, fetch substitute artwork, upgrade dependencies or rewrite source from the prose. If an expected file/hash is missing or wrong, report the exact discrepancy instead of inventing a replacement or regenerating the manifest.

From the extracted project root, run sequentially:

```bash
python3 scripts/verify_recreation.py
npm ci --no-fund --no-audit
npm run check
npm run build
npm run studio
```

Use the captured runtime/browser versions from the manifest when possible. First-time npm/browser installation can require network or cache; video playback itself uses local files. Use the exact local Studio URL printed by the command. Select **AtlasExplainer**: v9, 1920×1080, 30 fps, 8,400 frames, 280 seconds, captions off. **AtlasExplainer-Captions** is an optional review view. Standalone artwork and previous-review compositions are not the final master.

Compare the supplied named reference frames, using `python3 scripts/verify_recreation.py --render-reference NAME` with a name from the index. Inspect any mismatch before proceeding; never replace the baselines to make a check pass. Scrub the full film and listen across every scene boundary. Preserve the orange narrated focus, recognizable Copilot chat, nine build stages, actual Atlas Local Workbench screenshot, Stage/Apply distinction, GDS data-flow sequence and shared central knowledge/access diagram.

The current product label must be **GDS Frameworks** in every current scene and matching narration. Intro cues 7 and 8 and Run cue 2 already contain the renamed wording in the saved v9 files; preserve them exactly.

The closing must show **“Move GDS forward.”** followed by **“Keep project knowledge central and shared.”** Its final spoken words must be **“while keeping project knowledge central and shared.”** Those words remain in the saved v8 closing assets used by v9; do not re-edit or resynthesize them.

Deliver a local preview and a concise report of the actual integrity, lint/types, bundle and reference-frame results. State any runtime mismatch. Same source/media/timeline is the exact authored reproduction; do not promise byte-identical MP4 output across operating systems or encoders. The optional captions retain a system-font fallback, so cross-OS caption pixels can differ. No MP4 export is needed unless I explicitly ask for one.

---
