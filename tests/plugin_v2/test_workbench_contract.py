from __future__ import annotations

import json
import subprocess
from pathlib import Path

from gds_etl_workbench.tools.snapshots.metadata.archive import build_dataset_document
from gds_etl_workbench.tools.snapshots.metadata.contracts import (
    DATASETS as METADATA_DATASETS,
)
from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS as MODEL_DATASETS,
)
from gds_etl_workbench.tools.snapshots.model.contracts import (
    build_model_dataset_schema,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "gds"
WORKBENCH = SKILL_ROOT / "workbench"


def test_workbench_is_classic_modular_and_network_blocked() -> None:
    html = (WORKBENCH / "index.html").read_text()

    assert "connect-src 'none'" in html
    assert 'type="module"' not in html
    for script in (
        "unicode.js",
        "core.js",
        "workspace.js",
        "metadata.js",
        "model.js",
        "validation/common.js",
        "validation/metadata.js",
        "validation/model.js",
        "ui-state.js",
        "app.js",
    ):
        assert f'<script src="{script}"></script>' in html
        assert (WORKBENCH / script).is_file()

    source = "\n".join(path.read_text() for path in WORKBENCH.rglob("*.js"))
    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source
    assert "WebSocket" not in source
    assert "EventSource" not in source


def test_workbench_exposes_explicit_refresh_validate_and_override() -> None:
    html = (WORKBENCH / "index.html").read_text()

    assert 'id="refresh-button"' in html
    assert 'id="validate-button"' in html
    assert 'id="override-button"' in html
    assert 'id="all-groups"' in html
    assert 'data-area="metadata"' in html
    assert 'data-area="model"' in html
    assert "Save writes local JSON only." in html


def test_workbench_exposes_results_table_and_json_fallback() -> None:
    html = (WORKBENCH / "index.html").read_text()

    assert 'data-view="results"' in html
    assert 'data-view="json"' in html
    assert 'id="results-table"' in html
    assert 'aria-label="Normalized dataset results"' in html
    assert 'id="row-editor-dialog"' in html


def test_workbench_results_use_visible_spreadsheet_grid_lines() -> None:
    styles = (WORKBENCH / "styles.css").read_text()

    assert "border-right: 1px solid var(--grid-line);" in styles
    assert "border-bottom: 1px solid var(--grid-line);" in styles
    assert "border: 1px solid var(--grid-line-strong);" in styles


def test_add_row_form_covers_every_snapshot_dataset_schema(tmp_path: Path) -> None:
    datasets = [
        {
            "area": "metadata",
            "name": definition.name,
            "section": definition.section.value,
            "canonical_key": list(definition.canonical_key),
            "change_set_eligible": definition.change_set_eligible,
            "schema": build_dataset_document(definition).schema,
        }
        for definition in METADATA_DATASETS
    ]
    datasets.extend(
        {
            "area": "model",
            "name": definition.name,
            "section": definition.section,
            "canonical_key": list(definition.canonical_key),
            "change_set_eligible": definition.change_set_eligible,
            "schema": build_model_dataset_schema(definition),
        }
        for definition in MODEL_DATASETS
    )
    fixture = tmp_path / "workbench-dataset-schemas.json"
    fixture.write_text(json.dumps(datasets))
    result = subprocess.run(
        [
            "node",
            str(REPOSITORY_ROOT / "tests/plugin_v2/workbench_all_forms.mjs"),
            str(fixture),
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_workbench_labels_dynamic_state_and_supports_narrow_screens() -> None:
    html = (WORKBENCH / "index.html").read_text()
    styles = (WORKBENCH / "styles.css").read_text()

    assert 'role="tablist"' in html
    assert 'aria-selected="true"' in html
    assert 'aria-label="Local Change Set JSON draft"' in html
    assert 'id="status-message" role="status" aria-live="polite"' in html
    assert 'aria-labelledby="override-title"' in html
    assert "@media (max-width: 720px)" in styles
    assert ".validation-rail { position: static;" in styles


def test_workbench_uses_the_approved_visual_foundations() -> None:
    html = (WORKBENCH / "index.html").read_text()
    styles = (WORKBENCH / "styles.css").read_text()

    assert '<meta name="color-scheme" content="light">' in html
    for token in (
        "--ink: #17202a;",
        "--paper: #f2f4f6;",
        "--blue: #315fcf;",
        "--orange: #b75c27;",
        'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;',
    ):
        assert token in styles
    assert "backdrop-filter: blur(22px) saturate(155%);" in styles
    assert ".button-primary" in styles and "background: var(--orange);" in styles


def test_workbench_visual_feedback_respects_accessibility_preferences() -> None:
    styles = (WORKBENCH / "styles.css").read_text()

    assert "button:active:not(:disabled)" in styles
    assert "button:focus-visible" in styles
    assert "textarea:focus-visible" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert "@media (prefers-reduced-transparency: reduce)" in styles
    assert "@media (prefers-contrast: more)" in styles


def test_workbench_shell_uses_a_calm_ledger_hierarchy() -> None:
    styles = (WORKBENCH / "styles.css").read_text()

    assert "grid-template-columns: 206px minmax(480px, 1fr) 300px;" in styles
    assert (
        ".dataset-rail,\n.validation-rail { min-height: 0; background: #fafbfc; }"
        in styles
    )
    assert "border-top: 2px solid var(--ink);" in styles
    assert ".statusbar" in styles and "background: var(--ink);" in styles
    assert "box-shadow: none;" in styles


def test_workbench_keeps_fluid_layout_and_restrained_panel_motion() -> None:
    styles = (WORKBENCH / "styles.css").read_text()

    assert "html { min-width: 1000px" not in styles
    assert "@media (max-width: 1050px)" in styles
    assert "@media (max-width: 720px)" in styles
    assert "@keyframes panel-enter" in styles
    assert "animation: panel-enter 180ms cubic-bezier(.22, 1, .36, 1) both;" in styles


def test_workbench_keeps_utility_controls_dense_and_fallback_boundaries_clear() -> None:
    styles = (WORKBENCH / "styles.css").read_text()

    assert (
        ".field-label { display: block; margin-bottom: 7px; font-size: 9px;" in styles
    )
    assert (
        ".dataset-button span:last-child { color: var(--faint); font-size: 8px;"
        in styles
    )
    assert (
        ".topbar,\n  .area-tabs { background: #fff; backdrop-filter: none; }" in styles
    )
    assert ".icon-button,\n  .segmented button,\n  .editor-grid" in styles


def test_shell_launcher_is_static_and_syntax_valid() -> None:
    launcher = SKILL_ROOT / "scripts" / "open-workbench.sh"
    result = subprocess.run(
        ["bash", "-n", str(launcher)],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    source = launcher.read_text()
    assert "http.server" not in source
    assert "npm" not in source
    assert "index.html" in source
    assert 'open -a "Google Chrome"' in source
    assert 'open -a "Microsoft Edge"' in source


def test_powershell_launcher_has_no_server_or_runtime_dependency() -> None:
    source = (SKILL_ROOT / "scripts" / "open-workbench.ps1").read_text()

    assert "Start-Process" in source
    assert "index.html" in source
    assert "python" not in source.lower()
    assert "node" not in source.lower()
    assert "npm" not in source.lower()
    assert "msedge.exe" in source
    assert "chrome.exe" in source
    assert "$indexUri = [Uri]$indexItem.FullName" in source
    assert "-ArgumentList @($indexUri.AbsoluteUri)" in source
