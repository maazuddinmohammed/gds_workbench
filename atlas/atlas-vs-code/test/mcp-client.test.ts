import { describe, expect, test, vi } from "vitest";
import { StreamableHTTPError } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";

import {
  createStageMcpClient,
  ProtocolUnauthorizedError,
  StageMcpError,
  type ProtocolConnector,
} from "../src/mcp-client.js";
import type { ResolvedStageProfile } from "../src/profile.js";
import { StageAuthenticationError } from "../src/auth.js";

const LOCAL_PROFILE: ResolvedStageProfile = {
  name: "local",
  endpoint: new URL("http://127.0.0.1:8000/mcp"),
  authentication: "none",
};
const PRODUCTION_PROFILE: ResolvedStageProfile = {
  name: "production",
  endpoint: new URL("https://gds.example.com/mcp"),
  authentication: "microsoft",
};

describe("createStageMcpClient", () => {
  test.each([
    [Object.assign(new Error("private host"), { code: "ENOTFOUND" }), "MCP_DNS_FAILED", "DNS"],
    [new TypeError("fetch failed: private URL", {
      cause: Object.assign(new Error("private certificate"), { code: "UNABLE_TO_VERIFY_LEAF_SIGNATURE" }),
    }), "MCP_TLS_FAILED", "certificate"],
    [new Error("net::ERR_CERT_AUTHORITY_INVALID"), "MCP_TLS_FAILED", "certificate"],
    [new Error("net::ERR_PROXY_CONNECTION_FAILED"), "MCP_PROXY_FAILED", "proxy"],
    [Object.assign(new Error("private host"), { code: "ECONNREFUSED" }), "MCP_CONNECTION_FAILED", "connection"],
    [new TypeError("fetch failed", {
      cause: Object.assign(new Error("private host"), { code: "UND_ERR_CONNECT_TIMEOUT" }),
    }), "MCP_TIMEOUT", "timed out"],
    [new McpError(ErrorCode.RequestTimeout, "private request"), "MCP_TIMEOUT", "timed out"],
    [new StreamableHTTPError(403, "private server response"), "MCP_HTTP_ERROR", "HTTP 403"],
    [new StreamableHTTPError(-1, "private content type"), "MCP_RESPONSE_INVALID", "response"],
    [Object.assign(new Error("private unexpected detail"), { code: "private_unknown_code" }), "MCP_UNAVAILABLE", "unavailable"],
  ])("reports a safe read-failure category: %s", async (error, code, detail) => {
    const connector = vi.fn<ProtocolConnector>(async () => { throw error; });
    const client = await createStageMcpClient(LOCAL_PROFILE, undefined, connector);

    const failure = await client.callTool("list_tenants", { page_size: 1 }).catch((error: unknown) => error);
    expect(failure).toMatchObject({
      code, message: expect.stringContaining(detail),
    });
    expect((failure as Error).message).not.toContain("private");
    expect(connector).toHaveBeenCalledOnce();
  });

  test("network diagnostics never make a failed write safe to retry", async () => {
    const connector = vi.fn<ProtocolConnector>(async () => ({
      async callTool() { throw new StreamableHTTPError(502, "private server response"); },
      async close() {},
    }));
    const client = await createStageMcpClient(LOCAL_PROFILE, undefined, connector);

    await expect(client.callTool("commit_model_stage_batch", {})).rejects.toMatchObject({
      code: "MCP_OUTCOME_UNKNOWN",
      message: "The Stage operation outcome is unknown; verify before retrying.",
    });
    expect(connector).toHaveBeenCalledOnce();
  });

  test("does not retry a write after losing its response", async () => {
    const callTool = vi.fn(async () => { throw new Error("private connection detail"); });
    const close = vi.fn(async () => {});
    const connector = vi.fn<ProtocolConnector>(async () => ({ callTool, close }));
    const client = await createStageMcpClient(LOCAL_PROFILE, undefined, connector);

    await expect(client.callTool("commit_model_stage_batch", {})).rejects.toMatchObject({
      code: "MCP_OUTCOME_UNKNOWN",
      message: "The Stage operation outcome is unknown; verify before retrying.",
    });
    expect(callTool).toHaveBeenCalledOnce();
    expect(connector).toHaveBeenCalledOnce();
    await client.close();
    expect(close).toHaveBeenCalledOnce();
  });

  test("preserves the safe sign-in failure instead of reporting a server outage", async () => {
    const connector = vi.fn<ProtocolConnector>();
    const client = await createStageMcpClient(PRODUCTION_PROFILE, async () => {
      throw new StageAuthenticationError("AUTHENTICATION_REQUIRED", "Microsoft sign-in was not completed.");
    }, connector);

    await expect(client.callTool("list_tenants", {})).rejects.toMatchObject({
      code: "AUTHENTICATION_REQUIRED", message: "Microsoft sign-in was not completed.",
    });
    expect(connector).not.toHaveBeenCalled();
  });

  test("returns only structured content and never forwards raw MCP content", async () => {
    const connector = vi.fn<ProtocolConnector>(async () => ({
      async callTool() {
        return {
          isError: false,
          structuredContent: { status: "active", draft_revision: 2 },
          content: [{ type: "text", text: "raw physical row" }],
        };
      },
      async close() {},
    }));
    const client = await createStageMcpClient(LOCAL_PROFILE, undefined, connector);

    const result = await client.callTool("get_metadata_change_set", {
      tenant_id: 1,
    });

    expect(result).toEqual({ status: "active", draft_revision: 2 });
    expect(JSON.stringify(result)).not.toContain("raw physical row");
    expect(connector).toHaveBeenCalledWith(LOCAL_PROFILE.endpoint, undefined);
    await client.close();
  });

  test("maps tool failures to a bounded code without exposing raw content", async () => {
    const connector = vi.fn<ProtocolConnector>(async () => ({
      async callTool() {
        return {
          isError: true,
          content: [{ type: "text", text: "draft_revision_conflict: secret raw detail" }],
        };
      },
      async close() {},
    }));
    const client = await createStageMcpClient(LOCAL_PROFILE, undefined, connector);

    const operation = client.callTool("stage_metadata_change_set", {});

    await expect(operation).rejects.toMatchObject({
      code: "draft_revision_conflict",
      message: "GDS MCP rejected the operation.",
    });
  });

  test("reauthenticates once after an HTTP 401 and retries with the renewed session", async () => {
    const closed: boolean[] = [];
    let connection = 0;
    const connector = vi.fn<ProtocolConnector>(async (_endpoint, token) => {
      const current = connection++;
      expect(token).toBe(current === 0 ? "initial" : "renewed");
      return {
        async callTool() {
          if (current === 0) throw new ProtocolUnauthorizedError();
          return { isError: false, structuredContent: { tenants: [] }, content: [] };
        },
        async close() {
          closed[current] = true;
        },
      };
    });
    const tokenSupplier = vi.fn(async (force: boolean) => (force ? "renewed" : "initial"));
    const client = await createStageMcpClient(PRODUCTION_PROFILE, tokenSupplier, connector);

    const result = await client.callTool("list_tenants", { page_size: 1 });

    expect(result).toEqual({ tenants: [] });
    expect(tokenSupplier.mock.calls).toEqual([[false], [true]]);
    expect(closed[0]).toBe(true);
    expect(connector).toHaveBeenCalledTimes(2);
    await client.close();
  });

  test("never attempts Microsoft auth for a no-auth profile", async () => {
    const connector = vi.fn<ProtocolConnector>(async () => {
      throw new ProtocolUnauthorizedError();
    });
    const tokenSupplier = vi.fn(async () => "must-not-be-used");
    const client = await createStageMcpClient(LOCAL_PROFILE, tokenSupplier, connector);

    const operation = client.callTool("list_tenants", {});

    await expect(operation).rejects.toMatchObject({
      code: "PROFILE_AUTH_MISMATCH",
    });
    expect(tokenSupplier).not.toHaveBeenCalled();
  });
});
