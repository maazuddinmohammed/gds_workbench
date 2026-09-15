import { describe, expect, test, vi } from "vitest";

import {
  acquireMicrosoftAccessToken,
  StageAuthenticationError,
  type MicrosoftSessionGetter,
} from "../src/auth.js";
import { PRODUCTION_MCP_URL } from "../src/profile.js";

const TENANT_ID = "11111111-1111-4111-8111-111111111111";

function metadata() {
  return {
    resource: PRODUCTION_MCP_URL,
    authorization_servers: [`https://login.microsoftonline.com/${TENANT_ID}/v2.0`],
    scopes_supported: [`${PRODUCTION_MCP_URL}/workbench.access`],
    bearer_methods_supported: ["header"],
  };
}

describe("acquireMicrosoftAccessToken", () => {
  test("stops a chunked metadata body at the byte limit without reading the rest", async () => {
    let chunksRead = 0;
    const cancelled = vi.fn();
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        chunksRead += 1;
        controller.enqueue(new Uint8Array(8 * 1024));
        if (chunksRead === 20) controller.close();
      },
      cancel: cancelled,
    }, { highWaterMark: 0 });
    const getSession = vi.fn<MicrosoftSessionGetter>();
    await expect(acquireMicrosoftAccessToken(
      new URL(PRODUCTION_MCP_URL), getSession, async () => new Response(body),
    )).rejects.toMatchObject({ code: "AUTH_DISCOVERY_FAILED" });
    expect(chunksRead).toBe(5);
    expect(cancelled).toHaveBeenCalledOnce();
    expect(getSession).not.toHaveBeenCalled();
  });

  test("uses the validated MCP scope and tenant for normal Microsoft sign-in", async () => {
    const fetcher = vi.fn(async () =>
      new Response(JSON.stringify(metadata()), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const getSession = vi.fn<MicrosoftSessionGetter>(async () => ({
      accessToken: "short-lived-token",
    }));

    const accessToken = await acquireMicrosoftAccessToken(
      new URL(PRODUCTION_MCP_URL),
      getSession,
      fetcher,
      false,
    );

    expect(accessToken).toBe("short-lived-token");
    expect(fetcher).toHaveBeenCalledWith(
      new URL(
        "/.well-known/oauth-protected-resource/mcp",
        PRODUCTION_MCP_URL,
      ),
      expect.objectContaining({ method: "GET", redirect: "error" }),
    );
    expect(getSession).toHaveBeenCalledWith(
      "microsoft",
      [`${PRODUCTION_MCP_URL}/workbench.access`, `VSCODE_TENANT:${TENANT_ID}`],
      {
        createIfNone: {
          detail: "Sign in with the Microsoft account authorized for GDS Workbench.",
        },
      },
    );
  });

  test("fails closed before sign-in when metadata names another tenant authority", async () => {
    const fetcher = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ...metadata(),
          authorization_servers: ["https://login.example.com/common/v2.0"],
        }),
        { status: 200 },
      ),
    );
    const getSession = vi.fn<MicrosoftSessionGetter>();

    const operation = acquireMicrosoftAccessToken(
      new URL(PRODUCTION_MCP_URL),
      getSession,
      fetcher,
      false,
    );

    await expect(operation).rejects.toMatchObject({
      code: "AUTHORITY_MISMATCH",
    });
    expect(getSession).not.toHaveBeenCalled();
  });

  test("uses an explicit VS Code reauthentication request after a legitimate 401", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify(metadata()), { status: 200 }));
    const getSession = vi.fn<MicrosoftSessionGetter>(async () => ({ accessToken: "renewed" }));

    await acquireMicrosoftAccessToken(
      new URL(PRODUCTION_MCP_URL),
      getSession,
      fetcher,
      true,
    );

    expect(getSession.mock.calls[0]?.[2]).toEqual({
      forceNewSession: {
        detail: "GDS Workbench rejected the expired session. Sign in again to continue Stage.",
      },
    });
    expect(getSession.mock.calls[0]?.[1]).toEqual([
      `${PRODUCTION_MCP_URL}/workbench.access`, `VSCODE_TENANT:${TENANT_ID}`,
    ]);
  });
});
