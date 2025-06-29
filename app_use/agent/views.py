from __future__ import annotations

import json
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from langchain_core.language_models.chat_models import BaseChatModel
from openai import RateLimitError
from pydantic import (
	BaseModel,
	ConfigDict,
	Field,
	ValidationError,
	create_model,
	model_validator,
)

from app_use.agent.message_manager.views import MessageManagerState
from app_use.controller.registry.views import ActionModel
from app_use.nodes.app_node import AppState

ToolCallingMethod = Literal['function_calling', 'json_mode', 'raw', 'auto', 'tools']
REQUIRED_LLM_API_ENV_VARS = {
	'ChatOpenAI': ['OPENAI_API_KEY'],
	'AzureChatOpenAI': ['AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_KEY'],
	'ChatBedrockConverse': ['ANTHROPIC_API_KEY'],
	'ChatAnthropic': ['ANTHROPIC_API_KEY'],
	'ChatGoogleGenerativeAI': ['GOOGLE_API_KEY'],
	'ChatDeepSeek': ['DEEPSEEK_API_KEY'],
	'ChatOllama': [],
	'ChatGrok': ['GROK_API_KEY'],
}


class AgentSettings(BaseModel):
	"""Options for the agent"""

	use_vision: bool = True
	save_conversation_path: Optional[str] = None
	save_conversation_path_encoding: Optional[str] = 'utf-8'
	max_failures: int = Field(3, ge=1, description='Maximum number of consecutive failures allowed')
	retry_delay: int = Field(10, ge=1, description='Delay in seconds before retrying after a failure')
	max_input_tokens: int = Field(128000, gt=0, description='Maximum number of input tokens')
	validate_output: bool = False
	message_context: Optional[str] = None
	override_system_message: Optional[str] = None
	extend_system_message: Optional[str] = None
	max_actions_per_step: int = Field(10, gt=0, description='Maximum number of actions to execute per step')
	planner_llm: Optional[BaseChatModel] = None
	planner_interval: int = Field(1, ge=1, description='Run planner every N steps')
	is_planner_reasoning: bool = False
	extend_planner_system_prompt: Optional[str] = None
	generate_gif: bool = False

	tool_calling_method: ToolCallingMethod | None = 'auto'
	page_extraction_llm: Optional[BaseChatModel] = None


class AgentState(BaseModel):
	"""Holds all state information for an Agent"""

	agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
	n_steps: int = Field(1, ge=1)
	consecutive_failures: int = Field(0, ge=0)
	last_result: Optional[List[ActionResult]] = None
	last_model_output: Optional[AgentOutput] = None
	history: 'AgentHistoryList' = Field(default_factory=lambda: AgentHistoryList(history=[]))
	paused: bool = False
	stopped: bool = False
	message_manager_state: MessageManagerState = Field(default_factory=MessageManagerState)


@dataclass
class AgentStepInfo:
	step_number: int
	max_steps: int

	def is_last_step(self) -> bool:
		"""Check if this is the last step"""
		return self.step_number >= self.max_steps - 1


class StepMetadata(BaseModel):
	"""Metadata for a single step including timing and token information"""

	step_start_time: float
	step_end_time: float
	input_tokens: int  # Approximate tokens from message manager for this step
	step_number: int = Field(ge=1)

	@property
	def duration_seconds(self) -> float:
		"""Calculate step duration in seconds"""
		return self.step_end_time - self.step_start_time


class AgentBrain(BaseModel):
	"""Current state of the agent"""

	thinking: str
	evaluation_previous_goal: str
	memory: str
	next_goal: str


class AgentOutput(BaseModel):
	"""Output model for agent"""

	model_config = ConfigDict(arbitrary_types_allowed=True)

	thinking: str
	evaluation_previous_goal: str
	memory: str
	next_goal: str
	action: List[ActionModel] = Field(
		...,
		description='List of actions to execute',
		json_schema_extra={'min_items': 1},  # Ensure at least one action is provided
	)

	@property
	def current_state(self) -> AgentBrain:
		"""For backward compatibility - returns an AgentBrain with the flattened properties"""
		return AgentBrain(
			thinking=self.thinking,
			evaluation_previous_goal=self.evaluation_previous_goal,
			memory=self.memory,
			next_goal=self.next_goal,
		)

	@staticmethod
	def type_with_custom_actions(
		custom_actions: type[ActionModel],
	) -> type[AgentOutput]:
		"""Extend actions with custom actions"""
		model_ = create_model(
			'AgentOutput',
			__base__=AgentOutput,
			action=(
				List[custom_actions],
				Field(
					...,
					description='List of actions to execute',
					json_schema_extra={'min_items': 1},
				),
			),
			__module__=AgentOutput.__module__,
		)
		model_.__doc__ = 'AgentOutput model with custom actions'
		return model_


