export type HttpResponseReader<T> = (response: Response) => Promise<T>;

export type HttpRequest = <T>(
  path: string,
  init?: RequestInit,
  readResponse?: HttpResponseReader<T>,
) => Promise<T>;

const MAX_ERROR_BODY_BYTES = 16 * 1024;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly correlationId: string | null;

  constructor(status: number, code: string, correlationId: string | null) {
    super("The request could not be completed.");
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
  }
}

export function createHttpRequest(fetcher: typeof fetch = globalThis.fetch): HttpRequest {
  return async function request<T>(
    path: string,
    init?: RequestInit,
    readResponse?: HttpResponseReader<T>,
  ): Promise<T> {
    const response = await fetcher(path, {
      ...init,
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        accept: "application/json",
        ...init?.headers,
      },
    });

    await throwIfHttpError(response);
    if (readResponse) return await readResponse(response);
    return (await response.json()) as T;
  };
}

export async function throwIfHttpError(response: Response): Promise<void> {
  if (response.ok) return;

  const code = await readErrorCode(response);
  const correlationId = boundedHeader(response.headers.get("x-correlation-id"));
  throw new ApiError(response.status, code, correlationId);
}

async function readErrorCode(response: Response): Promise<string> {
  if (!response.headers.get("content-type")?.includes("application/json")) {
    return "request_failed";
  }

  const contentLength = response.headers.get("content-length");
  if (contentLength && /^\d+$/.test(contentLength)
    && Number(contentLength) > MAX_ERROR_BODY_BYTES) {
    return "request_failed";
  }

  const reader = response.body?.getReader();
  if (!reader) return "request_failed";

  try {
    const chunks: Uint8Array[] = [];
    let byteLength = 0;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      byteLength += chunk.value.byteLength;
      if (byteLength > MAX_ERROR_BODY_BYTES) {
        await reader.cancel();
        return "request_failed";
      }
      chunks.push(chunk.value);
    }

    const body = new Uint8Array(byteLength);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.byteLength;
    }
    const payload = JSON.parse(new TextDecoder().decode(body)) as {
      error?: { code?: unknown };
    };
    const code = payload.error?.code;
    return typeof code === "string" && /^[a-z][a-z0-9_-]{0,63}$/.test(code)
      ? code
      : "request_failed";
  } catch {
    return "request_failed";
  } finally {
    reader.releaseLock();
  }
}

function boundedHeader(value: string | null): string | null {
  return value && /^[a-zA-Z0-9_-]{1,128}$/.test(value) ? value : null;
}
