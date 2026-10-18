import { ApiError } from "../core/http";

export interface ArchiveDownload {
  blob: Blob;
  filename: string;
}

export interface LayerArchiveRequest {
  entity_type: "logical_entity" | "dimensional_entity";
  expected_project_revision: number;
}

export async function readArchiveDownload(response: Response): Promise<ArchiveDownload> {
  const contentType = response.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase();
  const filename = /^attachment\s*;\s*filename="([A-Za-z0-9][A-Za-z0-9._-]{0,179}\.zip)"\s*$/i
    .exec(response.headers.get("content-disposition") ?? "")?.[1];
  if (contentType !== "application/zip" || !filename) {
    throw new ApiError(502, "invalid_response", null);
  }
  return { blob: await response.blob(), filename };
}

export function saveArchiveDownload({ blob, filename }: ArchiveDownload): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  try {
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(url);
  }
}

export function archiveDownloadError(error: unknown, kind: "sql" | "validation"): string {
  if (error instanceof ApiError) {
    if (error.code === "project_revision_conflict") {
      return "The Project changed. Refresh, then retry the export.";
    }
    if (error.code === "generated_sql_export_empty") {
      return "No active SQL files are available for this layer. Refresh after SQL files are saved.";
    }
    if (error.code === "validation_export_empty") {
      return "No active validation checks are available for this layer. Refresh after checks are saved.";
    }
    if (error.code === "invalid_request") {
      return kind === "sql"
        ? "This export could not be prepared. Refresh and retry; if it continues, review the saved SQL files."
        : "This export could not be prepared. Refresh and retry; if it continues, review the saved validation definitions.";
    }
    if (error.code === "generated_sql_bundle_limit_exceeded") {
      return "The SQL export exceeds the archive limit. Download individual SQL files instead.";
    }
    if (error.code === "validation_bundle_limit_exceeded") {
      return "The validation export exceeds the archive limit. Open individual checks to copy their SQL and criteria.";
    }
    if (error.status === 403 || error.status === 404) {
      return "This Project is no longer accessible. Refresh to check your access.";
    }
    if (error.code === "invalid_response") {
      return "The server did not return a valid ZIP download. Retry, or contact your administrator if this continues.";
    }
  }
  return "The export could not be downloaded. Retry, or refresh the Project and try again.";
}