class AppStateHistory(BaseModel):
	"""History of app state for a step"""

	node_count: int = Field(ge=0)
	timestamp: float = Field(default_factory=lambda: time.time())
	tag_names: List[str] = []
	interactive_elements: int = Field(0, ge=0)
	screenshot: Optional[str] = None
	selector_map_size: int = Field(0, ge=0)

	@classmethod
	def from_app_state(cls, app_state: AppState, screenshot: Optional[str] = None) -> 'AppStateHistory':
		"""Create AppStateHistory from a AppState object"""
		# Count all element nodes in the tree
		node_count = len(app_state.selector_map)

		# Get all unique element types
		tag_names = []
		interactive_count = 0

		for node_id, node in app_state.selector_map.items():
			# Add element type if it's an ElementNode with a tag_name attribute
			if hasattr(node, 'tag_name'):
				tag_name = getattr(node, 'tag_name')
				if tag_name not in tag_names:
					tag_names.append(tag_name)

				# Count interactive elements
				if hasattr(node, 'is_interactive') and getattr(node, 'is_interactive'):
					interactive_count += 1

		return cls(
			node_count=node_count,
			tag_names=tag_names,
			interactive_elements=interactive_count,
			screenshot=app_state.screenshot if screenshot is None else screenshot,
			selector_map_size=len(app_state.selector_map),
		)


class AgentHistory(BaseModel):
	"""History item for agent actions"""

	model_output: Optional[AgentOutput] = None
	result: List[ActionResult]
	state: AppStateHistory
	metadata: Optional[StepMetadata] = None

	model_config = ConfigDict(arbitrary_types_allowed=True, protected_namespaces=())

	def model_dump(self, **kwargs) -> Dict[str, Any]:
		"""Custom serialization handling circular references"""
		# Handle action serialization more efficiently
		model_output_dump = None
		if self.model_output:
			# Use the built-in model_dump for the component parts
			model_output_dump = {
				'thinking': self.model_output.thinking,
				'evaluation_previous_goal': self.model_output.evaluation_previous_goal,
				'memory': self.model_output.memory,
				'next_goal': self.model_output.next_goal,
				'action': [action.model_dump(exclude_none=True) for action in self.model_output.action],
			}

		# Build the result dictionary directly
		return {
			'model_output': model_output_dump,
			'result': [r.model_dump(exclude_none=True) for r in self.result],
			'state': self.state.model_dump(),
			'metadata': self.metadata.model_dump() if self.metadata else None,
		}


