# Atlas product launch

## Current draft: Atlas-Film

**4:03**, 1920 × 1080, 30 fps. Open `/Atlas-Film` in Studio. Each scene is also
registered under the `Atlas-Film-Scenes` folder for focused editing.
Dark cinematic redesign with a persistent lifecycle rail, an original score and no narration.

| Start | Length | Scene | What it shows |
| --- | --- | --- | --- |
| 0:00 | 8s | Open | Atlas identity |
| 0:08 | 10s | Sources | Databases, NoSQL, APIs, files, streams, SaaS |
| 0:18 | 14s | Metadata | Tenant → System → Connection → Object → Attribute; Copy, Copy Group, Process |
| 0:32 | 16s | Bronze | Atlas metadata drives ADF triggers and Databricks notebooks into Bronze |
| 0:48 | 10s | Scope | Create Customer Orders 360 and pick its Model Input Scope |
| 0:58 | 30s | Evidence | Profile, Enrich, Analyze |
| 1:28 | 14s | Logical | 3NF Silver entities, keys, relationships, audit policy |
| 1:42 | 10s | Dimensional | Gold star schema with SCD Type 2 |
| 1:52 | 12s | Mapping | Rowset, filter and field expressions per target |
| 2:04 | 12s | Code | Generated SQL, code artifacts, validation definitions |
| 2:16 | 12s | Lakehouse | Handoff, GDS Framework, Silver and Gold loads |
| 2:28 | 8s | Two ways | Web app and plugin share governed records |
| 2:36 | 16s | Plugin connect | Copilot/Codex → plugin → Stage Runner → MCP → records; 12 skills |
| 2:52 | 32s | Plugin change | Custom request: context, impact, diff, Stage, Validate, Apply |
| 3:24 | 14s | Security | Entra identity, tenant isolation, cumulative roles, Super Admin limits |
| 3:38 | 16s | Concurrency | Tenant Lock, one run per tenant, revision checks |
| 3:54 | 9s | Close | Understand. Model. Build. Evolve. |

- `src/atlas-film/timeline.ts`: scene order and lengths. Retime here.
- `src/atlas-film/kit.tsx`: palette, typography, cards, flows, rail and other shared pieces.
- `src/atlas-film/Act*.tsx`: scenes grouped by act.
- `public/audio/atlas-film-score.wav`: original score from `python3 scripts/generate-film-score.py`
  (standard library only). Pass `--seconds` if the total length changes.

Render: `npx remotion render Atlas-Film out/atlas-film.mp4`.

Claims follow the repository docs: Apply saves governed records and never deploys;
target registration, process metadata and GDS execution are separate platform steps;
validation definitions are saved, not executed by Atlas; tenant security is role-based
authorization checked on the server; the plugin is shown in GitHub Copilot and Codex only.
Names, counts and SQL are fictional examples.

## Previous draft: Meet-Atlas

**4:21**, 1920 × 1080, 30 fps. Open `/Meet-Atlas` in Studio.
Music only; narration remains deferred. Each chapter is separately editable.

| Start | Duration | Chapter |
| --- | --- | --- |
| 0:00 | 7s | Meet Atlas |
| 0:07 | 51s | Sources expand, collapse, move; Atlas metadata; GDS Framework; Bronze ingestion |
| 0:58 | 32s | Define scope, profile, enrich, analyze, operational and dimensional design |
| 1:30 | 28s | Actual workspace; four navigation groups with camera moves and highlights |
| 1:58 | 45s | Actual Logical run: One shot, model, scope, progress, review, approval, applied result |
| 2:43 | 14s | Actual Excel export and SQL review/download controls |
| 2:57 | 18s | Deployment handoff, target/Process registration, GDS execution lifecycle |
| 3:15 | 36s | Illustrative Copilot ticket, dependencies, Stage/Validate/Apply, shared web state |
| 3:51 | 22s | Roles, tenant authorization, locks, run exclusivity and revision checks |
| 4:13 | 8s | From ticket to governed change |

The opening has separate motion and reading holds. Source Systems starts centered,
expands into six types, collapses to a database-only box, and moves right before the
copy appears. Metadata lives in a boxed Atlas symbol. Long padded metadata routes
connect Sources → Atlas → GDS Framework. ADF and Databricks appear while explaining
the Framework, then collapse into one Framework box. Data packets travel through it
to a boxed Databricks Lakehouse with a separated, highlighted Bronze layer.

Source Sans 3 is bundled locally. Actual application screenshots in
`public/captures/complete/` use fictional fixture data and an isolated disposable
PostgreSQL container, with fake AI and Databricks providers. Camera/pointer sequences
are edited demonstrations, not uncut recordings. Run time is condensed. They show
real controls and successful local review/Apply, not production model quality.

Product claims are grounded in repository code/docs and the user's GDS description:

- ADF owns triggers/pipelines; Databricks notebooks use metadata and ingest landing
  data to Bronze. SHIR/ADLS are intentionally omitted from the high-level view.
- Third normal form is a design goal, not a guaranteed automated certification.
- Web and plugin share governed persisted records. The web refreshes after Apply.
- Dependent model/mapping changes must be applied before downstream authoring.
  A stale SQL capture intentionally shows review required after upstream changes.
- Apply saves Atlas records. Deployment, target/Process registration and GDS
  execution are distinct platform steps, not automatic Atlas deployment.
