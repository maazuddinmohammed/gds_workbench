"""Download a protected Metadata Snapshot without exposing its SAS URL."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import aiohttp
from azure.identity.aio import DefaultAzureCredential


class DownloadError(Exception):
    """A bounded local-helper failure that contains no token or redirect URL."""


async def download_snapshot(
    protected_url: str,
    output: Path,
    *,
    scope: str | None,
    max_bytes: int,
) -> Path:
    """Authorize once against App Service, then download from Blob without that token."""
    _validate_protected_url(protected_url, scope=scope)
    if max_bytes <= 0:
        raise DownloadError("max-bytes must be positive")
    output = await asyncio.to_thread(_prepare_output, output)

    credential: DefaultAzureCredential | None = None
    headers: dict[str, str] = {}
    try:
        if scope is not None:
            credential = DefaultAzureCredential()
            access_token = await credential.get_token(scope)
            headers["Authorization"] = f"Bearer {access_token.token}"

        timeout = aiohttp.ClientTimeout(total=600, connect=30)
        async with (
            aiohttp.ClientSession(timeout=timeout, headers=headers) as application,
            application.get(protected_url, allow_redirects=False) as response,
        ):
            if response.status != 302:
                raise DownloadError("protected snapshot request was not accepted")
            location = response.headers.get("Location")
            if location is None:
                raise DownloadError("protected snapshot redirect is missing")
            blob_url = urljoin(protected_url, location)
            _validate_blob_redirect(blob_url)

        created_output = False
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as blob_session,
                blob_session.get(blob_url, allow_redirects=False) as response,
            ):
                if response.status != 200:
                    raise DownloadError("snapshot download failed")
                declared_length = response.content_length
                if declared_length is not None and declared_length > max_bytes:
                    raise DownloadError("snapshot download exceeds max-bytes")
                downloaded = 0
                output_file = await asyncio.to_thread(output.open, "xb")
                created_output = True
                try:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        downloaded += len(chunk)
                        if downloaded > max_bytes:
                            raise DownloadError("snapshot download exceeds max-bytes")
                        await asyncio.to_thread(output_file.write, chunk)
                finally:
                    await asyncio.to_thread(output_file.close)
            return output
        except Exception:
            if created_output:
                await asyncio.to_thread(_remove_partial_output, output)
            raise
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise DownloadError("snapshot service is unavailable") from exc
    finally:
        if credential is not None:
            await credential.close()


def _validate_protected_url(protected_url: str, *, scope: str | None) -> None:
    if not 1 <= len(protected_url) <= 2048:
        raise DownloadError("protected URL is invalid")
    parsed = urlsplit(protected_url)
    is_local_http = parsed.scheme == "http" and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/metadata-snapshots/")
        or not parsed.path.endswith("/download")
        or (parsed.scheme == "http" and not is_local_http)
    ):
        raise DownloadError("protected URL is invalid")
    if parsed.scheme == "https" and (scope is None or not scope.strip()):
        raise DownloadError("scope is required for an HTTPS protected URL")
    if is_local_http and scope is not None:
        raise DownloadError("scope must be omitted for a local HTTP URL")


def _prepare_output(output: Path) -> Path:
    resolved = output.resolve()
    if resolved.exists():
        raise DownloadError("output already exists")
    if not resolved.parent.is_dir():
        raise DownloadError("output parent directory does not exist")
    return resolved


def _remove_partial_output(output: Path) -> None:
    if output.is_file() and not output.is_symlink():
        output.unlink()


def _validate_blob_redirect(blob_url: str) -> None:
    parsed = urlsplit(blob_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.query
        or parsed.fragment
    ):
        raise DownloadError("snapshot redirect is invalid")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="protected download_url returned by MCP")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--scope",
        help="App Service API scope, for example api://<application-id>/.default",
    )
    parser.add_argument("--max-bytes", type=int, default=268435456)
    arguments = parser.parse_args()
    try:
        output = asyncio.run(
            download_snapshot(
                arguments.url,
                arguments.output,
                scope=arguments.scope,
                max_bytes=arguments.max_bytes,
            )
        )
    except DownloadError as error:
        parser.exit(1, f"download failed: {error}\n")
    print(output)


if __name__ == "__main__":
    main()
