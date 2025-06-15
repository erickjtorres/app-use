from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, model_validator


# Action Input Models
class ActionModel(BaseModel):
	"""Base model for dynamically created action models"""

	model_config = ConfigDict(arbitrary_types_allowed=True)

	def get_index(self) -> int | None:
		"""Get the index of the action if it exists"""
		params = self.model_dump(exclude_unset=True).values()
		if not params:
			return None
		for param in params:
			if param is not None and 'index' in param:
				return param['index']
		return None

	def set_index(self, index: int):
		"""Overwrite the index of the action"""
		action_data = self.model_dump(exclude_unset=True)
		action_name = next(iter(action_data.keys()))
		action_params = getattr(self, action_name)

		if hasattr(action_params, 'index'):
			action_params.index = index


class RegisteredAction(BaseModel):
	"""Model for a registered action"""

	name: str
	description: str
	function: Callable
	param_model: type[BaseModel]

	model_config = ConfigDict(arbitrary_types_allowed=True)

	def prompt_description(self) -> str:
		"""Get a description of the action for the prompt"""
		skip_keys = ['title']
		s = f'{self.description}: \n'
		s += '{' + str(self.name) + ': '
		s += str(
			{
				k: {sub_k: sub_v for sub_k, sub_v in v.items() if sub_k not in skip_keys}
				for k, v in self.param_model.model_json_schema()['properties'].items()
			}
		)
		s += '}'
		return s


class ActionRegistry(BaseModel):
	"""Model representing the action registry"""

	actions: dict[str, RegisteredAction] = {}

	def get_prompt_description(self) -> str:
		"""Get a description of all actions for the prompt"""
		return '\n'.join(action.prompt_description() for action in self.actions.values())


class ActionResult(BaseModel):
	"""Result of an action execution"""

	is_done: bool = False
	success: bool = True
	error: str | None = None
	extracted_content: str | None = None
	include_in_memory: bool = False


class ClickElementAction(BaseModel):
	"""Action model for clicking a element by its highlight index"""

	index: int  # Keep name for compatibility but represents highlight_index


class EnterTextAction(BaseModel):
	"""Action model for entering text into a element by its highlight index"""

	index: int  # Keep name for compatibility but represents highlight_index
	text: str


class ScrollIntoViewAction(BaseModel):
	"""Action model for scrolling a element into view by its highlight index"""

	index: int  # Keep name for compatibility but represents highlight_index


class ScrollAction(BaseModel):
	"""Action model for scrolling by pixel amount"""

	amount: int | None = None  # The number of pixels to scroll. If None, scroll one page


class GetAppStateAction(BaseModel):
	"""Action model for getting the current application state"""

	model_config = ConfigDict(extra='allow')

	@model_validator(mode='before')
	def ignore_all_inputs(cls, values):
		return {}


class DoneAction(BaseModel):
	"""Action model for completing a task with a result"""

	text: str
	success: bool = True


class SwipeCoordinatesAction(BaseModel):
	"""Action model for performing a swipe gesture between coordinates"""

	start_x: int
	start_y: int
	end_x: int
	end_y: int
	duration: int = 300


class PinchGestureAction(BaseModel):
	"""Action model for performing a pinch gesture"""

	center_x: int = None
	center_y: int = None
	percent: int = 50


class LongPressCoordinatesAction(BaseModel):
	"""Action model for performing a long press at coordinates"""

	x: int
	y: int
	duration: int = 1000


class DragAndDropCoordinatesAction(BaseModel):
	"""Action model for performing a drag and drop gesture between coordinates"""

	start_x: int
	start_y: int
	end_x: int
	end_y: int
	duration: int = 1000


class GetDropdownOptionsAction(BaseModel):
	"""Action model for retrieving all options from a dropdown element by its unique ID"""

	unique_id: int  # Keep name for compatibility but represents highlight_index


class SelectDropdownOptionAction(BaseModel):
	"""Action model for selecting an option in a dropdown by its text"""

	unique_id: int  # Keep name for compatibility but represents highlight_index
	text: str


class SendKeysAction(BaseModel):
	"""Action model for sending keyboard keys (Enter, Back, etc.)"""

	keys: str


# Helper model for models that require no parameters
class NoParamsAction(BaseModel):
	"""
	Accepts absolutely anything in the incoming data
	and discards it, so the final parsed model is empty.
	"""

	model_config = ConfigDict(extra='allow')

	@model_validator(mode='before')
	def ignore_all_inputs(cls, values):
		return {}
