import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../core/http";
import { archiveDownloadError, readArchiveDownload, saveArchiveDownload } from "./archiveDownload";

afterEach(() => vi.restoreAllMocks());

describe("archive downloads", () => {
  it.each([
    ["text/html", 'attachment; filename="export.zip"'],
    ["application/zip", 'attachment; filename="../export.zip"'],
    ["application/zip", 'attachment; filename="export.html"'],
    ["application/zip", ""],
  ])("rejects an unexpected download format or unsafe filename (%s, %s)", async (contentType, disposition) => {
    await expect(readArchiveDownload(new Response("untrusted response", {
      headers: { "content-type": contentType, "content-disposition": disposition },
    }))).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("releases its temporary URL and anchor even when browser download fails", () => {
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:archive");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => { throw new Error("download failed"); });
    expect(() => saveArchiveDownload({ blob: new Blob(["zip"]), filename: "export.zip" })).toThrow("download failed");
    expect(revoke).toHaveBeenCalledWith("blob:archive");
    expect(document.querySelector('a[download="export.zip"]')).toBeNull();
  });

  it.each([
    ["project_revision_conflict", "sql", "Refresh, then retry"],
    ["generated_sql_export_empty", "sql", "No active SQL files"],
    ["validation_export_empty", "validation", "No active validation checks"],
    ["invalid_request", "sql", "This export could not be prepared. Refresh and retry; if it continues, review the saved SQL files."],
    ["invalid_request", "validation", "This export could not be prepared. Refresh and retry; if it continues, review the saved validation definitions."],
    ["generated_sql_bundle_limit_exceeded", "sql", "Download individual SQL files"],
    ["validation_bundle_limit_exceeded", "validation", "Open individual checks"],
    ["invalid_response", "sql", "valid ZIP download"],
  ] as const)("explains %s safely for %s", (code, kind, message) => {
    expect(archiveDownloadError(new ApiError(400, code, null), kind)).toContain(message);
  });
});
