import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { UnauthorizedError } from "@modelcontextprotocol/sdk/client/auth.js";
import { StreamableHTTPClientTransport, StreamableHTTPError } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";

import type { McpToolClient } from "./stage-runner.js";
import type { ResolvedStageProfile } from "./profile.js";
import { StageAuthenticationError } from "./auth.js";

interface ProtocolToolResult {
  isError?: boolean;
  structuredContent?: unknown;
  content?: unknown;
}

export interface ProtocolConnection {
  callTool(name: string, input: Record<string, unknown>): Promise<ProtocolToolResult>;
  close(): Promise<void>;
}

export type ProtocolConnector = (
  endpoint: URL,
  accessToken: string | undefined,
) => Promise<ProtocolConnection>;

export type AccessTokenSupplier = (forceNewSession: boolean) => Promise<string>;

export class ProtocolUnauthorizedError extends Error {
  constructor() {
    super("unauthorized");
    this.name = "ProtocolUnauthorizedError";
  }
}

export class StageMcpError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
    this.name = "StageMcpError";
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function safeToolErrorCode(content: unknown): string {
  if (!Array.isArray(content)) return "MCP_OPERATION_REJECTED";
  for (const part of content) {
    if (!isObject(part) || typeof part.text !== "string") continue;
    const match = /^([a-z][a-z0-9_]{1,63}):/.exec(part.text);
    if (match?.[1]) return match[1];
  }
  return "MCP_OPERATION_REJECTED";
}

function couldHaveWritten(toolName: string): boolean {
  return /^(stage|begin|put|commit)_(metadata|model)_/.test(toolName);
}

class ManagedStageMcpClient implements McpToolClient {
  private connection: ProtocolConnection | undefined;

  constructor(
    private readonly profile: ResolvedStageProfile,
    private readonly tokenSupplier: AccessTokenSupplier | undefined,
    private readonly connector: ProtocolConnector,
  ) {}

  private async connect(forceNewSession: boolean): Promise<ProtocolConnection> {
    if (this.connection !== undefined) return this.connection;
    let accessToken: string | undefined;
    if (this.profile.authentication === "microsoft") {
      if (this.tokenSupplier === undefined) {
        throw new StageMcpError(
          "AUTHENTICATION_REQUIRED",
          "Microsoft authentication is unavailable.",
        );
      }
      accessToken = await this.tokenSupplier(forceNewSession);
    }
    this.connection = await this.connector(this.profile.endpoint, accessToken);
    return this.connection;
  }

  private async discardConnection(): Promise<void> {
    const connection = this.connection;
    this.connection = undefined;
    if (connection !== undefined) await connection.close().catch(() => undefined);
  }

