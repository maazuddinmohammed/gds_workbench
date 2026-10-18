import { readFileSync } from "node:fs";
import { describe, expect, test, vi } from "vitest";

import {
  createStageMcpClient,
  safeToolErrorCode,
  STAGE_RUNNER_HEADER,
  STAGE_UPLOAD_TOOL,
  type ProtocolConnector,
} from "../src/mcp-client.js";
import type { ResolvedStageProfile } from "../src/profile.js";
import { ALLOWED_DATASETS, type StageRequest } from "../src/stage-contract.js";
import { verifyStageFingerprint } from "../src/stage-transport.js";

// Generated from the MCP server by tests/atlas/test_stage_contract.py; never edit by hand.
interface AreaContract {
  result_schema_version: string;
  fingerprint_order: "declared" | "sorted";
  datasets: string[];
  fingerprint_example: Record<string, unknown> & {
    draft_revision: number;
    datasets: Array<{ dataset: string; record_count: number }>;
  };
}
interface ServerContract {
  fingerprint_version: string;
  metadata: AreaContract & { fingerprint_example: { tenant_id: number; metadata_change_set_id: string } };
  project: AreaContract & { fingerprint_example: { project_id: number; project_change_set_id: string } };
  stage_runner: { header: string; client: string; upload_tools: string[] };
  tool_error_examples: Array<{ tool: string; code: string; text: string }>;
}

const LOCAL_PROFILE: ResolvedStageProfile = {
  name: "local",
  endpoint: new URL("http://127.0.0.1:8000/mcp"),
  authentication: "none",
};
const contract = JSON.parse(
  readFileSync(new URL("./fixtures/server-contract.json", import.meta.url), "utf8"),
) as ServerContract;

function requestFor(area: "metadata" | "project", changeSetId: string): StageRequest {
  return { area, target: { change_set_id: changeSetId } } as unknown as StageRequest;
}

function changesFor(example: AreaContract["fingerprint_example"]): Array<{ dataset: string; records: Record<string, unknown>[] }> {
  return example.datasets
    .filter((item) => item.record_count > 0)
    .map((item) => ({ dataset: item.dataset, records: Array.from({ length: item.record_count }, () => ({})) }));
}

describe("MCP server contract", () => {
  test("Stage Runner accepts exactly the server's Metadata datasets in fingerprint order", () => {
    expect(contract.metadata.fingerprint_order).toBe("declared");
    expect([...ALLOWED_DATASETS.metadata]).toEqual(contract.metadata.datasets);
  });

  test("Stage Runner accepts exactly the server's Project datasets", () => {
    expect(contract.project.fingerprint_order).toBe("sorted");
    expect([...ALLOWED_DATASETS.project].sort()).toEqual(contract.project.datasets);
  });

  test("server Metadata fingerprints verify", () => {
    const example = contract.metadata.fingerprint_example;
    expect(example.fingerprint_version).toBe(contract.fingerprint_version);
    expect(
      verifyStageFingerprint(
        requestFor("metadata", example.metadata_change_set_id),
        example.tenant_id,
        example.draft_revision,
        changesFor(example),
        example,
      ),
    ).toBe(example.fingerprint);
  });

  test("server Project fingerprints verify", () => {
    const example = contract.project.fingerprint_example;
    expect(example.fingerprint_version).toBe(contract.fingerprint_version);
    expect(
      verifyStageFingerprint(
        requestFor("project", example.project_change_set_id),
        example.project_id,
        example.draft_revision,
        changesFor(example),
        example,
      ),
    ).toBe(example.fingerprint);
  });

  test("Stage Runner sends the header the server requires for upload tools", () => {
    expect(STAGE_RUNNER_HEADER).toEqual({
      name: contract.stage_runner.header,
      value: contract.stage_runner.client,
    });
    expect(contract.stage_runner.upload_tools).toHaveLength(8);
    for (const tool of contract.stage_runner.upload_tools) expect(STAGE_UPLOAD_TOOL.test(tool)).toBe(true);
    for (const tool of ["get_project_change_set", "get_metadata_change_set_fingerprint", "apply_project_change_set",
      "validate_metadata_change_set", "create_project_change_set", "list_tenants"]) {
      expect(STAGE_UPLOAD_TOOL.test(tool)).toBe(false);
    }
  });

  test("real MCP SDK tool failures keep their governed error code", async () => {
    expect(contract.tool_error_examples.length).toBeGreaterThan(0);
    for (const example of contract.tool_error_examples) {
      expect(safeToolErrorCode([{ type: "text", text: example.text }])).toBe(example.code);
      const connector = vi.fn<ProtocolConnector>(async () => ({
        async callTool() {
          return { isError: true, content: [{ type: "text", text: example.text }] };
        },
        async close() {},
      }));
      const client = await createStageMcpClient(LOCAL_PROFILE, undefined, connector);
      await expect(client.callTool(example.tool, {})).rejects.toMatchObject({
        code: example.code,
        message: "GDS MCP rejected the operation.",
      });
      await client.close();
    }
  });
});
