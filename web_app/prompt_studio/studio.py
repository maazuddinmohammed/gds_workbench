"""Prompt Studio: edit the default workflow prompts by numbered section, test changes with
agents, and build the seed that installs them. See README.md.

Run from the repository root with the backend environment:
    web_app/backend/.venv/bin/python web_app/prompt_studio/studio.py <command>
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import random
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STUDIO = Path(__file__).resolve().parent
ROOT = STUDIO.parents[1]
SEED = ROOT / "database" / "seed" / "05_global_prompt_defaults.template.sql"
VARIABLE_SEED = ROOT / "database" / "seed" / "04_application_reference.sql"
PROMPTS = STUDIO / "prompts"
FIXTURES = STUDIO / "fixtures"
EVALS = STUDIO / "evals"
OUT = STUDIO / "out"
IMPORTED = PROMPTS / "_imported.json"

# Rendering, input contracts and tools come from the backend, so tests see what a Run sends.
sys.path[:0] = [str(ROOT / "web_app" / "backend"), str(ROOT / "mcp_server")]

from gds_workbench_api.features.workflows.authoring.agent_execution import (  # noqa: E402
    AGENT_OUTPUT_CONTRACT_INSTRUCTION,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (  # noqa: E402
    get_prompt_input_contract,
)
from gds_workbench_api.features.workflows.authoring.tool_configuration import (  # noqa: E402
    registered_tool_definitions,
)
from gds_workbench_api.prompt_rendering import (  # noqa: E402
    PromptComponentTemplates,
    PromptVariableDefinition,
    render_prompt,
)
from jsonschema import Draft202012Validator  # noqa: E402

PAYLOAD_MARK = "$workflow_defaults$"
SYSTEM_MARK = "<!-- ===== SYSTEM PROMPT ===== -->\n"
INSTRUCTION_MARK = "\n<!-- ===== INSTRUCTION PROMPT ===== -->\n"
END_MARK = "\n<!-- ===== END ===== -->\n"
TOOLS_LINE = re.compile(r"^<!-- agent_tool_names: (.*) -->$", re.MULTILINE)
HEADING = re.compile(r"^(#{2,3}) (?:\[[SI]\d+(?:\.\d+)?\] )?(.*)$")
NUMBER = re.compile(r"^(#{2,3}) \[[SI]\d+(?:\.\d+)?\] ")
SECTION = re.compile(r"^## \[([SI]\d+)\] (.*)$")
JINJA = re.compile(r"{[{%](.*?)[}%]}", re.DOTALL)
SQL_VALUE = re.compile(r"\s*(?:'((?:[^']|'')*)'(::jsonb)?|(NULL)|(-?\d+))\s*(?:,|$)")
TESTABLE_MODE = "one_shot"


def stage_id(item: dict[str, Any]) -> str:
    """`workflow.mode.stage`, with `common` for stages that have no execution mode."""
    mode = item["workflow_execution_mode"] or "common"
    return f"{item['project_workflow']}.{mode}.{item['workflow_stage_code']}"


def read_seed(path: Path = SEED) -> tuple[str, list[dict[str, Any]], str]:
    """Seed 05 as the SQL before its JSON payload, the prompt items, and the SQL after."""
    parts = path.read_text(encoding="utf-8").split(PAYLOAD_MARK)
    if len(parts) != 3:
        raise SystemExit(f"{path.name}: expected one {PAYLOAD_MARK} JSON payload.")
    head, payload, tail = parts
    items = json.loads(payload)
    if "\n" + json.dumps(items, indent=2, ensure_ascii=False) + "\n" != payload:
        raise SystemExit(f"{path.name}: the JSON payload is not in the expected format.")
    return head, items, tail


def seed_text(head: str, items: list[dict[str, Any]], tail: str) -> str:
    payload = "\n" + json.dumps(items, indent=2, ensure_ascii=False) + "\n"
    return head + PAYLOAD_MARK + payload + PAYLOAD_MARK + tail


def number_sections(text: str, letter: str) -> str:
    """Number `##` headings S1, S2… (I1… for instructions) and `###` headings S1.1…

    Headings inside ``` fences are left alone. Existing numbers are replaced, so this also
    renumbers a file after sections were added, removed or moved.
    """
    lines = text.split("\n")
    major = minor = 0
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else HEADING.match(line)
        if match is None:
            continue
        hashes, title = match.groups()
        if len(hashes) == 2:
            major, minor = major + 1, 0
            label = f"{letter}{major}"
        else:
            minor += 1
            label = f"{letter}{major}.{minor}"
        lines[index] = f"{hashes} [{label}] {title}"
    return "\n".join(lines)


def strip_numbers(text: str) -> str:
    """Remove the studio's `[S3]` heading numbers; the model never sees them."""
    lines = text.split("\n")
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            lines[index] = NUMBER.sub(r"\1 ", line)
    return "\n".join(lines)


def stage_file_text(stage: str, system: str, instruction: str, tools: Any) -> str:
    for text in (system, instruction):
        if any(mark.strip() in text for mark in (SYSTEM_MARK, INSTRUCTION_MARK, END_MARK)):
            raise SystemExit(f"{stage}: the prompt contains a Prompt Studio marker line.")
        if any(NUMBER.match(line) for line in text.split("\n")):
            raise SystemExit(f"{stage}: a heading already starts with a [S1]-style number.")
    return (
        f"<!-- Prompt Studio stage {stage}. Edit the text between the marker lines. -->\n"
        f"<!-- agent_tool_names: {json.dumps(tools)} -->\n\n"
        + SYSTEM_MARK
        + number_sections(system, "S")
        + INSTRUCTION_MARK
        + number_sections(instruction, "I")
        + END_MARK
    )


def read_stage_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    header = text.split(SYSTEM_MARK, 1)[0]
    tools = TOOLS_LINE.search(header)
    if tools is None or SYSTEM_MARK not in text or not text.endswith(END_MARK):
        raise SystemExit(f"{path.name}: a marker line is missing or changed; see README.md.")
    body = text.split(SYSTEM_MARK, 1)[1].removesuffix(END_MARK)
    if INSTRUCTION_MARK not in body:
        raise SystemExit(f"{path.name}: the INSTRUCTION PROMPT marker line is missing.")
    system, instruction = body.split(INSTRUCTION_MARK, 1)
    return {
        "system": strip_numbers(system),
        "instruction": strip_numbers(instruction),
        "tools": json.loads(tools[1]),
        "file_text": text,
    }


def load_studio(prompts: Path = PROMPTS) -> dict[str, dict[str, Any]]:
    if not prompts.is_dir():
        raise SystemExit("No studio prompts yet. Run: studio.py import")
    return {path.stem: read_stage_file(path) for path in sorted(prompts.glob("*.md"))}


def merge_items(
    items: list[dict[str, Any]], studio: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Seed items with the studio prompts, keeping the seed's order and keys."""
    seed_ids = [stage_id(item) for item in items]
    missing = [stage for stage in seed_ids if stage not in studio]
    extra = sorted(set(studio) - set(seed_ids))
    if missing or extra:
        raise SystemExit(f"Stage files do not match the seed. Missing: {missing}. Extra: {extra}.")
    merged = []
    for item in items:
        stage = studio[stage_id(item)]
        updated = dict(item)
        updated["system_prompt"] = stage["system"]
        updated["instruction_prompt"] = stage["instruction"]
        if "agent_tool_names" in item or stage["tools"] is not None:
            updated["agent_tool_names"] = stage["tools"]
        merged.append(updated)
    return merged


def prompt_digest(system: str, instruction: str, tools: Any) -> str:
    text = json.dumps([system, instruction, tools], ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stage_states(
    items: list[dict[str, Any]], studio: dict[str, dict[str, Any]], imported: dict[str, str]
) -> dict[str, str]:
    """How each studio stage relates to the seed, using the digests recorded at import."""
    states: dict[str, str] = {}
    for item in items:
        stage = stage_id(item)
        if stage not in studio:
            states[stage] = "not imported"
            continue
        seed = prompt_digest(
            item["system_prompt"], item["instruction_prompt"], item.get("agent_tool_names")
        )
        mine = prompt_digest(
            studio[stage]["system"], studio[stage]["instruction"], studio[stage]["tools"]
        )
        base = imported.get(stage)
        if mine == seed:
            states[stage] = "in sync"
        elif base == seed:
            states[stage] = "edited in studio"
        elif base == mine:
            states[stage] = "seed changed"
        else:
            states[stage] = "both changed"
    return states


def read_variables(path: Path = VARIABLE_SEED) -> dict[str, list[dict[str, Any]]]:
    """Each stage's registered variables (seed 04) with their backend input contract."""
    text = path.read_text(encoding="utf-8")
    end = text.index(") AS seed(workflow, mode, stage_code, name, resolver,")
    start = text.rindex("FROM (VALUES\n", 0, end) + len("FROM (VALUES\n")
    variables: dict[str, list[dict[str, Any]]] = {}
    for number, line in enumerate(text[start:end].splitlines(), start=1):
        row = line.strip()
        if not row:
            continue
        if not row.startswith("(") or not row.endswith(("),", ")")):
            raise SystemExit(f"Seed 04 variable row {number} has an unexpected shape.")
        body = row[1 : row.rindex(")")]
        values: list[Any] = []
        position = 0
        while position < len(body):
            match = SQL_VALUE.match(body, position)
            if match is None:
                raise SystemExit(f"Seed 04 variable row {number} could not be read.")
            text_value, is_jsonb, is_null, integer = match.groups()
            if text_value is not None:
                text_value = text_value.replace("''", "'")
                values.append(json.loads(text_value) if is_jsonb else text_value)
            else:
                values.append(None if is_null else int(integer))
            position = match.end()
        workflow, mode, stage_code, name, resolver, data_type, description, example, order = values
        contract = get_prompt_input_contract(
            project_workflow=workflow,
            workflow_execution_mode=mode,
            stage_code=stage_code,
            resolver_key=resolver,
        )
        variables.setdefault(f"{workflow}.{mode or 'common'}.{stage_code}", []).append(
            {
                "name": name,
                "resolver_key": resolver,
                "data_type": data_type,
                "description": contract.description if contract else description,
                "example": contract.example if contract else example,
                "schema": contract.value_schema if contract else None,
                "delivery": contract.delivery if contract else None,
                "order": order,
            }
        )
    for stage_variables in variables.values():
        stage_variables.sort(key=lambda variable: variable["order"])
    return variables


def stage_tools(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Tools a tool-mode stage can call: its selected tools, or every registered one."""
    workflow, mode = item["project_workflow"], item["workflow_execution_mode"]
    if not (
        mode == "tool_assisted" or (mode is None and workflow in {"code_generation", "validation"})
    ):
        return []
    selected = item.get("agent_tool_names")
    return [
        {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
        for tool in registered_tool_definitions(workflow)
        if selected is None or tool.name in selected
    ]


def render(
    system: str, instruction: str, variables: list[dict[str, Any]], values: dict[str, Any]
) -> tuple[str, str]:
    """Render with the application's own renderer: compact JSON, sorted keys."""
    rendered = render_prompt(
        templates=PromptComponentTemplates(system=system, instruction=instruction),
        variables=tuple(
            PromptVariableDefinition(
                name=variable["name"],
                resolver_key=variable["resolver_key"],
                data_type=variable["data_type"],
                is_required=False,
            )
            for variable in variables
        ),
        resolver_values={
            variable["resolver_key"]: values.get(variable["name"]) for variable in variables
        },
    )
    return rendered.system, rendered.instruction


def stage_problems(item: dict[str, Any], variables: list[dict[str, Any]]) -> list[str]:
    problems = []
    try:
        render(
            item["system_prompt"],
            item["instruction_prompt"],
            variables,
            {variable["name"]: variable["example"] for variable in variables},
        )
    except Exception as error:  # The renderer raises one safe message per failure.
        problems.append(f"Does not render: {getattr(error, 'message', error)}")
    return problems


def sections(numbered: str) -> list[dict[str, str]]:
    """Split a numbered prompt at its `##` headings; `###` stays inside its section."""
    found: list[dict[str, Any]] = []
    current: dict[str, Any] = {"label": "", "title": "(before the first heading)", "lines": []}
    fenced = False
    for line in numbered.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        match = None if fenced else SECTION.match(line)
        if match is not None:
            found.append(current)
            current = {"label": match[1], "title": match[2], "lines": []}
        current["lines"].append(line)
    found.append(current)
    return [
        {"label": part["label"], "title": part["title"], "text": "\n".join(part["lines"])}
        for part in found
        if part["label"] or "\n".join(part["lines"]).strip()
    ]