class AgentHistoryList(BaseModel):
	"""List of agent history items"""

	history: List[AgentHistory] = Field(..., description='List of history items')

	def get_total_duration_seconds(self) -> float:
		"""Get total duration of all steps in seconds"""
		return sum(h.metadata.duration_seconds for h in self.history if h.metadata)

	def get_total_input_tokens(self) -> int:
		"""
		Get total tokens used across all steps.
		Note: These are from the approximate token counting of the message manager.
		For accurate token counting, use tools like LangChain Smith or OpenAI's token counters.
		"""
		return sum(h.metadata.input_tokens for h in self.history if h.metadata)

	def get_input_token_usage(self) -> List[int]:
		"""Get token usage for each step"""
		return [h.metadata.input_tokens for h in self.history if h.metadata]

	def __str__(self) -> str:
		"""Representation of the AgentHistoryList object"""
		return f'AgentHistoryList(all_results={self.get_action_results()}, all_model_outputs={self.get_model_actions()})'

	def __repr__(self) -> str:
		"""Representation of the AgentHistoryList object"""
		return self.__str__()

	def save_to_file(self, filepath: Union[str, Path]) -> None:
		"""Save history to JSON file with proper serialization"""
		try:
			Path(filepath).parent.mkdir(parents=True, exist_ok=True)
			data = self.model_dump()
			with open(filepath, 'w', encoding='utf-8') as f:
				json.dump(data, f, indent=2)
		except Exception as e:
			raise e

	def model_dump(self, **kwargs) -> Dict[str, Any]:
		"""Custom serialization that properly uses AgentHistory's model_dump"""
		return {
			'history': [h.model_dump(**kwargs) for h in self.history],
		}

	@classmethod
	def load_from_file(cls, filepath: Union[str, Path], output_model: type[AgentOutput]) -> 'AgentHistoryList':
		"""Load history from JSON file"""
		with open(filepath, encoding='utf-8') as f:
			data = json.load(f)

		# Loop through history and validate output_model actions
		for h in data['history']:
			if h['model_output']:
				if isinstance(h['model_output'], dict):
					h['model_output'] = output_model.model_validate(h['model_output'])
				else:
					h['model_output'] = None

		history = cls.model_validate(data)
		return history

	def get_last_action(self) -> Optional[Dict]:
		"""Get the last action in history"""
		if self.history and self.history[-1].model_output:
			return self.history[-1].model_output.action[-1].model_dump(exclude_none=True)
		return None

	def get_errors(self) -> List[Optional[str]]:
		"""Get all errors from history, with None for steps without errors"""
		errors = []
		for h in self.history:
			step_errors = [r.error for r in h.result if r.error]
			# each step can have only one error
			errors.append(step_errors[0] if step_errors else None)
		return errors

	def get_final_result(self) -> Optional[str]:
		"""Get final result from history"""
		if self.history and self.history[-1].result[-1].extracted_content:
			return self.history[-1].result[-1].extracted_content
		return None

	def is_done(self) -> bool:
		"""Check if the agent is done"""
		if self.history and len(self.history[-1].result) > 0:
			last_result = self.history[-1].result[-1]
			return last_result.is_done is True
		return False

	def is_successful(self) -> Optional[bool]:
		"""Check if the agent completed successfully - the agent decides in the last step if it was successful or not. None if not done yet."""
		if self.history and len(self.history[-1].result) > 0:
			last_result = self.history[-1].result[-1]
			if last_result.is_done is True:
				return last_result.success
		return None

	def has_errors(self) -> bool:
		"""Check if the agent has any non-None errors"""
		return any(error is not None for error in self.get_errors())

	def get_action_names(self) -> List[str]:
		"""Get all action names from history"""
		action_names = []
		for action in self.get_model_actions():
			actions = list(action.keys())
			if actions:
				action_names.append(actions[0])
		return action_names

	def get_model_thoughts(self) -> List[AgentBrain]:
		"""Get all thoughts from history"""
		return [h.model_output.current_state for h in self.history if h.model_output]

	def get_model_outputs(self) -> List[AgentOutput]:
		"""Get all model outputs from history"""
		return [h.model_output for h in self.history if h.model_output]

	def get_model_actions(self) -> List[Dict]:
		"""Get all actions from history"""
		outputs = []
		for h in self.history:
			if h.model_output:
				for action in h.model_output.action:
					output = action.model_dump(exclude_none=True)
					outputs.append(output)
		return outputs

	def get_action_results(self) -> List[ActionResult]:
		"""Get all results from history"""
		results = []
		for h in self.history:
			results.extend([r for r in h.result if r])
		return results

	def get_extracted_content(self) -> List[str]:
		"""Get all extracted content from history"""
		content = []
		for h in self.history:
			content.extend([r.extracted_content for r in h.result if r.extracted_content])
		return content

	def get_model_actions_filtered(self, include: Optional[List[str]] = None) -> List[Dict]:
		"""Get all model actions from history as JSON filtered by type"""
		if include is None:
			include = []
		outputs = self.get_model_actions()
		result = []
		for o in outputs:
			for i in include:
				if i == list(o.keys())[0]:
					result.append(o)
		return result

	def get_number_of_steps(self) -> int:
		"""Get the number of steps in the history"""
		return len(self.history)

	# For backward compatibility - will be deprecated in future
	total_duration_seconds = get_total_duration_seconds
	total_input_tokens = get_total_input_tokens
	input_token_usage = get_input_token_usage
	last_action = get_last_action
	errors = get_errors
	final_result = get_final_result
	action_names = get_action_names
	model_thoughts = get_model_thoughts
	model_outputs = get_model_outputs
	model_actions = get_model_actions
	action_results = get_action_results
	extracted_content = get_extracted_content
	model_actions_filtered = get_model_actions_filtered
	number_of_steps = get_number_of_steps


class AgentError:
	"""Container for agent error handling"""

	VALIDATION_ERROR = 'Invalid model output format. Please follow the correct schema.'
	RATE_LIMIT_ERROR = 'Rate limit reached. Waiting before retry.'
	NO_VALID_ACTION = 'No valid action found'

	@staticmethod
	def format_error(error: Exception, include_trace: bool = False) -> str:
		"""Format error message based on error type and optionally include trace"""
		if isinstance(error, ValidationError):
			return f'{AgentError.VALIDATION_ERROR}\nDetails: {str(error)}'
		if isinstance(error, RateLimitError):
			return AgentError.RATE_LIMIT_ERROR
		if include_trace:
			return f'{str(error)}\nStacktrace:\n{traceback.format_exc()}'
		return f'{str(error)}'


class ActionResult(BaseModel):
	"""Result of an action execution"""

	# For done action
	is_done: bool | None = False
	success: bool | None = None

	# Error handling - always include in long term memory
	error: str | None = None

	# Files
	attachments: list[str] | None = None  # Files to display in the done message

	# Always include in long term memory
	long_term_memory: str | None = None  # Memory of this action

	# if include_extracted_content_only_once is True we add the extracted_content to the agent context only once for the next step
	# if include_extracted_content_only_once is False we add the extracted_content to the agent long term memory if no long_term_memory is provided
	extracted_content: str | None = None
	include_extracted_content_only_once: bool = False  # Whether the extracted content should be used to update the read_state

	@model_validator(mode='after')
	def validate_success_requires_done(self):
		"""Ensure success=True can only be set when is_done=True"""
		if self.success is True and self.is_done is not True:
			raise ValueError(
				'success=True can only be set when is_done=True. '
				'For regular actions that succeed, leave success as None. '
				'Use success=False only for actions that fail.'
			)
		return self
