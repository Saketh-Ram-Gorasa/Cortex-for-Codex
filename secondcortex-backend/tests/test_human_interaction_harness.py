from models.schemas import ResurrectionCommand
from services.human_interaction_harness import (
    apply_human_interaction_harness,
    normalize_interaction_mode,
    parse_deny_patterns,
)


def test_prompt_mode_marks_high_risk_as_ask_and_keeps_low_risk():
    commands = [
        ResurrectionCommand(type="open_file", filePath="src/main.py"),
        ResurrectionCommand(type="git_checkout", branch="feat/harness"),
        ResurrectionCommand(type="run_command", command="npm run dev"),
    ]

    filtered, interaction = apply_human_interaction_harness(
        commands,
        mode="prompt",
        deny_patterns=parse_deny_patterns("rm -rf,git reset --hard"),
        max_actions=8,
        context_label="query",
    )

    assert len(filtered) == 3
    assert interaction.mode == "prompt"
    assert interaction.requires_confirmation is True
    assert any(item.decision == "ask" for item in interaction.decisions)


def test_critical_command_is_denied_in_allow_mode():
    commands = [
        ResurrectionCommand(type="run_command", command="rm -rf /tmp/foo"),
        ResurrectionCommand(type="open_file", filePath="README.md"),
    ]

    filtered, interaction = apply_human_interaction_harness(
        commands,
        mode="allow",
        deny_patterns=parse_deny_patterns("rm -rf,git reset --hard"),
        max_actions=8,
        context_label="resurrection",
    )

    assert len(filtered) == 1
    assert filtered[0].type == "open_file"
    assert len(interaction.denied_actions) == 1
    assert any(item.risk == "critical" and item.decision == "deny" for item in interaction.decisions)


def test_read_only_mode_allows_open_file_only():
    commands = [
        ResurrectionCommand(type="open_file", filePath="src/main.py"),
        ResurrectionCommand(type="git_checkout", branch="main"),
        ResurrectionCommand(type="run_command", command="pytest -q"),
    ]

    filtered, interaction = apply_human_interaction_harness(
        commands,
        mode="read_only",
        deny_patterns=[],
        max_actions=8,
        context_label="query",
    )

    assert len(filtered) == 1
    assert filtered[0].type == "open_file"
    assert len(interaction.denied_actions) == 2


def test_normalize_mode_falls_back_to_prompt():
    assert normalize_interaction_mode("ALLOW") == "allow"
    assert normalize_interaction_mode("bad-value") == "prompt"
