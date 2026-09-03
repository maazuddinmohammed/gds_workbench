# Staging

Use only after accepting the local digest and fetching the current server draft.

Run `prepare-stage` once with exact server pending datasets. It reconciles keys and writes the operation manifest. Never stage record-wise, repack, or invent hashes.

Parse each local `payload_file` once into its named MCP argument; never transcribe or rebuild it.

Execute `manifest.json.operations` by `sequence`:

1. Direct: pass complete file value as `changes`; resolve revision source.
2. Begin: copy its fields and revision.
3. Put: copy its fields/ID; records become `records`, code fragments `payload_fragment_base64`.
4. Commit: use its ID/revision; carry returned revision as directed.
5. Refetch/cache the active draft, then validate server-side.

A present dataset replaces server pending; calls never append.

Prefer 64 KiB; enlarge only for the 64-chunk cap. Hard limits: Metadata 450 KiB/5,000 records; Model 1 MiB/5,000. Limits are not quotas.
