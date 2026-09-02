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
        "dbml.js",
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


def test_workbench_exposes_refresh_and_optional_validation_without_review_buttons() -> None:
    html = (WORKBENCH / "index.html").read_text()
    app = (WORKBENCH / "app.js").read_text()

    assert 'id="refresh-button"' in app
    assert 'id="validate-button"' in app
    assert 'id="dbml-button"' in app
    assert 'id="override-button"' not in html + app
    assert 'id="accept-button"' not in html + app
    assert '["metadata", "Metadata"]' in app
    assert '["model", "Model"]' in app
    assert "Snapshot stays unchanged." in app
    assert "Save changes" in html
    assert "shared local validation reports" in app


def test_workbench_validation_is_schema_driven() -> None:
    source = (WORKBENCH / "validation" / "model.js").read_text()
    common = (WORKBENCH / "validation" / "common.js").read_text()
    powershell = (SKILL_ROOT / "scripts" / "gds-local.ps1").read_text()

    assert '"x-gds-record-type"' in source
    assert '"x-gds-references"' in source
    assert "broken_reference" in source
    assert "partial_null_reference" in source
    assert '"x-gds-change-set-eligible"' in common
    assert '"x-gds-unique-constraints"' in common
    assert "Locked records cannot be changed locally." in common
    assert "Add-DeclaredReferenceIssues" in powershell


def test_workbench_exposes_the_record_ledger_and_dedicated_document_details() -> None:
    html = (WORKBENCH / "index.html").read_text()
    app = (WORKBENCH / "app.js").read_text()

    assert 'class="data-table"' in app
    assert 'data-source="snapshot"' in app
    assert 'data-source="changeset"' in app
    assert 'data-action="back-to-ledger"' in app
    assert 'mapping_transformation_document' in app
    assert 'generated_code_content' in app
    assert 'validation_query_sql' in app
    assert 'id="row-editor-dialog"' in html
    assert 'id="pending-editor"' not in html + app


def test_workbench_results_use_visible_spreadsheet_grid_lines() -> None:
    styles = (WORKBENCH / "styles.css").read_text()

    assert "border-right: 1px solid var(--grid-line);" in styles
    assert "border-bottom: 1px solid var(--grid-line);" in styles
    assert "border: 1px solid var(--line-strong);" in styles
    assert "padding: 7px 9px;" in styles
    assert ".data-table th," in styles and "font-size: 9px;" in styles
    assert ".data-table td," in styles and "font-size: 10px;" in styles


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
    app = (WORKBENCH / "app.js").read_text()
    styles = (WORKBENCH / "styles.css").read_text()

    assert 'role="tablist"' in app
    assert 'aria-selected="${active === value}"' in app
    assert 'id="status-message" role="status" aria-live="polite"' in app
    assert 'aria-labelledby="override-title"' not in html
    assert "@media (max-width: 820px)" in styles
    assert ".record-layout," in styles and "grid-template-columns: 170px" in styles


def test_workbench_uses_the_approved_visual_foundations() -> None:
    html = (WORKBENCH / "index.html").read_text()
    styles = (WORKBENCH / "styles.css").read_text()

    assert '<meta name="color-scheme" content="light">' in html
    for token in (
        "--ink: #17202a;",
        "--paper: #f2f4f6;",
        "--blue: #315fcf;",
        "--orange: #b75c27;",
        'font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;',
    ):
        assert token in styles
    assert "backdrop-filter: blur(22px) saturate(150%);" in styles
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

    assert ".record-layout { grid-template-columns: 220px minmax(0, 1fr); }" in styles
    assert ".validation-layout { grid-template-columns: 245px minmax(0, 1fr); }" in styles
    assert ".dataset-rail,\n.report-rail" in styles
    assert "border-top: 2px solid var(--ink);" in styles
    assert ".statusbar" in styles and "background: var(--ink);" in styles
    assert ".validation-rail" not in styles


def test_workbench_keeps_fluid_layout_and_restrained_panel_motion() -> None:
    styles = (WORKBENCH / "styles.css").read_text()

    assert "html { min-width: 1000px" not in styles
    assert "@media (max-width: 1080px)" in styles
    assert "@media (max-width: 820px)" in styles
    assert "@keyframes page-enter" in styles
    assert "animation: page-enter 170ms var(--ease-fluid) both;" in styles


def test_workbench_keeps_utility_controls_dense_and_fallback_boundaries_clear() -> None:
    styles = (WORKBENCH / "styles.css").read_text()

    assert ".field-label { color: var(--muted); font-size: 9px;" in styles
    assert ".dataset-button > span:last-child { color: var(--faint); font-size: 8px;" in styles
    assert (
        ".topbar,\n  .area-tabs { background: #fff; backdrop-filter: none; }" in styles
    )
    assert ".row-editor-field" in styles
    assert ".detail-document pre" in styles


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
