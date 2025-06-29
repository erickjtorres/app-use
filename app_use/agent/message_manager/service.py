from __future__ import annotations

import logging
import re
import shutil
from typing import TYPE_CHECKING

from langchain_core.messages import (
	AIMessage,
	BaseMessage,
	HumanMessage,
	SystemMessage,
	ToolMessage,
)
from pydantic import BaseModel

from app_use.agent.message_manager.views import ManagedMessage, MessageManagerState, MessageMetadata
from app_use.agent.prompts import AgentMessagePrompt  # moved from this module
from app_use.nodes.app_node import AppState
from app_use.utils import time_execution_sync

if TYPE_CHECKING:
	from app_use.agent.views import ActionResult, AgentOutput, AgentStepInfo

logger = logging.getLogger(__name__)


def _log_get_message_emoji(message_type: str) -> str:
	"""Get emoji for a message type - used only for logging display"""
	emoji_map = {
		'HumanMessage': '💬',
		'AIMessage': '🧠',
		'ToolMessage': '🔨',
	}
	return emoji_map.get(message_type, '🎮')


def _log_clean_whitespace(text: str) -> str:
	"""Replace all repeated whitespace with single space and strip - used only for logging display"""
	return re.sub(r'\s+', ' ', text).strip()


def _log_extract_text_from_list_content(content: list) -> str:
	"""Extract text from list content structure - used only for logging display"""
	text_content = ''
	for item in content:
		if isinstance(item, dict) and 'text' in item:
			text_content += item['text']
	return text_content


def _log_format_agent_output_content(tool_call: dict) -> str:
	"""Format AgentOutput tool call into readable content - used only for logging display"""
	try:
		args = tool_call.get('args', {})
		action_info = ''

		# Get action name
		if 'action' in args and args['action']:
			first_action = args['action'][0] if isinstance(args['action'], list) and args['action'] else args['action']
			if isinstance(first_action, dict):
				action_name = next(iter(first_action.keys())) if first_action else 'unknown'
				action_info = f'{action_name}()'

		# Get goal
		goal_info = ''
		if 'current_state' in args and isinstance(args['current_state'], dict):
			next_goal = args['current_state'].get('next_goal', '').strip()
			if next_goal:
				# Clean whitespace from goal text to prevent newlines
				next_goal = _log_clean_whitespace(next_goal)
				goal_info = f': {next_goal}'

		# Combine action and goal info
		if action_info and goal_info:
			return f'{action_info}{goal_info}'
		elif action_info:
			return action_info
		elif goal_info:
			return goal_info[2:]  # Remove ': ' prefix for goal-only
		else:
			return 'AgentOutput'
	except Exception as e:
		logger.warning(f'Failed to format agent output content for logging: {e}')
		return 'AgentOutput'


def _log_extract_message_content(message: BaseMessage, is_last_message: bool, metadata: MessageMetadata | None = None) -> str:
	"""Extract content from a message for logging display only"""
	try:
		message_type = message.__class__.__name__

		if is_last_message and message_type == 'HumanMessage' and isinstance(message.content, list):
			# Special handling for last message with list content
			text_content = _log_extract_text_from_list_content(message.content)
			text_content = _log_clean_whitespace(text_content)

			# Look for current state section
			if '[Current state starts here]' in text_content:
				start_idx = text_content.find('[Current state starts here]')
				return text_content[start_idx:]
			return text_content

		# Standard content extraction
		cleaned_content = _log_clean_whitespace(str(message.content))

		# Handle AIMessages with tool calls
		if isinstance(message, AIMessage) and hasattr(message, 'tool_calls') and message.tool_calls and not cleaned_content:
			tool_call = message.tool_calls[0]
			tool_name = tool_call.get('name', 'unknown')

			if tool_name == 'AgentOutput':
				# Skip formatting for init example messages
				if metadata and metadata.message_type == 'init':
					return '[Example AgentOutput]'
				content = _log_format_agent_output_content(tool_call)
			else:
				content = f'[TOOL: {tool_name}]'
		else:
			content = cleaned_content

		# Shorten "Action result:" to "Result:" for display
		if content.startswith('Action result:'):
			content = 'Result:' + content[14:]

		return content
	except Exception as e:
		logger.warning(f'Failed to extract message content for logging: {e}')
		return '[Error extracting content]'