def compare_sections(current: str, seed: str, letter: str, names: set[str]) -> dict[str, Any]:
    """Sections of the studio prompt, each marked same / changed / new against the seed."""
    before: dict[tuple[str, int], dict[str, str]] = {}
    for part in sections(number_sections(seed, letter)):
        key = (part["title"].casefold(), sum(k[0] == part["title"].casefold() for k in before))
        before[key] = part
    shown: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    for part in sections(number_sections(current, letter)):
        title = part["title"].casefold()
        old = before.pop((title, seen[title]), None)
        seen[title] += 1
        text = strip_numbers(part["text"])
        variables = set()
        for block in JINJA.findall(text):
            variables.update(re.findall(r"[a-z_][a-z0-9_]*", block))
        entry: dict[str, Any] = {
            **part,
            "chars": len(text),
            "vars": sorted(variables & names),
            "state": "same",
            "diff": [],
        }
        if old is None:
            entry["state"] = "new"
        elif strip_numbers(old["text"]) != text:
            entry["state"] = "changed"
            entry["diff"] = list(
                difflib.unified_diff(
                    strip_numbers(old["text"]).split("\n"), text.split("\n"), lineterm="", n=2
                )
            )[2:]
        shown.append(entry)
    removed = [
        {"title": part["title"], "text": strip_numbers(part["text"])} for part in before.values()
    ]
    return {"sections": shown, "removed": removed, "chars": len(current)}


