"""Opaque HMAC-bound pagination cursors."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError


@dataclass(frozen=True, slots=True)
class CursorCodec:
    signing_key: bytes

    def encode(self, *, collection: str, offset: int) -> str:
        body = json.dumps(
            {"collection": collection, "offset": offset, "version": 1},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        signature = hmac.new(self.signing_key, body, hashlib.sha256).digest()
        return f"{_url_encode(body)}.{_url_encode(signature)}"

    def decode(self, token: str | None, *, collection: str) -> int:
        if token is None:
            return 0
        if len(token) > 2048 or token.count(".") != 1:
            raise InvalidRequestError("The pagination cursor is invalid.")
        encoded_body, encoded_signature = token.split(".")
        try:
            body = _url_decode(encoded_body)
            signature = _url_decode(encoded_signature)
        except ValueError as exc:
            raise InvalidRequestError("The pagination cursor is invalid.") from exc
        expected = hmac.new(self.signing_key, body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidRequestError("The pagination cursor is invalid.")
        try:
            payload: object = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidRequestError("The pagination cursor is invalid.") from exc
        if not isinstance(payload, dict):
            raise InvalidRequestError("The pagination cursor is invalid.")
        cursor_payload = cast(dict[str, object], payload)
        if set(cursor_payload) != {"collection", "offset", "version"}:
            raise InvalidRequestError("The pagination cursor is invalid.")
        offset = cursor_payload.get("offset")
        if (
            cursor_payload.get("collection") != collection
            or cursor_payload.get("version") != 1
            or not isinstance(offset, int)
            or isinstance(offset, bool)
            or not 0 <= offset <= 10_000_000
        ):
            raise InvalidRequestError("The pagination cursor is invalid.")
        return offset


def _url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _url_decode(value: str) -> bytes:
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid base64") from exc