class MessageManagerSettings(BaseModel):
	"""Settings for the message manager"""

	max_input_tokens: int = 128000
	estimated_characters_per_token: int = 3
	image_tokens: int = 800
	include_attributes: list[str] = []
	message_context: str | None = None
	# Support both old format {key: value} and new format {domain: {key: value}}
	sensitive_data: dict[str, str | dict[str, str]] | None = None
	available_file_paths: list[str] | None = None


class MessageManager:
	"""
	Manages the conversation history between the agent and the LLM
	"""

	def __init__(
		self,
		task: str,
		system_message: SystemMessage,
		settings: MessageManagerSettings = MessageManagerSettings(),
		state: MessageManagerState = MessageManagerState(),
	):
		self.task = task
		self.settings = settings
		self.state = state
		self.system_prompt = system_message
		self.agent_history_description = 'Agent initialized.\n'
		self.read_state_description = ''
		self.sensitive_data_description = ''

		if len(self.state.history.messages) == 0:
			self._init_messages()

	def _init_messages(self) -> None:
		"""Initialize the message history with system message, context, task, and other initial messages"""
		self._add_message_with_tokens(self.system_prompt, message_type='init')

		if self.settings.message_context:
			context_message = HumanMessage(content='Context for the task' + self.settings.message_context)
			self._add_message_with_tokens(context_message, message_type='init')

		task_message = HumanMessage(
			content=f'Your ultimate task is: """{self.task}""". If you achieved your ultimate task, stop everything and use the done action in the next step to complete the task. If not, continue as usual.'
		)
		self._add_message_with_tokens(task_message, message_type='init')

		if self.settings.sensitive_data:
			info = f'<sensitive_data>Here are placeholders for sensitive data: {list(self.settings.sensitive_data.keys())}'
			info += '\nTo use them, write <secret>the placeholder name</secret> </sensitive_data>'
			info_message = HumanMessage(content=info)
			self._add_message_with_tokens(info_message, message_type='init')

		placeholder_message = HumanMessage(
			content='<example_1>\nHere is an example output of thinking and action execution. You can use it as a reference but do not copy it exactly.'
		)
		self._add_message_with_tokens(placeholder_message, message_type='init')

		example_tool_call = AIMessage(
			content='',
			tool_calls=[
				{
					'name': 'AgentOutput',
					'args': {
						'thinking': """I need to analyze the current state of the mobile app. I can see several interactive elements, including a 'Continue' button at index [15]. The user wants me to navigate through the app and complete some task. I should tap on the Continue button to proceed to the main screen.""",
						'evaluation_previous_goal': """
                        Success - I successfully tapped on the 'Continue' button, which brought me to 
                        the main screen of the app. This is a successful step toward completing my task.
                        """.strip(),
						'memory': """
                        I navigated through the app and found the login screen. I used the 'tap_element_by_index' 
                        action to tap on element at index [15] labeled 'Continue' which took me to the main screen.
                        Currently at step 3/15.
                        """.strip(),
						'next_goal': """
                        Looking at the element structure of the current screen, I can see a SearchBar element at 
                        index [8]. I'll use the 'enter_text' action to search for the item I need to find.
                        """.strip(),
						'action': [{'tap_element_by_index': {'index': 8}}],
					},
					'id': str(self.state.tool_id),
					'type': 'tool_call',
				},
			],
		)
		self._add_message_with_tokens(example_tool_call, message_type='init')
		self.add_tool_message(content='Tapped element with index 8.\n</example_1>', message_type='init')

		placeholder_message = HumanMessage(content='[Your task history memory starts here]')
		self._add_message_with_tokens(placeholder_message)

		if self.settings.available_file_paths:
			filepaths_msg = HumanMessage(content=f'Here are file paths you can use: {self.settings.available_file_paths}')
			self._add_message_with_tokens(filepaths_msg, message_type='init')

	def add_new_task(self, new_task: str) -> None:
		"""Update the task and add a message about it"""
		self.task = new_task
		self.agent_history_description += f'\nUser updated USER REQUEST to: {new_task}\n'

	def _update_agent_history_description(
		self,
		model_output: 'AgentOutput' | None = None,
		result: list['ActionResult'] | None = None,
		step_info: 'AgentStepInfo' | None = None,
	) -> None:
		"""Update the agent history description"""

		if result is None:
			result = []
		step_number = step_info.step_number if step_info else 'unknown'

		self.read_state_initialization = 'This is displayed only **one time**, save this information if you need it later.\n'
		self.read_state_description = self.read_state_initialization

		action_results = ''
		result_len = len(result)
		for idx, action_result in enumerate(result):
			if action_result.include_extracted_content_only_once and action_result.extracted_content:
				self.read_state_description += action_result.extracted_content + '\n'
				logger.debug(f'Added extracted_content to read_state_description: {action_result.extracted_content}')

			if action_result.long_term_memory:
				action_results += f'Action {idx + 1}/{result_len} response: {action_result.long_term_memory}\n'
				logger.debug(f'Added long_term_memory to action_results: {action_result.long_term_memory}')
			elif action_result.extracted_content and not action_result.include_extracted_content_only_once:
				action_results += f'Action {idx + 1}/{result_len} response: {action_result.extracted_content}\n'
				logger.debug(f'Added extracted_content to action_results: {action_result.extracted_content}')

			if action_result.error:
				action_results += f'Action {idx + 1}/{result_len} response: {action_result.error[:200]}\n'
				logger.debug(f'Added error to action_results: {action_result.error[:200]}')

		# Handle case where model_output is None (e.g., parsing failed)
		if model_output is None:
			if isinstance(step_number, int) and step_number > 0:
				self.agent_history_description += f"""## Step {step_number}
No model output (parsing failed)
{action_results}
"""
		else:
			self.agent_history_description += f"""## Step {step_number}
Step evaluation: {model_output.current_state.evaluation_previous_goal}
Step memory: {model_output.current_state.memory}
Step goal: {model_output.current_state.next_goal}
{action_results}
"""

		if self.read_state_description == self.read_state_initialization:
			self.read_state_description = ''
		else:
			self.read_state_description += '\nMAKE SURE TO SAVE THIS INFORMATION INTO A FILE OR TO MEMORY IF YOU NEED IT LATER.'

	@time_execution_sync('--add_state_message')
	def add_state_message(
		self,
		app_state: AppState,
		model_output: 'AgentOutput' | None = None,
		result: list['ActionResult'] | None = None,
		step_info: 'AgentStepInfo' | None = None,
		use_vision=True,
	) -> None:
		"""Add app state as human message"""
		self._update_agent_history_description(model_output, result, step_info)
		if self.settings.sensitive_data:
			self.sensitive_data_description = self._get_sensitive_data_description()

		state_message = AgentMessagePrompt(
			app_state=app_state,
			agent_history_description=self.agent_history_description,
			read_state_description=self.read_state_description,
			task=self.task,
			include_attributes=self.settings.include_attributes,
			step_info=step_info,
			sensitive_data=self.sensitive_data_description,
		).get_user_message(use_vision)

		self._add_message_with_tokens(state_message)

	def add_model_output(self, model_output: AgentOutput) -> None:
		"""Add model output as AI message"""
		tool_calls = [
			{
				'name': 'AgentOutput',
				'args': model_output.model_dump(mode='json', exclude_unset=True),
				'id': str(self.state.tool_id),
				'type': 'tool_call',
			}
		]

		msg = AIMessage(
			content='',
			tool_calls=tool_calls,
		)

		self._add_message_with_tokens(msg)
		self.add_tool_message(content='')

	def add_plan(self, plan: str | None, position: int | None) -> None:
		"""Add a planning analysis message"""
		if plan:
			msg = AIMessage(content=plan)
			self._add_message_with_tokens(msg, position)

	def _log_history_lines(self) -> str:
		"""Generate a formatted log string of message history for debugging / printing to terminal"""
		try:
			total_input_tokens = 0
			message_lines = []
			terminal_width = shutil.get_terminal_size((80, 20)).columns

			for i, m in enumerate(self.state.history.messages):
				try:
					total_input_tokens += m.metadata.tokens
					is_last_message = i == len(self.state.history.messages) - 1

					# Extract content for logging
					content = _log_extract_message_content(m.message, is_last_message, m.metadata)

					# Format the message line(s)
					lines = self._log_format_message_line(m, content, is_last_message, terminal_width)
					message_lines.extend(lines)
				except Exception as e:
					logger.warning(f'Failed to format message {i} for logging: {e}')
					# Add a fallback line for this message
					message_lines.append('❓[   ?]: [Error formatting this message]')

			# Build final log message
			return (
				f'📜 LLM Message history ({len(self.state.history.messages)} messages, {total_input_tokens} tokens):\n'
				+ '\n'.join(message_lines)
			)
		except Exception as e:
			logger.warning(f'Failed to generate history log: {e}')
			# Return a minimal fallback message
			return f'📜 LLM Message history (error generating log: {e})'

	@time_execution_sync('--get_messages')
	def get_messages(self) -> list[BaseMessage]:
		"""Get current message list, potentially trimmed to max tokens"""
		messages = [m.message for m in self.state.history.messages]

		logger.debug(self._log_history_lines())

		return messages

	def _add_message_with_tokens(
		self,
		message: BaseMessage,
		position: int | None = None,
		message_type: str | None = None,
	) -> None:
		"""Add message with token count metadata
		position: None for last, -1 for second last, etc.
		"""
		# Filter out sensitive data
		if self.settings.sensitive_data:
			message = self._filter_sensitive_data(message)

		token_count = self._count_tokens(message)
		metadata = MessageMetadata(tokens=token_count, message_type=message_type)
		self.state.history.add_message(message, metadata, position)

	@time_execution_sync('--filter_sensitive_data')
	def _filter_sensitive_data(self, message: BaseMessage) -> BaseMessage:
		"""Filter out sensitive data from the message"""

		def replace_sensitive(value: str) -> str:
			if not self.settings.sensitive_data:
				return value

			# Collect all sensitive values, immediately converting old format to new format
			sensitive_values: dict[str, str] = {}

			# Process all sensitive data entries
			for key_or_domain, content in self.settings.sensitive_data.items():
				if isinstance(content, dict):
					# Already in new format: {domain: {key: value}}
					for key, val in content.items():
						if val:  # Skip empty values
							sensitive_values[key] = val
				elif content:  # Old format: {key: value} - convert to new format internally
					# We treat this as if it was {'http*://*': {key_or_domain: content}}
					sensitive_values[key_or_domain] = content

			# If there are no valid sensitive data entries, just return the original value
			if not sensitive_values:
				logger.warning('No valid entries found in sensitive_data dictionary')
				return value

			# Replace all valid sensitive data values with their placeholder tags
			for key, val in sensitive_values.items():
				value = value.replace(val, f'<secret>{key}</secret>')

			return value

		if isinstance(message.content, str):
			message.content = replace_sensitive(message.content)
		elif isinstance(message.content, list):
			for i, item in enumerate(message.content):
				if isinstance(item, dict) and 'text' in item:
					item['text'] = replace_sensitive(item['text'])
					message.content[i] = item
		return message

	def _count_tokens(self, message: BaseMessage) -> int:
		"""Count tokens in a message using a rough estimate"""
		tokens = 0
		if isinstance(message.content, list):
			for item in message.content:
				if 'image_url' in item:
					tokens += self.settings.image_tokens
				elif isinstance(item, dict) and 'text' in item:
					tokens += self._count_text_tokens(item['text'])
		else:
			msg_content = message.content
			if hasattr(message, 'tool_calls'):
				msg_content += str(message.tool_calls)
			tokens += self._count_text_tokens(msg_content)
		return tokens

	def _count_text_tokens(self, text: str) -> int:
		tokens = len(text) // self.settings.estimated_characters_per_token
		return tokens

	def cut_messages(self):
		"""Get current message list, potentially trimmed to max tokens"""
		diff = self.state.history.current_tokens - self.settings.max_input_tokens
		if diff <= 0:
			return None

		msg = self.state.history.messages[-1]

		if isinstance(msg.message.content, list):
			text = ''
			for item in msg.message.content:
				if 'image_url' in item:
					msg.message.content.remove(item)
					diff -= self.settings.image_tokens
					msg.metadata.tokens -= self.settings.image_tokens
					self.state.history.current_tokens -= self.settings.image_tokens
					logger.debug(
						f'Removed image with {self.settings.image_tokens} tokens - total tokens now: '
						f'{self.state.history.current_tokens}/{self.settings.max_input_tokens}'
					)
				elif 'text' in item and isinstance(item, dict):
					text += item['text']
			msg.message.content = text
			self.state.history.messages[-1] = msg

		if diff <= 0:
			return None

		proportion_to_remove = diff / msg.metadata.tokens
		if proportion_to_remove > 0.99:
			raise ValueError(
				f'Max token limit reached - history is too long - reduce the system prompt or task. '
				f'proportion_to_remove: {proportion_to_remove}'
			)
		logger.debug(
			f'Removing {proportion_to_remove * 100:.2f}% of the last message '
			f'({proportion_to_remove * msg.metadata.tokens:.2f} / {msg.metadata.tokens:.2f} tokens)'
		)

		content = msg.message.content
		characters_to_remove = int(len(content) * proportion_to_remove)
		content = content[:-characters_to_remove]

		self.state.history.remove_last_state_message()
		msg = HumanMessage(content=content)
		self._add_message_with_tokens(msg)

		last_msg = self.state.history.messages[-1]
		logger.debug(
			f'Added message with {last_msg.metadata.tokens} tokens - total tokens now: '
			f'{self.state.history.current_tokens}/{self.settings.max_input_tokens} - '
			f'total messages: {len(self.state.history.messages)}'
		)

	def _remove_last_state_message(self) -> None:
		"""Remove last state message from history"""
		self.state.history.remove_last_state_message()

	def add_tool_message(self, content: str, message_type: str | None = None) -> None:
		"""Add tool message to history"""
		msg = ToolMessage(content=content, tool_call_id=str(self.state.tool_id))
		self.state.tool_id += 1
		self._add_message_with_tokens(msg, message_type=message_type)

	def _get_sensitive_data_description(self) -> str:
		"""Get sensitive data description for placeholders"""
		sensitive_data = self.settings.sensitive_data
		if not sensitive_data:
			return ''

		# Collect placeholders for sensitive data
		placeholders = set()

		for key, value in sensitive_data.items():
			if isinstance(value, dict):
				# New format: {domain: {key: value}}
				placeholders.update(value.keys())
			else:
				# Old format: {key: value}
				placeholders.add(key)

		if placeholders:
			info = f'Here are placeholders for sensitive data: {list(placeholders)}'
			info += '\nTo use them, write <secret>the placeholder name</secret>'
			return info

		return ''

	def _log_format_message_line(
		self,
		message_with_metadata: object,
		content: str,
		is_last_message: bool,
		terminal_width: int,
	) -> list[str]:
		"""Format a single message for logging display"""
		try:
			lines = []

			# Get emoji and token info
			if isinstance(message_with_metadata, ManagedMessage):
				message_type = message_with_metadata.message.__class__.__name__
				emoji = _log_get_message_emoji(message_type)
				token_str = str(message_with_metadata.metadata.tokens).rjust(4)
			else:
				return ['❓[   ?]: [Invalid message format]']
			prefix = f'{emoji}[{token_str}]: '

			# Calculate available width (emoji=2 visual cols + [token]: =8 chars)
			content_width = terminal_width - 10

			# Handle last message wrapping
			if is_last_message and len(content) > content_width:
				# Find a good break point
				break_point = content.rfind(' ', 0, content_width)
				if break_point > content_width * 0.7:  # Keep at least 70% of line
					first_line = content[:break_point]
					rest = content[break_point + 1 :]
				else:
					# No good break point, just truncate
					first_line = content[:content_width]
					rest = content[content_width:]

				lines.append(prefix + first_line)

				# Second line with 10-space indent
				if rest:
					if len(rest) > terminal_width - 10:
						rest = rest[: terminal_width - 10]
					lines.append(' ' * 10 + rest)
			else:
				# Single line - truncate if needed
				if len(content) > content_width:
					content = content[:content_width]
				lines.append(prefix + content)

			return lines
		except Exception as e:
			logger.warning(f'Failed to format message line for logging: {e}')
			# Return a simple fallback line
			return ['❓[   ?]: [Error formatting message]']