def known_output_schema(stage: str) -> dict[str, Any] | None:
    """The `required_output_schema` the backend sends for stages whose schema is fixed."""
    from gds_workbench_api.features.analysis import candidate

    if stage == "analysis.one_shot.per_table_authoring":
        return candidate._AnalysisTableCandidate.model_json_schema()  # noqa: SLF001
    if stage == "analysis.one_shot.relationship_inference":
        return candidate._AnalysisInferenceCandidate.model_json_schema()  # noqa: SLF001
    return None


def fixture_problems(fixture: dict[str, Any], variables: list[dict[str, Any]]) -> list[str]:
    problems = []
    names = {variable["name"] for variable in variables}
    for name in sorted(set(fixture.get("values", {})) - names):
        problems.append(f"values.{name}: not a variable of this stage")
    for variable in variables:
        value = fixture.get("values", {}).get(variable["name"])
        if variable["schema"] is None or value is None:
            continue
        for error in list(Draft202012Validator(variable["schema"]).iter_errors(value))[:3]:
            path = ".".join(str(part) for part in error.absolute_path)
            problems.append(f"values.{variable['name']}.{path}: {error.message[:160]}")
    if not fixture.get("output_schema"):
        problems.append("output_schema is empty: copy the stage validator's output_schema().")
    expect = fixture.get("expect", {})
    if not expect.get("key") or not (expect.get("expected") or expect.get("forbidden")):
        problems.append("expect needs key fields and expected or forbidden items.")
    return problems


