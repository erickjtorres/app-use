"""Prompt helper classes for mobile app-use agents."""

from __future__ import annotations

import importlib.resources
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from langchain_core.messages import HumanMessage, SystemMessage

if TYPE_CHECKING:  # pragma: no cover
	# These are only for type-checking / IDE auto-completion – avoid cyclic deps
	from app_use.agent.views import AgentStepInfo
	from app_use.nodes.app_node import AppState


class SystemPrompt:
	"""Generate the system prompt used for the LLM conversation.

	The prompt template lives in *app_use/agent/system_prompt_mobile.md*.
	If that file cannot be found we fall back to a small built-in template so
	that the agent can still run in development environments without requiring
	extra resources to be bundled.
	"""

	DEFAULT_TEMPLATE = (
		'You are an AI assistant that helps users interact with mobile '
		'applications through automation. You can perform taps, swipes, text entry, '
		'and other high-level actions on mobile apps. Always think step-by-step, reference '
		'interactive elements by their *index* as provided, and only use the '
		'available actions. When working with mobile apps, be aware of common '
		'mobile UI patterns like navigation drawers, tab bars, and gesture-based interactions.'
		'\n\n'  # newline so the caller can append the dynamic action list
		'Your AVAILABLE ACTIONS:\n{actions}\n'
		'# End of system instructions'
	)

	def __init__(
		self,
		action_description: str,
		max_actions_per_step: int = 10,
		override_system_message: str | None = None,
		extend_system_message: str | None = None,
	) -> None:
		self.default_action_description = action_description
		self.max_actions_per_step = max_actions_per_step

		# Decide final prompt content.
		if override_system_message is not None:
			prompt_text = override_system_message
		else:
			prompt_text = self._load_prompt_template().format(max_actions=max_actions_per_step)
		# Append dynamic section with actions.
		prompt_text = prompt_text.replace('{actions}', action_description)

		if extend_system_message:
			prompt_text += f'\n{extend_system_message}'

		self.system_message = SystemMessage(content=prompt_text)

	# ---------------------------------------------------------------------
	# Helpers
	# ---------------------------------------------------------------------

	def _load_prompt_template(self) -> str:
		"""Load the markdown template from package resources or fallback."""
		try:
			with importlib.resources.files('app_use.agent').joinpath('system_prompt.md').open('r', encoding='utf-8') as f:
				return f.read()
		except (FileNotFoundError, ModuleNotFoundError):
			# Development / editable install – fall back to built-in template.
			return self.DEFAULT_TEMPLATE

	# ------------------------------------------------------------------
	# API
	# ------------------------------------------------------------------
	def get_system_message(self) -> SystemMessage:
		"""Return the ready-to-use *SystemMessage* instance."""
		return self.system_message


class PlannerPrompt(SystemPrompt):
	"""Provides a secondary prompt used by a *planning* agent."""

	def __init__(
		self,
		available_actions: str,
		original_task: str = '',
		current_step: int = 1,
		is_reasoning: bool = False,
		extend_prompt: str | None = None,
	):
		self.available_actions = available_actions
		self.original_task = original_task
		self.current_step = current_step
		self.is_reasoning = is_reasoning
		self.extend_prompt = extend_prompt

	def get_system_message(
		self,
		*,
		is_planner_reasoning: bool = None,
		extended_planner_system_prompt: str | None = None,
	) -> SystemMessage | HumanMessage:
		"""Return either a *SystemMessage* or *HumanMessage* depending on COT needs."""

		# Use instance variables if method parameters are not provided
		if is_planner_reasoning is None:
			is_planner_reasoning = self.is_reasoning
		if extended_planner_system_prompt is None:
			extended_planner_system_prompt = self.extend_prompt

		planner_prompt_text = f"""
You are a planning agent that helps break down tasks into smaller steps when interacting with **mobile** apps.

Original task: {self.original_task}
Current step: {self.current_step}

Your role is to:
1. Analyse the current state and history
2. Evaluate progress towards the ultimate goal
3. Identify potential challenges or roadblocks
4. Suggest the next high-level steps to take

Available actions for the main agent:
{self.available_actions}

Respond strictly as a JSON object with the following fields:
{{
    "state_analysis": "Brief analysis of the current state and what has been done so far",
    "progress_evaluation": "Evaluation of progress towards the ultimate goal (percentage + short description)",
    "challenges": "List any potential challenges or roadblocks",
    "next_steps": "List 2-3 concrete next steps to take",
    "reasoning": "Explain your reasoning for the suggested next steps"
}}
"""
		if extended_planner_system_prompt:
			planner_prompt_text += f'\n{extended_planner_system_prompt}'

		if is_planner_reasoning:
			# For chain-of-thought we provide the text as a *HumanMessage* so the
			# model reveals its reasoning but we do NOT expose that to the final
			# user.
			return HumanMessage(content=planner_prompt_text)
		return SystemMessage(content=planner_prompt_text)


