from __future__ import annotations

import pytest

from download_metadata_snapshot import DownloadError, _validate_protected_url


def test_download_helper_accepts_production_and_local_protected_urls() -> None:
    _validate_protected_url(
        "https://workbench.example/metadata-snapshots/123/"
        "7d7cc8ad-62b5-44ef-aeb0-c09c770ff233/download",
        scope="api://workbench/.default",
    )
    _validate_protected_url(
        "http://localhost:8000/metadata-snapshots/123/"
        "7d7cc8ad-62b5-44ef-aeb0-c09c770ff233/download",
        scope=None,
    )


@pytest.mark.parametrize(
    ("url", "scope"),
    [
        (
            "http://workbench.example/metadata-snapshots/123/id/download",
            None,
        ),
        (
            "https://workbench.example/metadata-snapshots/123/id/download?sig=secret",
            "api://workbench/.default",
        ),
        (
            "https://workbench.example/metadata-snapshots/123/id/download",
            None,
        ),
        (
            "http://localhost:8000/metadata-snapshots/123/id/download",
            "api://workbench/.default",
        ),
    ],
)
def test_download_helper_rejects_unsafe_url_and_scope_combinations(
    url: str,
    scope: str | None,
) -> None:
    with pytest.raises(DownloadError):
        _validate_protected_url(url, scope=scope)