def score_run(result: Any, fixture: dict[str, Any]) -> dict[str, Any]:
    """One agent's result: answer validity, expected/forbidden/other items, and its review."""
    score: dict[str, Any] = {
        "returned": isinstance(result, dict),
        "valid": False,
        "expected": 0,
        "forbidden": 0,
        "other": 0,
        "clarity": None,
        "confidence": None,
        "blockers": [],
        "confusing": [],
        "intent": "",
        "comment": "",
    }
    if not isinstance(result, dict):
        return score
    answer = result.get("answer")
    score["valid"] = isinstance(answer, dict) and Draft202012Validator(
        fixture["output_schema"]
    ).is_valid(answer)
    expect = fixture.get("expect", {})
    found: Any = answer
    for part in filter(None, expect.get("list", "").split(".")):
        found = found.get(part) if isinstance(found, dict) else None
    if score["valid"] and isinstance(found, list):
        fields = expect["key"]

        def key(item: Any) -> tuple[str, ...]:
            return tuple(str(item.get(field, "")).strip().casefold() for field in fields)

        expected = {key(item) for item in expect.get("expected", [])}
        forbidden = {key(item) for item in expect.get("forbidden", [])}
        returned = [key(item) for item in found if isinstance(item, dict)]
        score["expected"] = len(expected & set(returned))
        score["forbidden"] = sum(item in forbidden for item in returned)
        score["other"] = sum(item not in expected and item not in forbidden for item in returned)
    review = result.get("review") if isinstance(result.get("review"), dict) else {}
    for field in ("clarity", "confidence"):
        value = review.get(field)
        score[field] = value if isinstance(value, int) and 1 <= value <= 5 else None
    for field in ("blockers", "confusing"):
        notes = review.get(field) if isinstance(review.get(field), list) else []
        score[field] = [note for note in notes if isinstance(note, dict)]
    score["intent"] = str(review.get("intent", ""))[:400]
    score["comment"] = str(review.get("comment", ""))[:600]
    return score


def summarize(scores: list[dict[str, Any]], expected_count: int) -> dict[str, Any]:
    valid = [score for score in scores if score["valid"]]

    def average(field: str) -> float | None:
        values = [score[field] for score in scores if score[field] is not None]
        return sum(values) / len(values) if values else None

    possible = expected_count * len(valid)
    return {
        "runs": len(scores),
        "returned": sum(score["returned"] for score in scores),
        "valid": len(valid),
        "found": sum(score["expected"] for score in valid),
        "possible": possible,
        "recall": sum(score["expected"] for score in valid) / possible if possible else None,
        "forbidden": sum(score["forbidden"] for score in valid),
        "other": sum(score["other"] for score in valid) / len(valid) if valid else None,
        "clarity": average("clarity"),
        "confidence": average("confidence"),
        "blockers": Counter(
            str(note.get("section", "?")) for score in scores for note in score["blockers"]
        ),
        "confusing": Counter(
            str(note.get("section", "?")) for score in scores for note in score["confusing"]
        ),
    }


