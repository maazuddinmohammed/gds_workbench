export const PRODUCTION_MCP_URL =
  "https://gds-test-workbench-hsemb2a9cuacd0gx.canadacentral-01.azurewebsites.net/mcp";

export type StageProfileName = "production" | "local" | "azureLocalTest";

export interface ResolvedStageProfile {
  name: StageProfileName;
  endpoint: URL;
  authentication: "microsoft" | "none";
}

export class StageProfileError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StageProfileError";
  }
}

export function resolveStageProfile(
  name: string,
  localUrl: string,
): ResolvedStageProfile {
  if (name === "production" || name === "azureLocalTest") {
    return {
      name,
      endpoint: new URL(PRODUCTION_MCP_URL),
      authentication: name === "production" ? "microsoft" : "none",
    };
  }
  if (name !== "local") {
    throw new StageProfileError("GDS Stage Runner profile is invalid.");
  }
  let endpoint: URL;
  try {
    endpoint = new URL(localUrl);
  } catch {
    throw new StageProfileError("Local MCP URL is invalid.");
  }
  if (
    endpoint.protocol !== "http:" ||
    !["localhost", "127.0.0.1", "[::1]"].includes(endpoint.hostname) ||
    endpoint.pathname !== "/mcp" ||
    endpoint.username !== "" ||
    endpoint.password !== "" ||
    endpoint.search !== "" ||
    endpoint.hash !== ""
  ) {
    throw new StageProfileError("Local mode permits only a loopback HTTP /mcp endpoint.");
  }
  return { name, endpoint, authentication: "none" };
}
