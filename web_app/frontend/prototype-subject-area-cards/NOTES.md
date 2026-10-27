# Subject Area cards — temporary

Throwaway prototype. It runs the real Atlas frontend with sample data and changes one
thing: lists of Subject Areas show as cards instead of tables. `src/` is untouched.

## Run / discard

From the repository root:

```sh
node_modules/.bin/vite --config web_app/frontend/prototype-subject-area-cards/vite.config.mjs
```

Open <http://127.0.0.1:4331/prototype-subject-area-cards/>. The **Prototype** switch
(bottom right) flips between **Cards** and **Current table** with the same data.
Delete this folder once a decision is made.

## What changes

- Subject Areas show as a vertical list of cards, one per row: name, definition and
  counts, with **Open** on the right. The whole card also opens the area.
- Subject Areas page (Areas view): counts are Objects and Attributes. Checkboxes still
  drive Lock/Unlock/Deactivate; Locked and Inactive show beside the name.
- Logical and Dimensional pages, Subject Areas tab: counts are Objects and that layer's
  Entities. **Open** goes to the area's existing page.
- Everything else is unchanged: Entities, Relationships, Unassigned Objects and all
  detail pages stay tables.

## How it works

- `vite.config.mjs` serves `SubjectAreasScreen.tsx` and `ModelSubjectAreas.tsx` from this
  folder in place of the originals. Only `AreasLedger` and `ModelSubjectAreasLedger` differ.
- `sample-data.ts` answers the API with invented data (shapes copied from the local
  stack). Writes are refused.

## If built for real

- Frontend only: the cards use fields the API already returns. Move the two card versions
  into `src` in place of the tables, add tests for cards, selection and Open, and note the
  card rule in `docs/design-system.md`.

## Decision

Pending user review.