def verdict(base: dict[str, Any], candidate: dict[str, Any] | None) -> str:
    """A suggestion only: recall up 10+ points without more forbidden items or invalid answers."""
    if candidate is None:
        return "baseline only (no studio change for this stage)"
    if base["recall"] is None or candidate["recall"] is None:
        return "not enough valid answers to compare"
    worse = (
        candidate["recall"] < base["recall"] - 0.1
        or candidate["forbidden"] / candidate["runs"] > base["forbidden"] / base["runs"]
        or candidate["valid"] / candidate["runs"] < base["valid"] / base["runs"]
    )
    if worse:
        return "worse"
    return "better" if candidate["recall"] >= base["recall"] + 0.1 else "same"


def cmd_status() -> None:
    _, items, _ = read_seed()
    studio = load_studio()
    imported = json.loads(IMPORTED.read_text(encoding="utf-8")) if IMPORTED.exists() else {}
    states = stage_states(items, studio, imported)
    for stage, state in states.items():
        print(f"{state:18} {stage}")
    counts = Counter(states.values())
    print("\n" + ", ".join(f"{count} {state}" for state, count in counts.items()))
    if counts.keys() - {"in sync", "edited in studio"}:
        print("Seed changes exist: run `import` (add --force to discard studio edits).")


def cmd_import(force: bool) -> None:
    _, items, _ = read_seed()
    studio = load_studio() if PROMPTS.is_dir() else {}
    imported = json.loads(IMPORTED.read_text(encoding="utf-8")) if IMPORTED.exists() else {}
    states = stage_states(items, studio, imported)
    edited = [
        stage for stage, state in states.items() if state in {"edited in studio", "both changed"}
    ]
    if edited and not force:
        raise SystemExit(
            "Import would overwrite studio edits in: "
            + ", ".join(edited)
            + ". Copy the built seed first, or run `import --force` to discard them."
        )
    PROMPTS.mkdir(exist_ok=True)
    digests = {}
    for item in items:
        stage = stage_id(item)
        path = PROMPTS / f"{stage}.md"
        tools = item.get("agent_tool_names")
        path.write_text(
            stage_file_text(stage, item["system_prompt"], item["instruction_prompt"], tools),
            encoding="utf-8",
        )
        back = read_stage_file(path)
        if (back["system"], back["instruction"]) != (
            item["system_prompt"],
            item["instruction_prompt"],
        ):
            raise SystemExit(f"{stage}: section numbers did not round-trip.")
        digests[stage] = prompt_digest(item["system_prompt"], item["instruction_prompt"], tools)
    IMPORTED.write_text(json.dumps(digests, indent=2) + "\n", encoding="utf-8")
    stale = sorted(set(studio) - set(digests))
    print(f"Imported {len(items)} stages from {SEED.relative_to(ROOT)} into prompts/.")
    if stale:
        print("Not in the seed any more (delete if unwanted): " + ", ".join(stale))


