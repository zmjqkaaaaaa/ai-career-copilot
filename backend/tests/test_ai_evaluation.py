import ast
from dataclasses import replace
import json

import pytest

from app.evaluations.cases import CASES
from app.evaluations.checks import CHECKS
from app.prompts.registry import PromptRegistry, ROOT, fingerprint
from app.services.ai_evaluation_service import compare, run


def test_registry_covers_actual_prompt_definitions():
    registry = PromptRegistry()
    names = set()
    for file in ROOT.parent.rglob("*.py"):
        if file.parent == ROOT or file.name == "ai_evaluation_service.py":
            continue
        module = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Prompt"
                    and len(node.args) >= 2 and all(isinstance(value, ast.Constant) for value in node.args[:2])):
                names.add((node.args[0].value, node.args[1].value))
    assert names == registry.by_key.keys()
    assert len({(row["prompt_name"], row["version"]) for row in registry.inventory()}) == len(names)


def test_registry_detects_unversioned_edit_and_can_select_archived_revision(tmp_path):
    original = PromptRegistry()
    current = original.get("resume_extraction")
    definitions = list(original.by_key.values())
    changed = replace(current, prompt=replace(current.prompt, instruction="Unversioned edit"))
    with pytest.raises(ValueError, match="without a registry version update"):
        PromptRegistry([changed if row == current else row for row in definitions])

    archived = replace(current, prompt=replace(current.prompt, version="fixture-archive-v0"))
    metadata = original.metadata
    metadata["versions"].append({"prompt_name": archived.prompt.name, "version": archived.prompt.version,
                                 "created_at": None, "registered_at": "2026-11-21", "changelog": "Test fixture",
                                 "sha256": fingerprint(archived.manifest())})
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    local_registry = PromptRegistry([*definitions, archived], lock_path=path)
    assert local_registry.get(archived.prompt.name, archived.prompt.version) == archived
    assert local_registry.get(archived.prompt.name) == current
    assert len(local_registry.history(archived.prompt.name)) == 2
    with pytest.raises(ValueError, match="expected array field blocks"):
        current.validate_payload({"blocks": "Wrong kind"})


def test_twelve_quality_controls_and_reference_labels():
    registry = PromptRegistry()
    assert set(CHECKS) == {case.category for case in CASES}
    offline = run(CASES, registry)
    summary = offline["summary"]
    assert summary["passed"] == summary["cases"] == 12
    assert summary["structured_pass"] == summary["negative_controls_detected"] == summary["malformed_controls_rejected"] == 12


def test_compare_refuses_different_dataset_and_keeps_gate_deltas():
    base = run(CASES, PromptRegistry())
    candidate = json.loads(json.dumps(base))
    test_case = candidate["cases"][0]
    test_case["checks"]["all_expected_fields_recovered"] = False
    test_case["status"] = "failed"
    changes = compare(base, candidate)["changes"]
    assert changes[0]["checks_changed"]["all_expected_fields_recovered"] == {"before": True, "after": False}
    with pytest.raises(ValueError, match="dataset_sha256"):
        compare(base, {**candidate, "dataset_sha256": "invalid version"})