# -------------------------------------------------------------------------
# User state → message converter (moved from message_manager.service)
# -------------------------------------------------------------------------
class AgentMessagePrompt:
	"""Generate a human-readable message from the current mobile app state.

	This class was originally located in *agent/message_manager/service.py* but
	has been moved here to keep all prompt-related helpers in a single module
	and avoid circular dependencies.
	"""

	def __init__(
		self,
		app_state: AppState,
		agent_history_description: str | None = None,
		read_state_description: str | None = None,
		task: str | None = None,
		include_attributes: list[str] | None = None,
		step_info: Optional['AgentStepInfo'] = None,
		sensitive_data: str | None = None,
	) -> None:
		self.app_state = app_state
		self.agent_history_description = agent_history_description
		self.read_state_description = read_state_description
		self.task = task
		self.include_attributes = include_attributes or []
		self.step_info = step_info
		self.sensitive_data = sensitive_data

	# ------------------------------------------------------------------
	# Public helpers
	# ------------------------------------------------------------------
	def _get_app_state_description(self) -> str:
		"""Get description of the current app state"""
		# List interactive elements in the current viewport
		elements_text = self.app_state.element_tree.interactive_elements_to_string(include_attributes=self.include_attributes)

		has_content_above = (self.app_state.pixels_above or 0) > 0
		has_content_below = (self.app_state.pixels_below or 0) > 0

		if elements_text:
			if has_content_above:
				elements_text = (
					f'... {self.app_state.pixels_above} pixels above - scroll or extract content to see more ...\n{elements_text}'
				)
			else:
				elements_text = f'[Start of page]\n{elements_text}'

			if has_content_below:
				elements_text = (
					f'{elements_text}\n... {self.app_state.pixels_below} pixels below - scroll or extract content to see more ...'
				)
			else:
				elements_text = f'{elements_text}\n[End of page]'
		else:
			elements_text = 'empty page'

		return f'Interactive elements from top layer of the current page inside the viewport:\n{elements_text}'

	def _get_agent_state_description(self) -> str:
		"""Get description of current agent state and context"""
		if self.step_info:
			step_info_description = f'Step {self.step_info.step_number + 1} of {self.step_info.max_steps} max possible steps\n'
		else:
			step_info_description = ''

		time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
		step_info_description += f'Current date and time: {time_str}'

		agent_state = f"""
<user_request>
{self.task}
</user_request>
<step_info>
{step_info_description}
</step_info>
"""
		if self.sensitive_data:
			agent_state += f'<sensitive_data>\n{self.sensitive_data}\n</sensitive_data>\n'

		return agent_state.strip()

	def get_user_message(self, use_vision: bool = True) -> HumanMessage:
		"""Return a `HumanMessage` describing *app_state* with viewport context."""

		state_description = (
			'<agent_history>\n'
			+ (self.agent_history_description.strip('\n') if self.agent_history_description else '')
			+ '\n</agent_history>\n'
		)
		state_description += '<agent_state>\n' + self._get_agent_state_description().strip('\n') + '\n</agent_state>\n'
		state_description += '<app_state>\n' + self._get_app_state_description().strip('\n') + '\n</app_state>\n'
		state_description += (
			'<read_state>\n'
			+ (self.read_state_description.strip('\n') if self.read_state_description else '')
			+ '\n</read_state>\n'
		)

		# Multi-modal message (text + screenshot) for vision models
		if use_vision is True and self.app_state.screenshot:
			return HumanMessage(
				content=[
					{'type': 'text', 'text': state_description},
					{
						'type': 'image_url',
						'image_url': {'url': f'data:image/png;base64,{self.app_state.screenshot}'},
					},
				]
			)

		return HumanMessage(content=state_description)