- Roles, tenant-scoped authorization, owned locks, one running workflow per Tenant,
  revision checks and reviewed Apply are verified. Native database RLS policies
  were not found and are not claimed. Validation definitions do not imply executed
  Databricks checks. Claude Code support remains unconfirmed.

`src/launch-next/MeetAtlas.tsx` owns timing. `src/Root.tsx` registers the complete
video and its chapter previews. The previous 2:36 concept remains `Atlas-Launch`.
The separate tutorial is still a future video.

### Voice audition

An 11-second audition is saved at `out/meet-atlas-elevenlabs-sample.wav`:
ElevenLabs **Chris — Charming, Down-to-Earth**, Eleven v4, stability 0.5,
similarity 0.75. Generated directly in ElevenLabs on 2026-10-05. It includes the
existing instrumental at a lower level. Original narration:
`public/audio/meet-atlas-elevenlabs-chris-sample.mp3`.
Voice is deferred until the visuals are approved. The complete composition
remains music-only; saved voice samples are not included in the timeline.

### Infrastructure assets

Unmodified vendor SVGs are bundled in `public/brands/`:

- ADF and VM: [Microsoft Azure architecture icons](https://learn.microsoft.com/en-us/azure/architecture/icons/), V24.
- ADLS: the official Azure Storage Accounts icon, preserving its teal colors; no retired Gen1 icon is used.
- Databricks: [official Databricks repository asset](https://github.com/databricks/databricks-agent-skills/blob/main/assets/databricks.svg).
- Brand accents follow the source icons and [Databricks brand guidance](https://brand.databricks.com/iconography): Azure blue `#0078D4`, storage teal `#258277`, Databricks Lava `#FF3621` and Navy `#0B2026`.

Icons are not cropped, recolored, stretched, or used as the Atlas identity.

## Previous complete concept

Editable **2:36 music-only preview**, 1920 × 1080, 30 fps. Main composition: `Atlas-Launch`.
No narration or subtitle strip. Short scene headings and diagrams carry the story.
Twelve scene compositions remain independently editable in Remotion Studio.

Run `npm run dev`, then open the Studio URL at `/Atlas-Launch`.
`npm run lint` checks TypeScript and Remotion rules; `npm run build` creates the local bundle.

## Story

| Start | Duration | Scene                                                               |
| ----- | -------- | ------------------------------------------------------------------- |
| 0:00  | 8s       | Introduce Atlas and its value                                       |
| 0:08  | 16s      | SQL, NoSQL, streams, APIs, file systems, files                      |
| 0:24  | 12s      | Example metadata-driven GDS ingestion into Bronze                   |
| 0:36  | 13s      | Create Retail Sales and visibly select six sources                  |
| 0:49  | 24s      | Profile fields, enrich meaning, infer relationships; 8s each        |
| 1:13  | 15s      | Operational and dimensional models; 7.5s each                       |
| 1:28  | 11s      | Quantity × UnitPrice → SalesAmount                                  |
| 1:39  | 12s      | Generate SQL and author a validation definition                     |
| 1:51  | 13s      | Delivery, Process registration, GDS execution, Silver and Gold      |
| 2:04  | 10s      | Investigate a supplied pipeline failure with the plugin             |
| 2:14  | 14s      | Add loyalty tier across affected artifacts, then review and approve |
| 2:28  | 8s       | Design. Build. Evolve.                                              |

## Assets and editing

- `src/scenes/`: independent scene artwork, with frame-driven animation and reading holds.
- `src/objects.tsx`: original SVG source illustrations and an animated demonstration pointer.
- `src/design.tsx`: Atlas-derived colors, typography, mark, and diagram elements.
- `src/AtlasLaunch.tsx` and `src/Root.tsx`: scene durations and composition registration.
- `public/audio/score.wav`: original stereo instrumental score, spanning 156 seconds with an opening and closing fade. No speech or licensed samples.
- `scripts/generate-music.py`: deterministic local synthesis using Python's standard library. Run `npm run audio` to regenerate the earlier score. For the complete video run `python3 scripts/generate-music.py --seconds 261 --output score-complete.wav`. Match its length to the compositions after changing timing.
- `musicVolume` composition prop: music level, default 0.8.
- `out/narrated-v1-backup.zip`: recoverable previous narrated version, including source and audio. Unused narration/caption files have been removed from the active project.

Profile numbers, source records, SQL excerpts, and conversations are fictional. Product screens are enlarged illustrative reconstructions, not recordings of a deployed instance. The Atlas mark follows `web_app/frontend/src/shared/ui.tsx`.

The lifecycle distinguishes Atlas authoring, governed Apply, delivery handoff, and GDS execution. Saved validation definitions do not imply executed checks. Claude Code support and automatic deployment remain unconfirmed and are not advertised. The tutorial remains the next, separate video.

## Guidance

Built using [Remotion's official skills](https://github.com/remotion-dev/skills), including creation, markup, interactivity, and Studio guidance. Fonts are bundled locally using `@fontsource/inter` and `@fontsource/ibm-plex-mono`.

This project is separate from the application build. No production services or databases are used. The sibling `../atlas-launch.mp4` predates this project and remains unchanged.

Remotion usage remains subject to [Remotion's license](https://www.remotion.dev/license).
