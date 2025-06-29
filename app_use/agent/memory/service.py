from __future__ import annotations

from app_use.agent.message_manager.views import ManagedMessage

"""Procedural memory service for *app-use* agents."""

import logging
import os
import tempfile
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor, TimeoutError

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
		use_mem0_client: bool = False,
	) -> None:
		self.message_manager = message_manager
		self.llm = llm
		self.logger = logger
		self.use_mem0_client = use_mem0_client

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
			from mem0 import Memory as Mem0Memory
			from mem0 import MemoryClient  # pylint: disable=import-error
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

		if self.use_mem0_client:
			self.mem0 = MemoryClient()
		else:
			# Initialize Mem0 with the configuration
			with warnings.catch_warnings():
				warnings.filterwarnings('ignore', category=DeprecationWarning)
				try:
					self.mem0 = Mem0Memory.from_config(config_dict=self.config.full_config_dict)
				except Exception as e:
					if 'history_old' in str(e) and 'sqlite3.OperationalError' in str(type(e)):
						# Handle the migration error by using a unique history database path
						self.logger.warning(
							f'⚠️ Mem0 SQLite migration error detected in {self.config.full_config_dict}. Using a temporary database to avoid conflicts.\n{type(e).__name__}: {e}'
						)
						# Create a unique temporary database path
						temp_dir = tempfile.gettempdir()
						unique_id = str(uuid.uuid4())[:8]
						history_db_path = os.path.join(temp_dir, f'app_use_mem0_history_{unique_id}.db')

						# Add the history_db_path to the config
						config_with_history_path = self.config.full_config_dict.copy()
						config_with_history_path['history_db_path'] = history_db_path

						# Try again with the new config
						self.mem0 = Mem0Memory.from_config(config_dict=config_with_history_path)
					else:
						# Re-raise if it's a different error
						raise

	# ------------------------------------------------------------------
	# Public API --------------------------------------------------------
	# ------------------------------------------------------------------
	@time_execution_sync('--create_procedural_memory')
	def create_procedural_memory(self, current_step: int) -> None:
		"""Create and insert procedural memory into chat history if needed.

		Args:
		    current_step: The current step number of the agent
		"""
		self.logger.debug(f'📱 Creating procedural memory at step {current_step}')

		all_messages = self.message_manager.state.history.messages
		new_messages: list[ManagedMessage] = []  # maintain same ManagedMessage type
		messages_to_process: list[ManagedMessage] = []

		for msg in all_messages:
			if isinstance(msg, ManagedMessage) and msg.metadata.message_type in {
				'init',
				'memory',
			}:
				# Keep system and memory messages as they are
				new_messages.append(msg)
			else:
				if len(msg.message.content) > 0:
					messages_to_process.append(msg)
		# At least 2 messages required to build meaningful summary
		if len(messages_to_process) <= 1:
			self.logger.debug('📱 Not enough non-memory messages to summarise')
			return

		# Create a procedural memory with timeout
		try:
			with ThreadPoolExecutor(max_workers=1) as executor:
				future = executor.submit(self._create, [m.message for m in messages_to_process], current_step)
				memory_content = future.result(timeout=30)
		except TimeoutError:
			self.logger.warning('📱 Procedural memory creation timed out after 30 seconds')
			return
		except Exception as e:
			self.logger.error(f'📱 Error during procedural memory creation: {e}')
			return

		if not memory_content:
			self.logger.warning('📱 Failed to create procedural memory: ' + str(messages_to_process))
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
			ManagedMessage(  # ManagedMessage class
				message=memory_msg,
				metadata=MessageMetadata(tokens=memory_tokens, message_type='memory'),
			)
		)

		# Update manager state
		self.message_manager.state.history.messages = new_messages
		self.message_manager.state.history.current_tokens -= removed_tokens
		self.message_manager.state.history.current_tokens += memory_tokens
		self.logger.info(f'📜 History consolidated: {len(messages_to_process)} steps converted to long-term memory')

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
			if len(results.get('results', [])):
				return results.get('results', [])[0].get('memory')
			return None
		except Exception as exc:  # pragma: no cover
			self.logger.error(f'📱 Error creating procedural memory: {exc}')
			return None
