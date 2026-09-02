# Staging

Load only after local-digest acceptance and fetching the current server draft.

Run `prepare-stage` once with the exact server pending datasets. It reconciles normalized keys, rejects conflicts/stale bindings, combines non-overlap, and writes `tasks/<task>.stage/manifest.json`. Never stage record by record or invent chunks/hashes.

Execute `manifest.json.operations` by `sequence`:

1. Direct Stage: use `payload_file` as the complete `changes`; resolve `expected_revision_from` exactly.
2. Begin: copy its dataset, counts, mode, optional bytes, batch hash, and revision.
3. Put: use its payload file, index, hash, and referenced Begin `stage_batch_id`. `records` files become `records`; Model `generated_code` fragment files become `payload_fragment_base64`.
4. Commit: use the referenced Begin ID/revision. Carry the returned revision only where the next operation directs.
5. When all operations succeed, refetch and cache the active draft revision before server validation.

A present dataset replaces its complete pending server dataset. Repeated direct calls do not append. Empty replacements remain direct because batches cannot be empty.

Limits: direct request 1 MiB; Metadata chunks 450 KiB/5,000 records; Model record chunks 900 KiB/5,000; 64 chunks per batch. Metadata's server contract enforces 450 KiB. These are packing limits, not output quotas.
