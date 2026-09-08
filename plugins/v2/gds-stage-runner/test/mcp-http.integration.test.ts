import type { AddressInfo } from "node:net";

import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import type { Request, Response } from "express";
import { afterEach, describe, expect, test } from "vitest";
import * as z from "zod/v4";

import { createStageMcpClient } from "../src/mcp-client.js";

const servers: Array<{ close(callback: (error?: Error) => void): void }> = [];

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map(
      (server) =>
        new Promise<void>((resolve, reject) =>
          server.close((error) => (error === undefined ? resolve() : reject(error))),
        ),
    ),
  );
});

describe("MCP Streamable HTTP integration", () => {
  test("does not forward Stage payloads through an HTTP redirect", async () => {
    const app = createMcpExpressApp();
    let forwarded = 0;
    app.post("/unexpected", (_request: Request, response: Response) => {
      forwarded += 1;
      response.status(400).end();
    });
    app.post("/mcp", async (request: Request, response: Response) => {
      if (request.body.method === "tools/call") {
        response.redirect(307, "/unexpected");
        return;
      }
      const server = new McpServer({ name: "redirect-test", version: "1.0.0" });
      const transport = new StreamableHTTPServerTransport({});
      await server.connect(transport as unknown as Transport);
      response.on("close", () => { void server.close(); });
      await transport.handleRequest(request, response, request.body);
    });
    const httpServer = app.listen(0, "127.0.0.1");
    servers.push(httpServer);
    await new Promise<void>((resolve, reject) => {
      httpServer.once("listening", resolve);
      httpServer.once("error", reject);
    });
    const port = (httpServer.address() as AddressInfo).port;
    const client = await createStageMcpClient({
      name: "local", endpoint: new URL(`http://127.0.0.1:${port}/mcp`), authentication: "none",
    });
    try {
      await expect(client.callTool("stage_metadata_change_set", { records: [] }))
        .rejects.toMatchObject({ code: "MCP_OUTCOME_UNKNOWN" });
      expect(forwarded).toBe(0);
    } finally {
      await client.close();
    }
  });

  test("sends the in-memory bearer token and exposes only structured tool output", async () => {
    const app = createMcpExpressApp();
    app.post("/mcp", async (request: Request, response: Response) => {
      if (request.headers.authorization !== "Bearer test-only-token") {
        response.status(401).set("WWW-Authenticate", "Bearer").end();
        return;
      }
      const server = new McpServer({ name: "gds-test", version: "1.0.0" });
      server.registerTool(
        "list_tenants",
        {
          description: "Return a bounded test tenant list.",
          inputSchema: { page_size: z.number().int().positive() },
          outputSchema: { tenants: z.array(z.object({ tenant_id: z.number().int() })) },
        },
        async () => ({
          content: [{ type: "text", text: "raw response must remain internal" }],
          structuredContent: { tenants: [{ tenant_id: 17 }] },
        }),
      );
      const transport = new StreamableHTTPServerTransport({});
      await server.connect(transport as unknown as Transport);
      await transport.handleRequest(request, response, request.body);
      response.on("close", () => {
        void transport.close();
        void server.close();
      });
    });
    const httpServer = app.listen(0, "127.0.0.1");
    servers.push(httpServer);
    await new Promise<void>((resolve, reject) => {
      httpServer.once("listening", resolve);
      httpServer.once("error", reject);
    });
    const port = (httpServer.address() as AddressInfo).port;
    const profile = {
      name: "production" as const,
      endpoint: new URL(`http://127.0.0.1:${port}/mcp`),
      authentication: "microsoft" as const,
    };
    const client = await createStageMcpClient(profile, async () => "test-only-token");

    const result = await client.callTool("list_tenants", { page_size: 1 });

    expect(result).toEqual({ tenants: [{ tenant_id: 17 }] });
    expect(JSON.stringify(result)).not.toContain("raw response");
    await client.close();
  });
});
