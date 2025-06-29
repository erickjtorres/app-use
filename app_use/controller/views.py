from pydantic import BaseModel, ConfigDict, model_validator


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
	"""Action model for retrieving all options from a dropdown element by its index"""

	index: int  # Keep name for compatibility but represents highlight_index


class SelectDropdownOptionAction(BaseModel):
	"""Action model for selecting an option in a dropdown by its text"""

	index: int  # Keep name for compatibility but represents highlight_index
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
