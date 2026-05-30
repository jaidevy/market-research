from pathlib import Path

from market_research.agentic.skills import LoadedSkill, SkillLoader


def test_parse_inline_accepts_markdown_string() -> None:
    loader = SkillLoader(Path("./does-not-exist"))

    inline = loader.parse_inline("- always include invalidation levels", owner="Hermes")

    assert len(inline) == 1
    assert inline[0].name == "Hermes.skills"
    assert "invalidation" in inline[0].content


def test_parse_inline_accepts_json_and_markdown_items() -> None:
    loader = SkillLoader(Path("./does-not-exist"))

    payload = [
        {"name": "risk-guard", "markdown": "- enforce risk caps"},
        {"name": "memory-policy", "window": "trade-day", "max_items": 20},
    ]
    inline = loader.parse_inline(payload, owner="concierge")

    assert [item.name for item in inline] == ["risk-guard", "memory-policy"]
    assert inline[0].content == "- enforce risk caps"
    assert "max_items" in inline[1].content


def test_build_system_prompt_merges_file_and_inline_skills(tmp_path: Path) -> None:
    (tmp_path / "base.skill.md").write_text("- base rule", encoding="utf-8")
    loader = SkillLoader(tmp_path)

    merged, names, trace = loader.build_system_prompt(
        "base prompt",
        extra_skills=[LoadedSkill(name="inline.skill", content="- inline rule")],
    )

    assert "[SKILL: base.skill]" in merged
    assert "[SKILL: inline.skill]" in merged
    assert names == ["base.skill", "inline.skill"]
    assert len(trace) == 2


def test_frontmatter_metadata_is_parsed_and_applied(tmp_path: Path) -> None:
    (tmp_path / "routed.skill.md").write_text(
        """---
name: routed
category: policy
trigger: approval_required
priority: 25
---
- enforce approval conditions
""",
        encoding="utf-8",
    )
    loader = SkillLoader(tmp_path)

    merged, names, trace = loader.build_system_prompt(
        "base",
        runtime_context={"require_approval": True, "channel": "review"},
    )

    assert names == ["routed.skill"]
    assert "Priority: 25" in merged
    assert "Category: policy" in merged
    assert "Trigger: approval_required" in merged
    assert trace[0]["active"] is True


def test_trigger_filter_excludes_approval_skill_when_not_required(tmp_path: Path) -> None:
    (tmp_path / "approval.skill.md").write_text(
        """---
name: approval
trigger: approval_required
priority: 40
---
- emit approval summary
""",
        encoding="utf-8",
    )
    loader = SkillLoader(tmp_path)

    merged, names, trace = loader.build_system_prompt(
        "base",
        runtime_context={"require_approval": False, "channel": "none"},
    )

    assert merged == "base"
    assert names == []
    assert len(trace) == 1
    assert trace[0]["active"] is False


def test_selected_skills_are_sorted_by_priority(tmp_path: Path) -> None:
    (tmp_path / "late.skill.md").write_text(
        """---
name: late
priority: 90
---
- late rule
""",
        encoding="utf-8",
    )
    (tmp_path / "early.skill.md").write_text(
        """---
name: early
priority: 10
---
- early rule
""",
        encoding="utf-8",
    )
    loader = SkillLoader(tmp_path)

    _, names, _ = loader.build_system_prompt("base", runtime_context={"require_approval": True})

    assert names == ["early.skill", "late.skill"]


def test_get_skill_summaries_groups_by_category(tmp_path: Path) -> None:
    (tmp_path / "risk.skill.md").write_text(
        """---
name: risk-check
category: policy
description: Risk checks and constraints
priority: 10
---
- risk guidance
""",
        encoding="utf-8",
    )
    (tmp_path / "analysis.skill.md").write_text(
        """---
name: thesis-build
category: procedure
description: Thesis construction run
priority: 20
---
- analysis guidance
""",
        encoding="utf-8",
    )
    loader = SkillLoader(tmp_path)
    summaries = loader.get_skill_summaries()

    assert "### policy" in summaries
    assert "### procedure" in summaries
    assert "risk.skill" in summaries
    assert "analysis.skill" in summaries


def test_get_skill_content_wraps_selected_skill(tmp_path: Path) -> None:
    (tmp_path / "alpha.skill.md").write_text(
        """---
name: alpha
description: Alpha run
---
Full skill body.
""",
        encoding="utf-8",
    )
    loader = SkillLoader(tmp_path)
    selected, _ = loader.route(loader.load(), runtime_context={})

    content = loader.get_skill_content("alpha.skill", skills=selected)
    missing = loader.get_skill_content("missing-skill", skills=selected)

    assert '<skill name="alpha.skill">' in content
    assert "Full skill body." in content
    assert missing.startswith("Error: Unknown skill")
