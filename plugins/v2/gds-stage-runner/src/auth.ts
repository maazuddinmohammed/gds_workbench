const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_METADATA_BYTES = 32 * 1024;

export interface MicrosoftAuthenticationSession {
  accessToken: string;
}

export interface MicrosoftChallengeRequest {
  wwwAuthenticate: string;
  fallbackScopes: readonly string[];
}

export interface MicrosoftSessionOptions {
  createIfNone?: { detail: string };
  forceNewSession?: { detail: string };
}

export type MicrosoftSessionGetter = (
  providerId: "microsoft",
  request: MicrosoftChallengeRequest,
  options: MicrosoftSessionOptions,
) => PromiseLike<MicrosoftAuthenticationSession | undefined>;

export class StageAuthenticationError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
    this.name = "StageAuthenticationError";
  }
}

function fail(code: string, message: string): never {
  throw new StageAuthenticationError(code, message);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export async function acquireMicrosoftAccessToken(
  endpoint: URL,
  getSession: MicrosoftSessionGetter,
  fetcher: typeof fetch = fetch,
  forceNewSession = false,
): Promise<string> {
  if (endpoint.protocol !== "https:" || endpoint.pathname !== "/mcp") {
    fail("ENDPOINT_MISMATCH", "Production MCP endpoint is invalid.");
  }
  const metadataUrl = new URL("/.well-known/oauth-protected-resource/mcp", endpoint);
  let response: Response;
  try {
    response = await fetcher(metadataUrl, {
      method: "GET",
      headers: { accept: "application/json" },
      redirect: "error",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    fail("AUTH_DISCOVERY_FAILED", "GDS authentication metadata could not be reached.");
  }
  const advertisedLength = Number(response.headers.get("content-length") ?? "0");
  if (!response.ok || (advertisedLength > 0 && advertisedLength > MAX_METADATA_BYTES)) {
    await response.body?.cancel().catch(() => undefined);
    fail("AUTH_DISCOVERY_FAILED", "GDS authentication metadata is unavailable.");
  }
  const chunks: Uint8Array[] = [];
  let bodyBytes = 0;
  try {
    if (response.body === null) fail("AUTH_DISCOVERY_FAILED", "GDS authentication metadata is empty.");
    for await (const chunk of response.body) {
      bodyBytes += chunk.byteLength;
      if (bodyBytes > MAX_METADATA_BYTES) {
        fail("AUTH_DISCOVERY_FAILED", "GDS authentication metadata is too large.");
      }
      chunks.push(chunk);
    }
  } catch (error) {
    if (error instanceof StageAuthenticationError) throw error;
    fail("AUTH_DISCOVERY_FAILED", "GDS authentication metadata is unreadable.");
  }
  let metadata: unknown;
  try {
    metadata = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    fail("AUTH_DISCOVERY_FAILED", "GDS authentication metadata is invalid.");
  }
  const expectedResource = endpoint.toString();
  const expectedScope = `${expectedResource}/workbench.access`;
  if (
    !isObject(metadata) ||
    metadata.resource !== expectedResource ||
    !Array.isArray(metadata.authorization_servers) ||
    metadata.authorization_servers.length !== 1 ||
    !Array.isArray(metadata.scopes_supported) ||
    metadata.scopes_supported.length !== 1 ||
    metadata.scopes_supported[0] !== expectedScope ||
    !Array.isArray(metadata.bearer_methods_supported) ||
    metadata.bearer_methods_supported.length !== 1 ||
    metadata.bearer_methods_supported[0] !== "header"
  ) {
    fail("AUTHORITY_MISMATCH", "GDS authentication metadata does not match this extension.");
  }
  let authorizationServer: URL;
  try {
    authorizationServer = new URL(String(metadata.authorization_servers[0]));
  } catch {
    fail("AUTHORITY_MISMATCH", "GDS authorization server is invalid.");
  }
  const authorityParts = authorizationServer.pathname.split("/").filter(Boolean);
  if (
    authorizationServer.protocol !== "https:" ||
    authorizationServer.hostname !== "login.microsoftonline.com" ||
    authorizationServer.port !== "" ||
    authorizationServer.username !== "" ||
    authorizationServer.password !== "" ||
    authorizationServer.search !== "" ||
    authorizationServer.hash !== "" ||
    authorityParts.length !== 2 ||
    !UUID.test(authorityParts[0] ?? "") ||
    authorityParts[1] !== "v2.0"
  ) {
    fail("AUTHORITY_MISMATCH", "GDS authorization server is not an exact Entra tenant.");
  }
  const challenge: MicrosoftChallengeRequest = {
    wwwAuthenticate:
      `Bearer resource_metadata="${metadataUrl.toString()}", ` +
      `scope="${expectedScope}"`,
    fallbackScopes: [expectedScope],
  };
  let session: MicrosoftAuthenticationSession | undefined;
  try {
    session = await getSession(
      "microsoft",
      challenge,
      forceNewSession
        ? {
            forceNewSession: {
              detail:
                "GDS Workbench rejected the expired session. Sign in again to continue Stage.",
            },
          }
        : {
            createIfNone: {
              detail: "Sign in with the Microsoft account authorized for GDS Workbench.",
            },
          },
    );
  } catch {
    fail("AUTHENTICATION_REQUIRED", "Microsoft sign-in was not completed.");
  }
  if (
    session === undefined ||
    typeof session.accessToken !== "string" ||
    !session.accessToken.trim() ||
    session.accessToken.length > 32_768
  ) {
    fail("AUTHENTICATION_REQUIRED", "Microsoft authentication returned no usable session.");
  }
  return session.accessToken;
}
