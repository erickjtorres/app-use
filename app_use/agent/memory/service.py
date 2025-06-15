from __future__ import annotations

"""Procedural memory service for *app-use* agents."""

import logging
import os
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.messages.utils import convert_to_openai_messages

from app_use.agent.memory.views import MemoryConfig
from app_use.agent.message_manager.service import MessageManager
from app_use.utils import time_execution_sync

logger = logging.getLogger(__name__)


class Memory:
	"""Manage procedural memory for *app-use* agents.

	The class is a thin façade around `mem0.Memory`.  Every *memory_interval*
	steps we create a summary of the most recent interaction window and insert
	it back into the conversation history to keep the context window under
	control while still preserving crucial information.
	"""

	def __init__(
		self,
		message_manager: MessageManager,
		llm: BaseChatModel,
		config: MemoryConfig | None = None,
	) -> None:
		self.message_manager = message_manager
		self.llm = llm

		# ------------------------------------------------------------------
		# Derive configuration defaults if none provided -------------------
		# ------------------------------------------------------------------
		if config is None:
			cfg = MemoryConfig(llm_instance=llm, agent_id=f'agent_{id(self)}')

			# Set appropriate embedder based on LLM type, but default to huggingface for compatibility
			llm_cls = llm.__class__.__name__
			if llm_cls == 'ChatOpenAI' and os.getenv('OPENAI_API_KEY'):
				cfg.embedder_provider = 'openai'
				cfg.embedder_model = 'text-embedding-3-small'
				cfg.embedder_dims = 1536
			elif llm_cls == 'ChatGoogleGenerativeAI' and os.getenv('GOOGLE_API_KEY'):
				cfg.embedder_provider = 'gemini'
				cfg.embedder_model = 'models/text-embedding-004'
				cfg.embedder_dims = 768
			elif llm_cls == 'ChatOllama':
				cfg.embedder_provider = 'ollama'
				cfg.embedder_model = 'nomic-embed-text'
				cfg.embedder_dims = 512
			else:
				# Default to huggingface for models without embedding support or missing API keys
				cfg.embedder_provider = 'huggingface'
				cfg.embedder_model = 'all-MiniLM-L6-v2'
				cfg.embedder_dims = 384
			self.config = cfg
		else:
			# Validate and patch LLM instance into user-provided config
			self.config = MemoryConfig.model_validate(config)
			self.config.llm_instance = llm

		# ------------------------------------------------------------------
		# Dependency checks -------------------------------------------------
		# ------------------------------------------------------------------
		try:
			if os.getenv('ANONYMIZED_TELEMETRY', 'true').lower()[0] in 'fn0':
				os.environ['MEM0_TELEMETRY'] = 'False'
			from mem0 import Memory as Mem0Memory  # pylint: disable=import-error
		except ImportError as exc:  # pragma: no cover
			raise ImportError('mem0 is required when enable_memory=True. Please install it with `pip install mem0`.') from exc

		if self.config.embedder_provider == 'huggingface':
			try:
				from sentence_transformers import SentenceTransformer  # noqa: F401
			except ImportError as exc:  # pragma: no cover
				raise ImportError(
					'sentence_transformers is required when enable_memory=True and embedder_provider="huggingface". '
					'Please install it with `pip install sentence-transformers`.'
				) from exc

		# Instantiate Mem0 backend

		self.mem0 = Mem0Memory.from_config(config_dict=self.config.full_config_dict)

	# ------------------------------------------------------------------
	# Public API --------------------------------------------------------
	# ------------------------------------------------------------------
	@time_execution_sync('--create_procedural_memory')
	def create_procedural_memory(self, current_step: int) -> None:
		"""Create and insert procedural memory into chat history if needed."""
		logger.debug('Creating procedural memory at step %s', current_step)

		all_messages = self.message_manager.state.history.messages
		new_messages: list[Any] = []  # maintain same ManagedMessage type
		messages_to_process: list[Any] = []

		for msg in all_messages:
			if hasattr(msg, 'metadata') and msg.metadata.message_type in {
				'init',
				'memory',
			}:
				new_messages.append(msg)
			else:
				if getattr(msg.message, 'content', ''):
					messages_to_process.append(msg)

		# At least 2 messages required to build meaningful summary
		if len(messages_to_process) <= 1:
			logger.debug('Not enough non-memory messages to summarise')
			return

		memory_content = self._create([m.message for m in messages_to_process], current_step)

		if not memory_content:
			logger.warning('Failed to create procedural memory')
			return

		# Replace processed window with single memory blob
		memory_msg = HumanMessage(content=memory_content)
		memory_tokens = self.message_manager._count_tokens(memory_msg)  # pylint: disable=protected-access
		from app_use.agent.message_manager.views import (
			MessageMetadata,
		)  # local import to avoid cycles

		# compute removed tokens
		removed_tokens = sum(m.metadata.tokens for m in messages_to_process)

		# push memory message
		new_messages.append(
			type(messages_to_process[0])(  # ManagedMessage class
				message=memory_msg,
				metadata=MessageMetadata(tokens=memory_tokens, message_type='memory'),
			)
		)

		# Update manager state
		hist = self.message_manager.state.history
		hist.messages = new_messages
		hist.current_tokens = hist.current_tokens - removed_tokens + memory_tokens
		logger.info(
			'Messages consolidated: %s messages converted to procedural memory',
			len(messages_to_process),
		)

	# ------------------------------------------------------------------
	# Internal helpers --------------------------------------------------
	# ------------------------------------------------------------------
	def _create(self, messages: list[BaseMessage], current_step: int) -> str | None:
		"""Invoke Mem0 to create a procedural memory summary."""
		parsed = convert_to_openai_messages(messages)
		try:
			results = self.mem0.add(
				messages=parsed,
				agent_id=self.config.agent_id,
				memory_type='procedural_memory',
				metadata={'step': current_step},
			)
			if results.get('results'):
				return results['results'][0].get('memory')
			return None
		except Exception as exc:  # pragma: no cover
			logger.error('Error creating procedural memory: %s', exc)
			return None
