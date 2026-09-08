import { StageAuthenticationError } from "./auth.js";
import { StageMcpError } from "./mcp-client.js";
import { StageProfileError } from "./profile.js";
import { StageRunnerError, type StageReceipt } from "./stage-runner.js";

export interface StageFailureReceipt {
  schemaVersion: "1.0";
  status: "failed";
  code: string;
  message: string;
  stageStarted: boolean;
  legacyFallbackAllowed: boolean;
}

export type StageToolReceipt = StageReceipt | StageFailureReceipt;

export function failureReceipt(error: unknown, stageStarted: boolean): StageFailureReceipt {
  const safe =
    error instanceof StageRunnerError ||
    error instanceof StageMcpError ||
    error instanceof StageAuthenticationError
      ? { code: error.code, message: error.message }
      : error instanceof StageProfileError
        ? { code: "PROFILE_INVALID", message: error.message }
        : {
            code: "INTERNAL_ERROR",
            message: "GDS Stage Runner could not complete the operation.",
          };
  return {
    schemaVersion: "1.0",
    status: "failed",
    code: safe.code,
    message: safe.message,
    stageStarted,
    legacyFallbackAllowed: !stageStarted,
  };
}