  async callTool(name: string, input: Record<string, unknown>): Promise<unknown> {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const connection = await this.connect(attempt === 1);
        const result = await connection.callTool(name, input);
        if (result.isError === true) {
          throw new StageMcpError(
            safeToolErrorCode(result.content),
            "GDS MCP rejected the operation.",
          );
        }
        if (!isObject(result.structuredContent)) {
          throw new StageMcpError(
            "MCP_RESPONSE_INVALID",
            "GDS MCP returned no structured result.",
          );
        }
        return result.structuredContent;
      } catch (error) {
        if (error instanceof StageMcpError || error instanceof StageAuthenticationError) throw error;
        if (error instanceof ProtocolUnauthorizedError) {
          await this.discardConnection();
          if (this.profile.authentication !== "microsoft") {
            throw new StageMcpError(
              "PROFILE_AUTH_MISMATCH",
              "The selected no-auth profile was rejected by GDS MCP.",
            );
          }
          if (attempt === 0) continue;
          throw new StageMcpError(
            "AUTHENTICATION_REQUIRED",
            "Microsoft authentication was rejected by GDS MCP.",
          );
        }
        if (couldHaveWritten(name)) {
          throw new StageMcpError(
            "MCP_OUTCOME_UNKNOWN",
            "The Stage operation outcome is unknown; verify before retrying.",
          );
        }
        // Report only known categories/statuses; SDK messages can contain response bodies and URLs.
        if (error instanceof StreamableHTTPError) {
          if (typeof error.code === "number" && Number.isInteger(error.code) && error.code >= 100 && error.code <= 599) {
            throw new StageMcpError(
              "MCP_HTTP_ERROR",
              `GDS MCP returned HTTP ${error.code}. Check server access and the selected Stage Runner profile.`,
            );
          }
          throw new StageMcpError("MCP_RESPONSE_INVALID", "GDS MCP returned an unsupported HTTP response.");
        }
        const cause = error instanceof Error && error.cause !== undefined ? error.cause : error;
        const networkCode = error instanceof McpError && error.code === ErrorCode.RequestTimeout
          ? "ETIMEDOUT"
          : isObject(cause) && typeof cause.code === "string" ? cause.code
            : cause instanceof Error ? /^net::(ERR_[A-Z_]+)$/.exec(cause.message)?.[1] : undefined;
        const failures: Array<[string[], string, string]> = [
          [["ENOTFOUND", "EAI_AGAIN", "ERR_NAME_NOT_RESOLVED"], "MCP_DNS_FAILED",
            "GDS MCP DNS lookup failed. Check the server address, VPN, and DNS access."],
          [["CERT_HAS_EXPIRED", "UNABLE_TO_VERIFY_LEAF_SIGNATURE", "UNABLE_TO_GET_ISSUER_CERT_LOCALLY",
            "SELF_SIGNED_CERT_IN_CHAIN", "DEPTH_ZERO_SELF_SIGNED_CERT", "ERR_TLS_CERT_ALTNAME_INVALID",
            "ERR_CERT_AUTHORITY_INVALID", "ERR_CERT_DATE_INVALID", "ERR_CERT_COMMON_NAME_INVALID"], "MCP_TLS_FAILED",
            "GDS MCP certificate verification failed. Check the server certificate and VS Code's trusted certificates."],
          [["ETIMEDOUT", "UND_ERR_CONNECT_TIMEOUT", "UND_ERR_HEADERS_TIMEOUT", "UND_ERR_BODY_TIMEOUT",
            "ERR_CONNECTION_TIMED_OUT", "ERR_TIMED_OUT"], "MCP_TIMEOUT",
            "The GDS MCP connection timed out. Check server availability and network access."],
          [["ERR_PROXY_CONNECTION_FAILED", "ERR_TUNNEL_CONNECTION_FAILED", "ERR_NO_SUPPORTED_PROXIES"], "MCP_PROXY_FAILED",
            "The GDS MCP proxy connection failed. Check VS Code's proxy settings."],
          [["ECONNREFUSED", "ECONNRESET", "EHOSTUNREACH", "ENETUNREACH", "UND_ERR_SOCKET",
            "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_RESET", "ERR_ADDRESS_UNREACHABLE"], "MCP_CONNECTION_FAILED",
            "The GDS MCP connection was refused, interrupted, or unreachable. Check server and network access."],
        ];
        for (const [codes, code, message] of failures) {
          if (networkCode !== undefined && codes.includes(networkCode)) throw new StageMcpError(code, message);
        }
        throw new StageMcpError("MCP_UNAVAILABLE", "GDS MCP is unavailable.");
      }
    }
    throw new StageMcpError("AUTHENTICATION_REQUIRED", "Microsoft authentication failed.");
  }

  async close(): Promise<void> {
    await this.discardConnection();
  }
}

export async function connectSdkProtocol(
  endpoint: URL,
  accessToken: string | undefined,
): Promise<ProtocolConnection> {
  const client = new Client({ name: "gds-stage-runner", version: "0.1.1" });
  const transport = new StreamableHTTPClientTransport(endpoint, {
    requestInit: {
      redirect: "error",
      ...(accessToken === undefined ? {} : { headers: { authorization: `Bearer ${accessToken}` } }),
    },
  });
  try {
    await client.connect(transport as unknown as Transport);
  } catch (error) {
    await transport.close().catch(() => undefined);
    if (error instanceof UnauthorizedError) throw new ProtocolUnauthorizedError();
    throw error;
  }
  return {
    async callTool(name, input) {
      try {
        const result = await client.callTool({ name, arguments: input });
        return {
          ...(typeof result.isError === "boolean" ? { isError: result.isError } : {}),
          ...(result.structuredContent === undefined
            ? {}
            : { structuredContent: result.structuredContent }),
          content: result.content,
        };
      } catch (error) {
        if (error instanceof UnauthorizedError) throw new ProtocolUnauthorizedError();
        throw error;
      }
    },
    async close() {
      await client.close();
    },
  };
}

export async function createStageMcpClient(
  profile: ResolvedStageProfile,
  tokenSupplier?: AccessTokenSupplier,
  connector: ProtocolConnector = connectSdkProtocol,
): Promise<ManagedStageMcpClient> {
  return new ManagedStageMcpClient(profile, tokenSupplier, connector);
}
