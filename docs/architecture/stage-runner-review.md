# Stage Runner review — 2026-09-05

Reviewed every handwritten extension source file, its dependencies on shared
plugin code, server Stage contracts, tests, build, and VSIX contents. Applied small
fixes; retained the current architecture and legacy fallback.

## Problems fixed

| Problem | Change |
| --- | --- |
| A linked Change Set folder could point outside the workspace. | Reject linked folders before reading payloads or contacting MCP. |
| Payloads were loaded entirely into memory before their size limit was checked. | Check size before hashing; stream the hash and reject files that change size while being read. |
| HTTP redirects could forward Stage payloads to another URL. | Reject redirects on every MCP request. Reproduced with a real loopback HTTP redirect. |
| Authentication discovery read an entire response before checking its 32 KiB limit. | Bound the streaming read and cancel oversized bodies. |
| Cancelled sign-in appeared as an MCP outage. | Preserve the authentication module's safe error code and message. |
| An acknowledgement with an unknown dataset and missing count could pass validation. | Require every acknowledged dataset to belong to the request. |
| Approval, payloads, or the request could change while server reads were pending. | Recheck the local request and its existing approval/snapshot bindings before the first write. |
| A small dataset could be staged before a later dataset failed local chunk limits. | Plan and validate all batches before writing anything. Avoid making an extra whole-payload buffer for ordinary record batches. |
| JavaScript and Python serialized some small decimals and Unicode object keys differently, breaking chunk hashes. | Correct the existing shared serializer; use it in the extension and fallback. Remove the extension's duplicate serializer. Raw-file approval digests retain their existing format. |

Each bug received a regression check that failed before its fix. Additional
tests cover the VS Code boundary: workspace trust, cancellation, receipt
redaction, connection cleanup, and fallback after a possible write. A lost write
response is never retried automatically.

## Verification

- Extension: 70 tests; TypeScript check; bundle and VSIX build.
- Shared Workbench JavaScript: 44 tests, including browser interaction tests.
- Related plugin and MCP Stage suites: 173 passed; Windows PowerShell test
  skipped on macOS. Database tests use only disposable PostgreSQL fixtures.
- Python server serializer comparison: 9,989 generated finite-number cases and
  1,000 Unicode key maps; permanent digest vectors also pass.
- VSIX opened in an isolated VS Code 1.136.1 host: activation, command/tool
  registration, input schema, and JSON result support pass.
- Rebuilt local plugin ZIP and extension VSIX; packaging tests check bundled
  files against their sources/build outputs.

The host test checks loading and API compatibility. Stage behavior is tested
with synthetic MCP responses, real loopback MCP transport tests, and the
existing server/database tests. This is not a live signed-in end-to-end Stage
against Azure. Windows execution and production Microsoft sign-in still need
verification in their actual environments. Nothing was deployed or published.

Keep the fallback until that live verification passes. Switching the extension
to VS Code's existing MCP connection remains a separate experiment, not part of
this review.
