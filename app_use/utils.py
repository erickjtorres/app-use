import logging
import time
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger(__name__)
R = TypeVar('R')
P = ParamSpec('P')
# Import error types - these may need to be adjusted based on actual import paths
try:
	from openai import BadRequestError as OpenAIBadRequestError
except ImportError:
	OpenAIBadRequestError = None


def time_execution_sync(additional_text: str = '') -> Callable[[Callable[P, R]], Callable[P, R]]:
	def decorator(func: Callable[P, R]) -> Callable[P, R]:
		@wraps(func)
		def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
			start_time = time.time()
			result = func(*args, **kwargs)
			execution_time = time.time() - start_time
			# Only log if execution takes more than 0.25 seconds
			if execution_time > 0.25:
				logger.debug(f'⏳ {additional_text.strip("-")}() took {execution_time:.2f}s')
			return result

		return wrapper

	return decorator


class LLMException(Exception):
	"""Custom exception for LLM-related errors."""

	def __init__(self, code: int, message: str):
		self.code = code
		self.message = message
		super().__init__(message)


def handle_llm_error(e: Exception) -> tuple[dict[str, Any], Any | None]:
	"""
	Handle LLM API errors and extract failed generation data when available.

	Args:
		e: The exception that occurred during LLM API call

	Returns:
		Tuple containing:
		- response: Dict with 'raw' and 'parsed' keys
		- parsed: Parsed data (None if extraction was needed)

	Raises:
		LLMException: If the error is not a recognized type with failed generation data
	"""
	# Handle OpenAI BadRequestError with failed_generation
	if (
		OpenAIBadRequestError
		and isinstance(e, OpenAIBadRequestError)
		and hasattr(e, 'body')
		and e.body  # type: ignore[attr-defined]
		and 'failed_generation' in e.body  # type: ignore[operator]
	):
		raw = e.body['failed_generation']  # type: ignore[index]
		response = {'raw': raw, 'parsed': None}
		parsed = None
		logger.debug(f'Failed to do tool call, trying to parse raw response: {raw}')
		return response, parsed

	# If it's not a recognized error type, log and raise
	logger.error(f'Failed to invoke model: {str(e)}')
	raise LLMException(401, 'LLM API call failed' + str(e)) from e


def time_execution_async(
	additional_text: str = '',
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
	def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
		@wraps(func)
		async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
			start_time = time.time()
			result = await func(*args, **kwargs)
			execution_time = time.time() - start_time
			# Only log if execution takes more than 0.25 seconds to avoid spamming the logs
			# you can lower this threshold locally when you're doing dev work to performance optimize stuff
			if execution_time > 0.25:
				logger.debug(f'⏳ {additional_text.strip("-")}() took {execution_time:.2f}s')
			return result

		return wrapper

	return decorator
