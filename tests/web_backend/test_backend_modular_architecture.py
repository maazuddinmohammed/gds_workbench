"""Static deletion and dependency-direction checks for the backend modules."""

import ast
import importlib.util
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_ROOT = _REPOSITORY_ROOT / "web_app" / "backend" / "gds_workbench_api"
_PACKAGE_NAME = "gds_workbench_api"

_REMOVED_MODULES = (
    Path("assertions.py"),
    Path("conceptual.py"),
    Path("dimensional.py"),
    Path("locks.py"),
    Path("logical.py"),
    Path("mapping_review.py"),
    Path("metadata.py"),
    Path("metadata_repository.py"),
    Path("metadata_workbook.py"),
    Path("model_commands.py"),
    Path("models.py"),
    Path("profiling_analysis.py"),
    Path("profiling_execution.py"),
    Path("profiling_workflow.py"),
    Path("prompts.py"),
    Path("scope.py"),
    Path("session.py"),
    Path("tenants.py"),
    Path("workflow_commands.py"),
    Path("workflow_overview.py"),
    Path("workflow_runs.py"),
    Path("features/mapping/preparation.py"),
    Path("integrations/agents/runtime.py"),
)
_WORKFLOW_COMPOSITION_MODULE = "gds_workbench_api.features.workflows.execution.assembly"
_AGENT_PORT_MODULE = "gds_workbench_api.features.workflows.authoring.agent_execution"


def _module_identity(source: Path) -> tuple[str, bool]:
    relative = source.relative_to(_PACKAGE_ROOT).with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join((_PACKAGE_NAME, *parts)), is_package


def _resolve_imports(
    *,
    module_name: str,
    is_package: bool,
    tree: ast.Module,
) -> set[str]:
    package = module_name if is_package else module_name.rpartition(".")[0]
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue

        if node.level:
            relative_name = "." * node.level + (node.module or "")
            target = importlib.util.resolve_name(relative_name, package)
        else:
            target = node.module or ""

        if node.module is not None:
            targets.add(target)
        for alias in node.names:
            if alias.name != "*":
                targets.add(f"{target}.{alias.name}")
    return targets


def _find_cycle(graph: dict[str, set[str]]) -> tuple[str, ...] | None:
    states: dict[str, int] = {}
    stack: list[str] = []
    positions: dict[str, int] = {}

    def visit(module_name: str) -> tuple[str, ...] | None:
        states[module_name] = 1
        positions[module_name] = len(stack)
        stack.append(module_name)
        for dependency in sorted(graph[module_name]):
            state = states.get(dependency, 0)
            if state == 0:
                cycle = visit(dependency)
                if cycle is not None:
                    return cycle
            elif state == 1:
                return tuple(stack[positions[dependency] :] + [dependency])
        stack.pop()
        positions.pop(module_name)
        states[module_name] = 2
        return None

    for module_name in sorted(graph):
        if states.get(module_name, 0) == 0:
            cycle = visit(module_name)
            if cycle is not None:
                return cycle
    return None


def test_backend_modular_architecture_deletion_contract() -> None:
    """Protect only the feature moves and inward Agent port already established."""
    restored_modules = [
        str(relative_path)
        for relative_path in _REMOVED_MODULES
        if (_PACKAGE_ROOT / relative_path).exists()
    ]
    assert not restored_modules, (
        "Retired backend modules must stay deleted: " + ", ".join(restored_modules)
    )

    module_sources: dict[str, Path] = {}
    package_modules: set[str] = set()
    for source in sorted(_PACKAGE_ROOT.rglob("*.py")):
        module_name, is_package = _module_identity(source)
        module_sources[module_name] = source
        if is_package:
            package_modules.add(module_name)

    assert _AGENT_PORT_MODULE in module_sources

    imports_by_module: dict[str, set[str]] = {}
    for module_name, source in module_sources.items():
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        imports_by_module[module_name] = _resolve_imports(
            module_name=module_name,
            is_package=module_name in package_modules,
            tree=tree,
        )

    feature_provider_violations = sorted(
        (module_name, imported)
        for module_name, imports in imports_by_module.items()
        if module_name.startswith(f"{_PACKAGE_NAME}.features.")
        and module_name != _WORKFLOW_COMPOSITION_MODULE
        for imported in imports
        if imported == f"{_PACKAGE_NAME}.integrations"
        or imported.startswith(f"{_PACKAGE_NAME}.integrations.")
    )
    assert not feature_provider_violations, (
        "Feature modules may reach provider adapters only through Workflow runtime "
        f"composition: {feature_provider_violations}"
    )

    agent_port_imports = imports_by_module[_AGENT_PORT_MODULE]
    assert not {
        imported
        for imported in agent_port_imports
        if imported == f"{_PACKAGE_NAME}.integrations"
        or imported.startswith(f"{_PACKAGE_NAME}.integrations.")
    }, "The workflow-owned Agent port must not depend on outward integrations"

    agent_adapter_modules = {
        module_name
        for module_name in module_sources
        if module_name.startswith(f"{_PACKAGE_NAME}.integrations.agents")
    }
    agent_feature_import_violations = sorted(
        (module_name, imported)
        for module_name in agent_adapter_modules
        for imported in imports_by_module[module_name]
        if imported.startswith(f"{_PACKAGE_NAME}.features.")
        and imported != _AGENT_PORT_MODULE
        and not imported.startswith(f"{_AGENT_PORT_MODULE}.")
    )
    assert not agent_feature_import_violations, (
        "Agent provider adapters may depend only on their workflow-owned port: "
        f"{agent_feature_import_violations}"
    )
    assert any(
        _AGENT_PORT_MODULE in imports_by_module[module_name]
        for module_name in agent_adapter_modules
    ), "Agent provider adapters must continue implementing the workflow-owned port"

    known_modules = set(module_sources)
    import_graph = {
        module_name: {imported for imported in imports if imported in known_modules}
        for module_name, imports in imports_by_module.items()
    }
    cycle = _find_cycle(import_graph)
    assert cycle is None, "Backend import cycle detected: " + " -> ".join(cycle or ())