def cmd_build() -> None:
    head, items, tail = read_seed()
    studio = load_studio()
    renumbered = []
    for stage, data in studio.items():
        canonical = stage_file_text(stage, data["system"], data["instruction"], data["tools"])
        if canonical != data["file_text"]:
            (PROMPTS / f"{stage}.md").write_text(canonical, encoding="utf-8")
            renumbered.append(stage)
    merged = merge_items(items, studio)
    imported = json.loads(IMPORTED.read_text(encoding="utf-8")) if IMPORTED.exists() else {}
    states = stage_states(items, studio, imported)
    variables = read_variables()
    seed_by_id = {stage_id(item): item for item in items}
    built = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    stages = []
    for item in merged:
        stage = stage_id(item)
        stage_variables = variables.get(stage, [])
        names = {variable["name"] for variable in stage_variables}
        seed = seed_by_id[stage]
        fixtures = []
        for path in sorted((FIXTURES / stage).glob("*.json")):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            fixtures.append(
                {
                    "name": path.stem,
                    "description": fixture.get("description", ""),
                    "expected": len(fixture.get("expect", {}).get("expected", [])),
                    "forbidden": len(fixture.get("expect", {}).get("forbidden", [])),
                    "problems": fixture_problems(fixture, stage_variables),
                }
            )
        log = EVALS / f"{stage}.md"
        stages.append(
            {
                "id": stage,
                "workflow": item["project_workflow"],
                "mode": item["workflow_execution_mode"] or "common",
                "stage": item["workflow_stage_code"],
                "state": states[stage],
                "testable": item["workflow_execution_mode"] == TESTABLE_MODE,
                "problems": stage_problems(item, stage_variables),
                "system": compare_sections(
                    item["system_prompt"], seed["system_prompt"], "S", names
                ),
                "instruction": compare_sections(
                    item["instruction_prompt"], seed["instruction_prompt"], "I", names
                ),
                "variables": stage_variables,
                "tools": stage_tools(item),
                "fixtures": fixtures,
                "eval_log": log.read_text(encoding="utf-8") if log.exists() else "",
            }
        )
    OUT.mkdir(exist_ok=True)
    (OUT / SEED.name).write_text(seed_text(head, merged, tail), encoding="utf-8")
    counts = Counter(states.values())
    data = {
        "built": built,
        "seed": str(SEED.relative_to(ROOT)),
        "summary": ", ".join(f"{count} {state}" for state, count in counts.items()),
        "stages": stages,
    }
    page = (STUDIO / "page.html").read_text(encoding="utf-8")
    page = page.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (OUT / "studio.html").write_text(page, encoding="utf-8")
    problems = {stage["id"]: stage["problems"] for stage in stages if stage["problems"]}
    print(f"Built out/studio.html and out/{SEED.name} ({data['summary']}).")
    if renumbered:
        print("Renumbered sections in: " + ", ".join(renumbered))
    for stage, messages in problems.items():
        for message in messages:
            print(f"PROBLEM {stage}: {message}")
    if problems:
        raise SystemExit(1)


