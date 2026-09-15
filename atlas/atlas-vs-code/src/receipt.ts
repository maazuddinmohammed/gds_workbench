import { randomUUID } from "node:crypto";
import { link, lstat, realpath, unlink, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, sep } from "node:path";
import { StageAuthenticationError } from "./auth.js";
import { StageMcpError } from "./mcp-client.js";
import { StageProfileError } from "./profile.js";
import { StageRunnerError, type StageReceipt } from "./stage-runner.js";

export interface StageFailureReceipt {
  schema_version: "1.0";
  status: "failed";
  code: string;
  message: string;
  stage_started: boolean;
  legacy_fallback_allowed: boolean;
}

export type StageToolReceipt = StageReceipt | StageFailureReceipt;

export function failureReceipt(error: unknown, stage_started: boolean): StageFailureReceipt {
  const safe =
    error instanceof StageRunnerError ||
    error instanceof StageMcpError ||
    error instanceof StageAuthenticationError
      ? { code: error.code, message: error.message }
      : error instanceof StageProfileError
        ? { code: "PROFILE_INVALID", message: error.message }
        : {
            code: "INTERNAL_ERROR",
            message: "Atlas Stage Runner could not complete the operation.",
          };
  return {
    schema_version: "1.0",
    status: "failed",
    code: safe.code,
    message: safe.message,
    stage_started,
    legacy_fallback_allowed: !stage_started,
  };
}

// Receipt exports are new files only. Approval, draft and Snapshot files are never destinations.
export async function exportReceipt<T extends object>(
  receipt: T,
  outputFile: unknown,
  roots: string[],
): Promise<T | (T & { receipt_export: { status: "failed"; code: string; message: string } })> {
  if (outputFile === undefined) return receipt;
  let temporary: string | undefined;
  try {
    if (typeof outputFile !== "string" || outputFile.length > 4_096 || !isAbsolute(outputFile) ||
        !outputFile.endsWith(".json")) throw new Error("invalid output");
    // Resolve the trusted root, then reject symlinks in every destination component.
    let destination: string | undefined;
    for (const root of roots) {
      const lexical = relative(root, outputFile);
      if (isAbsolute(lexical) || lexical.split(sep).some(part => !part || part === ".." || part === ".")) continue;
      const parts = lexical.split(sep);
      const atlasIndex = parts.indexOf(".atlas");
      if (atlasIndex < 0 || parts[atlasIndex + 1] !== "temp" || atlasIndex + 2 >= parts.length) continue;
      let directory = await realpath(root);
      for (const part of parts.slice(0, -1)) {
        directory = join(directory, part);
        const stat = await lstat(directory);
        if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error("invalid directory");
      }
      if (await realpath(directory) !== directory) throw new Error("changed directory");
      destination = join(directory, parts.at(-1)!);
      break;
    }
    if (!destination) throw new Error("outside receipt directory");
    const bytes = Buffer.from(`${JSON.stringify(receipt, null, 2)}\n`, "utf8");
    if (bytes.length > 32 * 1024) throw new Error("receipt limit");
    temporary = join(dirname(destination), `.atlas-receipt-${randomUUID()}.tmp`);
    await writeFile(temporary, bytes, { flag: "wx", mode: 0o600 });
    if (await realpath(dirname(destination)) !== dirname(destination)) throw new Error("changed directory");
    // Atomic no-clobber publication also rejects existing files and dangling symlinks.
    await link(temporary, destination);
    return receipt;
  } catch {
    // A successful Stage is durable already; a failed optional export must not invite replay.
    return { ...receipt, receipt_export: { status: "failed", code: "RECEIPT_EXPORT_FAILED",
      message: "Receipt export failed. Use a new .json path in an existing workspace .atlas/temp directory; the operation outcome above is unchanged." } };
  } finally {
    if (temporary) await unlink(temporary).catch(() => undefined);
  }
}
