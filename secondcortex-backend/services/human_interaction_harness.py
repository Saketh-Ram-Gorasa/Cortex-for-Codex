from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from models.schemas import (
	HumanInteractionDecision,
	HumanInteractionEnvelope,
	ResurrectionCommand,
)


InteractionMode = Literal["allow", "prompt", "read_only"]
RiskLevel = Literal["low", "medium", "high", "critical"]
DecisionKind = Literal["allow", "ask", "deny"]


@dataclass
class CommandAssessment:
	index: int
	command: ResurrectionCommand
	risk: RiskLevel
	decision: DecisionKind
	reason: str


def normalize_interaction_mode(raw_mode: str | None) -> InteractionMode:
	value = str(raw_mode or "prompt").strip().lower()
	if value in {"allow", "prompt", "read_only"}:
		return value
	return "prompt"


def parse_deny_patterns(raw: str | None) -> list[str]:
	if not raw:
		return []
	return [item.strip().lower() for item in str(raw).split(",") if item.strip()]


def apply_human_interaction_harness(
	commands: list[ResurrectionCommand],
	*,
	mode: InteractionMode,
	deny_patterns: list[str],
	max_actions: int,
	context_label: str,
) -> tuple[list[ResurrectionCommand], HumanInteractionEnvelope]:
	capped_commands = commands[: max(0, int(max_actions or 0))] if max_actions else commands
	assessments: list[CommandAssessment] = []

	for idx, command in enumerate(capped_commands):
		risk = _assess_risk(command, deny_patterns)
		decision, reason = _resolve_decision(command, risk, mode)
		assessments.append(
			CommandAssessment(
				index=idx,
				command=command,
				risk=risk,
				decision=decision,
				reason=reason,
			)
		)

	allowed_commands = [item.command for item in assessments if item.decision != "deny"]
	decisions = [
		HumanInteractionDecision(
			actionId=f"action_{item.index + 1}",
			commandType=item.command.type,
			decision=item.decision,
			risk=item.risk,
			reason=item.reason,
			commandPreview=_command_preview(item.command),
		)
		for item in assessments
	]

	ask_count = sum(1 for item in assessments if item.decision == "ask")
	denied = [f"action_{item.index + 1}" for item in assessments if item.decision == "deny"]
	allowed = [f"action_{item.index + 1}" for item in assessments if item.decision != "deny"]

	prompt = ""
	if ask_count > 0:
		prompt = (
			f"{ask_count} action(s) in this {context_label} plan require explicit user confirmation "
			f"before execution."
		)
	elif denied:
		prompt = f"Blocked {len(denied)} unsafe action(s) from this {context_label} plan."

	envelope = HumanInteractionEnvelope(
		mode=mode,
		requiresConfirmation=ask_count > 0,
		prompt=prompt,
		decisions=decisions,
		allowedActions=allowed,
		deniedActions=denied,
	)
	return allowed_commands, envelope


def _assess_risk(command: ResurrectionCommand, deny_patterns: list[str]) -> RiskLevel:
	command_type = (command.type or "").strip().lower()
	preview = _command_preview(command).lower()

	if command_type == "open_file":
		return "low"

	if command_type in {"git_checkout", "split_terminal"}:
		return "medium"

	if command_type in {"open_workspace", "git_stash"}:
		return "high"

	if command_type == "run_command":
		for pattern in deny_patterns:
			if pattern and pattern in preview:
				return "critical"
		if re.search(r"\b(sudo|admin|chmod\s+777|powershell\s+-executionpolicy)\b", preview):
			return "high"
		return "medium"

	return "medium"


def _resolve_decision(
	command: ResurrectionCommand,
	risk: RiskLevel,
	mode: InteractionMode,
) -> tuple[DecisionKind, str]:
	command_type = (command.type or "").strip().lower()

	if risk == "critical":
		return "deny", "Blocked by safety policy: critical command pattern detected."

	if mode == "allow":
		return "allow", "Auto-approved by allow mode."

	if mode == "read_only":
		if command_type == "open_file":
			return "allow", "Allowed in read_only mode (read action)."
		return "deny", "Blocked in read_only mode (state-changing action)."

	# prompt mode
	if risk in {"medium", "high"}:
		return "ask", "Requires explicit user confirmation in prompt mode."
	return "allow", "Low-risk action auto-approved in prompt mode."


def _command_preview(command: ResurrectionCommand) -> str:
	if command.type == "run_command":
		return str(command.command or "").strip()
	if command.type == "open_file":
		return str(command.file_path or "").strip()
	if command.type == "git_checkout":
		return f"git checkout {str(command.branch or 'main').strip()}"
	if command.type == "open_workspace":
		return str(command.file_path or "").strip()
	return command.type
