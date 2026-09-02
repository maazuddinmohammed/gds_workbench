# Staging

Load only after the user accepted the local digest and the current server draft was fetched.

Run local `prepare-stage` with the exact server pending datasets returned by the Change Set read. It reconciles by canonical key, refuses conflicts or a stale draft binding, merges non-overlapping records, and writes a deterministic manifest under `tasks/<task>.stage/`. Do not calculate chunks or hashes manually.

Follow `manifest.json` in this order:

1. If `direct` is present, read its file and make one direct Stage call with that complete `changes` array and `starting_revision`.
2. For each batch, call Begin with its dataset, record count, chunk count, payload mode, optional payload bytes, and batch hash.
3. Put every chunk in index order. In `records` mode the file is the `records` value. In `json_fragments` mode the file contains the `payload_fragment_base64` string and is allowed only for Model `generated_code`.
4. Commit that batch. Use every returned `draft_revision` as the expected revision for the next direct or Begin/Commit operation.
5. After all entries succeed, fetch the draft again and cache its new active revision before server validation.

A present dataset is its complete pending replacement. Direct Stage replaces all listed datasets once; repeated direct calls do not append. Empty replacements must remain in the direct request because a batch cannot be empty.

The planner keeps a direct request at or below 1 MiB. Metadata record chunks are at most 450 KiB and 5,000 records; Model record chunks use a conservative 900 KiB and 5,000 records. A batch has at most 64 chunks. These are packing rules, not output quotas.