def cmd_fixture(stage: str, name: str) -> None:
    _, items, _ = read_seed()
    if stage not in {stage_id(item) for item in items}:
        raise SystemExit(f"Unknown stage {stage}. Run `status` to list stages.")
    path = FIXTURES / stage / f"{name}.json"
    if path.exists():
        raise SystemExit(f"{path.relative_to(ROOT)} already exists.")
    variables = read_variables().get(stage, [])
    fixture = {
        "description": "One sentence: what situation this made-up input tests.",
        "values": {variable["name"]: variable["example"] for variable in variables},
        "output_schema": known_output_schema(stage) or {},
        "expect": {"list": "", "key": [], "expected": [], "forbidden": []},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Created {path.relative_to(ROOT)} from the registered examples. Next: edit it (README).")


def cmd_pack(stage: str, fixture_name: str, runs: int, label: str) -> None:
    _, items, _ = read_seed()
    seed_item = next((item for item in items if stage_id(item) == stage), None)
    if seed_item is None:
        raise SystemExit(f"Unknown stage {stage}. Run `status` to list stages.")
    if seed_item["workflow_execution_mode"] != TESTABLE_MODE:
        raise SystemExit("Only one_shot stages can be tested: tool stages need live tool results.")
    fixture_path = FIXTURES / stage / f"{fixture_name}.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    variables = read_variables().get(stage, [])
    problems = fixture_problems(fixture, variables)
    if problems:
        raise SystemExit("Fix the fixture first:\n- " + "\n- ".join(problems))
    studio = load_studio()[stage]
    variants = {"baseline": (seed_item["system_prompt"], seed_item["instruction_prompt"])}
    if (studio["system"], studio["instruction"]) != variants["baseline"]:
        variants["candidate"] = (studio["system"], studio["instruction"])
    folder = EVALS / stage / label
    if folder.exists():
        raise SystemExit(f"{folder.relative_to(ROOT)} exists; choose another --label.")
    folder.mkdir(parents=True)
    plan = [variant for variant in variants for _ in range(runs)]
    random.Random(label).shuffle(plan)
    key = {}
    for number, variant in enumerate(plan, start=1):
        run = f"run-{number:02d}"
        system, instruction = variants[variant]
        rendered_system, rendered_instruction = render(
            number_sections(system, "S"),
            number_sections(instruction, "I"),
            variables,
            fixture["values"],
        )
        # The same two messages a Run sends: see agent_input_payload and _system_prompt.
        system_message = rendered_system + "\n\n" + AGENT_OUTPUT_CONTRACT_INSTRUCTION
        user_message = json.dumps(
            {
                "context": {"repair": None},
                "instruction": rendered_instruction,
                "required_output_schema": fixture["output_schema"],
                "response_format": "JSON object",
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        result = folder / f"{run}.result.json"
        (folder / f"{run}.md").write_text(
            packet_text(run, result, system_message, user_message), encoding="utf-8"
        )
        key[run] = variant
    (folder / "key.json").write_text(
        json.dumps({"stage": stage, "fixture": fixture_name, "key": key}, indent=2) + "\n",
        encoding="utf-8",
    )
    # Keep the exact prompts this test measured, so `restore` can bring a tested version back.
    tools = studio["tools"]
    for variant, (system, instruction) in variants.items():
        (folder / f"prompt-{variant}.md").write_text(
            stage_file_text(stage, system, instruction, tools), encoding="utf-8"
        )
    print(f"Wrote {len(plan)} packets to {folder.relative_to(ROOT)} ({', '.join(variants)}).")
    if "candidate" not in variants:
        print("No studio change for this stage, so every packet is the baseline.")
    print("\nRun each packet in its own fresh agent, with only this message:")
    for run in key:
        print(f"  Read {folder / (run + '.md')} and follow it exactly.")
    print(f"\nThen: studio.py score {stage} {label}")


def replace_stage_file(stage: str, text: str) -> None:
    """Write a stage file, keeping the replaced version as <stage>.md.previous."""
    path = PROMPTS / f"{stage}.md"
    if path.exists():
        path.with_name(path.name + ".previous").write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    path.write_text(text, encoding="utf-8")


def cmd_revert(stage: str) -> None:
    """Put one stage back to the seed's prompt."""
    _, items, _ = read_seed()
    item = next((item for item in items if stage_id(item) == stage), None)
    if item is None:
        raise SystemExit(f"Unknown stage {stage}. Run `status` to list stages.")
    tools = item.get("agent_tool_names")
    replace_stage_file(
        stage, stage_file_text(stage, item["system_prompt"], item["instruction_prompt"], tools)
    )
    imported = json.loads(IMPORTED.read_text(encoding="utf-8")) if IMPORTED.exists() else {}
    imported[stage] = prompt_digest(item["system_prompt"], item["instruction_prompt"], tools)
    IMPORTED.write_text(json.dumps(imported, indent=2) + "\n", encoding="utf-8")
    print(f"Reverted {stage} to the seed (previous file kept as {stage}.md.previous).")


def cmd_restore(stage: str, label: str) -> None:
    """Put back the candidate prompt that test `label` measured."""
    saved = EVALS / stage / label / "prompt-candidate.md"
    if not saved.exists():
        raise SystemExit(f"Test {label} has no candidate prompt: it measured the baseline only.")
    read_stage_file(saved)
    replace_stage_file(stage, saved.read_text(encoding="utf-8"))
    print(f"Restored {stage} to the version tested in {label} (previous file kept as .previous).")


def cmd_score(stage: str, label: str) -> None:
    folder = EVALS / stage / label
    meta = json.loads((folder / "key.json").read_text(encoding="utf-8"))
    fixture = json.loads((FIXTURES / stage / f"{meta['fixture']}.json").read_text(encoding="utf-8"))
    scores: dict[str, list[dict[str, Any]]] = {}
    notes: list[str] = []
    for run, variant in sorted(meta["key"].items()):
        path = folder / f"{run}.result.json"
        try:
            result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        except json.JSONDecodeError:
            result = None
        score = score_run(result, fixture)
        scores.setdefault(variant, []).append(score)
        for field in ("blockers", "confusing"):
            for note in score[field]:
                notes.append(
                    f"- {variant} {run} {field[:-1] if field == 'blockers' else field} "
                    f"[{note.get('section', '?')}]: {str(note.get('issue', ''))[:600]}"
                )
        if score["comment"]:
            notes.append(f"- {variant} {run} comment: {score['comment']}")
    expected_count = len(fixture.get("expect", {}).get("expected", []))
    summaries = {variant: summarize(runs, expected_count) for variant, runs in scores.items()}
    columns = [variant for variant in ("baseline", "candidate") if variant in summaries]

    def cell(summary: dict[str, Any], field: str) -> str:
        if field == "returned":
            return f"{summary['returned']}/{summary['runs']}"
        if field == "valid":
            return f"{summary['valid']}/{summary['runs']}"
        if field == "found":
            recall = summary["recall"]
            share = "–" if recall is None else f"{recall:.0%}"
            return f"{summary['found']}/{summary['possible']} ({share})"
        if field in {"blockers", "confusing"}:
            counts = summary[field]
            return (
                ", ".join(f"{section} ×{count}" for section, count in counts.most_common()) or "–"
            )
        value = summary[field]
        return (
            "–" if value is None else (f"{value:.1f}" if isinstance(value, float) else str(value))
        )

    rows = [
        ("Results returned", "returned"),
        ("Valid answers (schema)", "valid"),
        ("Expected items found", "found"),
        ("Forbidden items returned", "forbidden"),
        ("Other items per valid answer", "other"),
        ("Clarity (1–5)", "clarity"),
        ("Confidence (1–5)", "confidence"),
        ("Blockers cited", "blockers"),
        ("Confusing cited", "confusing"),
    ]
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        f"## {today} · `{label}` · fixture `{meta['fixture']}` · {len(meta['key'])} runs",
        "",
        "| Measure | " + " | ".join(columns) + " |",
        "|---|" + "---|" * len(columns),
    ]
    lines += [
        f"| {title} | " + " | ".join(cell(summaries[column], field) for column in columns) + " |"
        for title, field in rows
    ]
    suggestion = verdict(summaries["baseline"], summaries.get("candidate"))
    lines += ["", f"Suggested verdict: **{suggestion}**", ""]
    if notes:
        lines += ["Review notes:", *notes, ""]
    report = "\n".join(lines)
    print(report)
    EVALS.mkdir(exist_ok=True)
    log = EVALS / f"{stage}.md"
    previous = log.read_text(encoding="utf-8") if log.exists() else f"# Test log: {stage}\n\n"
    log.write_text(previous + report + "\n", encoding="utf-8")
    print(f"Appended to {log.relative_to(ROOT)}.")


def packet_text(run: str, result: Path, system_message: str, user_message: str) -> str:
    return f"""# Prompt Studio test {run}

You are helping test an AI prompt. Use only this file: do not open other files or look at
any repository.

## Part 1: answer as the model

The SYSTEM MESSAGE and USER MESSAGE below are exactly what a model receives in this
application. Read them as that model would and produce the one JSON object it should return.
Follow the messages as written; do not improve on them.

## Part 2: review the prompt

Answer honestly about the messages you just used. Cite sections by their number, such as S7
or I1 (the numbers in square brackets in the headings).

- intent: one or two sentences: what do the messages ask the model to produce?
- clarity: 1 to 5 (5 = completely clear what to do with this input)
- confidence: 1 to 5 (5 = sure your answer is what the messages want)
- blockers: rules that made you leave out something you believed was right,
  as [{{"section": "S7", "issue": "..."}}]
- confusing: unclear or conflicting instructions, as [{{"section": "S3", "issue": "..."}}]
- comment: anything else, at most three sentences

## Result

Write exactly one JSON file to {result} with this shape and nothing else:

{{"answer": <the JSON object from Part 1>, "review": {{"intent": "...", "clarity": 4,
"confidence": 3, "blockers": [], "confusing": [], "comment": "..."}}}}

Then reply with one line: done.

## SYSTEM MESSAGE

=====BEGIN SYSTEM MESSAGE=====
{system_message}
=====END SYSTEM MESSAGE=====

## USER MESSAGE

=====BEGIN USER MESSAGE=====
{user_message}
=====END USER MESSAGE=====
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prompt Studio. See web_app/prompt_studio/README.md."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Compare the studio prompts with the seed.")
    import_parser = commands.add_parser("import", help="Copy the seed prompts into prompts/.")
    import_parser.add_argument("--force", action="store_true", help="Discard studio edits.")
    commands.add_parser("build", help="Renumber, check, and write out/studio.html and the seed.")
    fixture_parser = commands.add_parser("fixture", help="Create a starter test input.")
    fixture_parser.add_argument("stage")
    fixture_parser.add_argument("name")
    pack_parser = commands.add_parser("pack", help="Write test packets for agents.")
    pack_parser.add_argument("stage")
    pack_parser.add_argument("fixture")
    pack_parser.add_argument("--runs", type=int, default=3, help="Runs per variant (default 3).")
    pack_parser.add_argument("--label", default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    revert_parser = commands.add_parser("revert", help="Put one stage back to the seed.")
    revert_parser.add_argument("stage")
    restore_parser = commands.add_parser("restore", help="Bring back a tested prompt version.")
    restore_parser.add_argument("stage")
    restore_parser.add_argument("label")
    score_parser = commands.add_parser("score", help="Score the returned test results.")
    score_parser.add_argument("stage")
    score_parser.add_argument("label")
    args = parser.parse_args()
    if args.command == "status":
        cmd_status()
    elif args.command == "import":
        cmd_import(args.force)
    elif args.command == "build":
        cmd_build()
    elif args.command == "fixture":
        cmd_fixture(args.stage, args.name)
    elif args.command == "revert":
        cmd_revert(args.stage)
    elif args.command == "restore":
        cmd_restore(args.stage, args.label)
    elif args.command == "pack":
        cmd_pack(args.stage, args.fixture, args.runs, args.label)
    else:
        cmd_score(args.stage, args.label)


if __name__ == "__main__":
    main()
