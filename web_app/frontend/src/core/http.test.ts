import { describe, expect, it, vi } from "vitest";

import { ApiError, createHttpRequest } from "./http";

describe("private HTTP adapter", () => {
  it("applies the shared same-origin JSON request defaults", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ accepted: true }), {
        headers: { "content-type": "application/json" },
      }),
    );
    const request = createHttpRequest(fetcher);

    await expect(request<{ accepted: boolean }>("/api/v1/example", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ value: 1 }),
    })).resolves.toEqual({ accepted: true });

    expect(fetcher).toHaveBeenCalledWith("/api/v1/example", {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify({ value: 1 }),
    });
  });

  it("exposes only a bounded stable code and correlation ID from JSON errors", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({
        error: {
          code: "authorization_denied",
          message: "secret database diagnostics",
        },
      }), {
        status: 403,
        headers: {
          "content-type": "application/json",
          "x-correlation-id": "safe-correlation_123",
        },
      }),
    );

    await expect(createHttpRequest(fetcher)("/api/v1/example")).rejects.toEqual(
      expect.objectContaining<ApiError>({
        name: "ApiError",
        status: 403,
        code: "authorization_denied",
        correlationId: "safe-correlation_123",
        message: "The request could not be completed.",
      }),
    );
  });

  it("does not parse an oversized JSON error body", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({
        error: {
          code: "authorization_denied",
          message: "x".repeat(16_384),
        },
      }), {
        status: 403,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(createHttpRequest(fetcher)("/api/v1/example")).rejects.toEqual(
      expect.objectContaining<ApiError>({
        name: "ApiError",
        status: 403,
        code: "request_failed",
        correlationId: null,
        message: "The request could not be completed.",
      }),
    );
  });

  it("supports a typed success-response reader with the shared request defaults", async () => {
    const workbook = new Uint8Array([80, 75, 3, 4]);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(workbook, {
        headers: { "content-type": "application/octet-stream" },
      }),
    );

    const blob = await createHttpRequest(fetcher)<Blob>(
      "/api/v1/example.xlsx",
      {
        method: "POST",
        headers: { accept: "application/octet-stream" },
      },
      (response) => response.blob(),
    );

    expect(Array.from(new Uint8Array(await blob.arrayBuffer()))).toEqual([80, 75, 3, 4]);
    expect(fetcher).toHaveBeenCalledWith("/api/v1/example.xlsx", {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: { accept: "application/octet-stream" },
    });
  });
});
