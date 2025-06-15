import logging
from typing import (
	Callable,
	Generic,
	List,
	Optional,
	TypeVar,
)

from pydantic import BaseModel, create_model

from app_use.app.app import App
from app_use.controller.registry.service import Registry
from app_use.controller.views import (
	ActionModel,
	ActionResult,
	ClickElementAction,
	DoneAction,
	DragAndDropCoordinatesAction,
	EnterTextAction,
	GetAppStateAction,
	GetDropdownOptionsAction,
	LongPressCoordinatesAction,
	PinchGestureAction,
	ScrollAction,
	ScrollIntoViewAction,
	SelectDropdownOptionAction,
	SendKeysAction,
	SwipeCoordinatesAction,
)
from app_use.utils import time_execution_sync

logger = logging.getLogger(__name__)

Context = TypeVar('Context')


class Controller(Generic[Context]):
	"""
	Controller class that manages actions and their execution.

	This class registers standard actions and provides a way to
	execute them against an App instance.
	"""

	def __init__(
		self,
		exclude_actions: Optional[List[str]] = None,
		output_model: Optional[type[BaseModel]] = None,
	):
		"""
		Initialize the controller.

		Args:
		    exclude_actions: List of action names to exclude from registration
		    output_model: Optional output model type for done action
		"""
		self.registry = Registry[Context](exclude_actions)

		self._register_actions(output_model)

	def _register_actions(self, output_model: Optional[type[BaseModel]] = None) -> None:
		"""Register all default app actions.

		Args:
		    output_model: Optional output model type for done action
		"""
		if output_model is not None:
			# Create the ExtendedOutputModel dynamically using create_model
			ExtendedOutputModel = create_model('ExtendedOutputModel', success=(bool, True), data=(output_model, ...))

			@self.registry.action(
				'Complete task - with return text and if the task is finished (success=True) or not yet completely finished (success=False)',
				param_model=ExtendedOutputModel,
			)
			async def done(params) -> ActionResult:
				try:
					output_dict = params.data.model_dump()
					return ActionResult(
						is_done=True,
						success=params.success,
						extracted_content=str(output_dict),
						include_in_memory=True,
					)
				except Exception as e:
					logger.error(f'Error in done action: {str(e)}')
					return ActionResult(
						is_done=True,
						success=False,
						error=f'Error in done action: {str(e)}',
						include_in_memory=True,
					)
		else:

			@self.registry.action(
				'Complete task - with return text and if the task is finished (success=True) or not yet completely finished (success=False)',
				param_model=DoneAction,
			)
			async def done(params: DoneAction) -> ActionResult:
				try:
					return ActionResult(
						is_done=True,
						success=params.success,
						extracted_content=params.text,
						include_in_memory=True,
					)
				except Exception as e:
					logger.error(f'Error in done action: {str(e)}')
					return ActionResult(
						is_done=True,
						success=False,
						error=f'Error in done action: {str(e)}',
						include_in_memory=True,
					)

		@self.registry.action(
			'Click an element by its index - DO NOT use this for text input fields, use enter_text instead',
			param_model=ClickElementAction,
		)
		async def click_element(params: ClickElementAction, app: App) -> ActionResult:
			try:
				success = app.click_element_by_highlight_index(params.index)  # index represents highlight_index

				if success:
					msg = f'🖱️ Clicked element with highlight index {params.index}'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = f'Failed to click element with highlight index {params.index}'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in click_element: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in click_element: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Input text into an interactive element by its index',
			param_model=EnterTextAction,
		)
		async def enter_text(params: EnterTextAction, app: App) -> ActionResult:
			try:
				if params.index is None:
					return ActionResult(
						success=False,
						error='Missing required index',
						include_in_memory=True,
					)
				if params.text is None:
					return ActionResult(
						success=False,
						error='Missing required text',
						include_in_memory=True,
					)

				selector_map = app.get_selector_map()
				if params.index not in selector_map:
					return ActionResult(
						success=False,
						error=f'Element with highlight index {params.index} not found',
						include_in_memory=True,
					)

				success = app.enter_text_with_highlight_index(params.index, params.text)  # index represents highlight_index

				if success:
					msg = f"⌨️ Entered text '{params.text}' into element with highlight index {params.index}"
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = f'Failed to enter text into element with highlight index {params.index}'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in enter_text: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in enter_text: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'If you dont find something which you want to interact with, scroll to it',
			param_model=ScrollIntoViewAction,
		)
		async def scroll_into_view(params: ScrollIntoViewAction, app: App) -> ActionResult:
			try:
				if params.index is None:
					return ActionResult(
						success=False,
						error='Missing required highlight_index',
						include_in_memory=True,
					)

				selector_map = app.get_selector_map()

				if params.index not in selector_map:
					return ActionResult(
						success=False,
						error=f'Element with highlight index {params.index} not found',
						include_in_memory=True,
					)

				success = app.scroll_into_view_by_highlight_index(params.index)  # index represents highlight_index

				if success:
					msg = f'🔍 Scrolled element with highlight index {params.index} into view'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = f'Failed to scroll element with highlight index {params.index} into view'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in scroll_into_view: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in scroll_into_view: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Scroll down the page by pixel amount - if none is given, scroll one page',
			param_model=ScrollAction,
		)
		async def scroll_down(params: ScrollAction, app: App) -> ActionResult:
			try:
				# Get screen dimensions to calculate one page scroll
				size = app.driver.get_window_size()
				scroll_amount = params.amount or size['height'] // 2  # Half screen height as "one page"

				success = app.scroll_by_amount(scroll_amount, direction='down')

				if success:
					amount_str = f'{params.amount} pixels' if params.amount is not None else 'one page'
					msg = f'🔍 Scrolled down the page by {amount_str}'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = 'Failed to scroll down'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in scroll_down: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in scroll_down: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Scroll up the page by pixel amount - if none is given, scroll one page',
			param_model=ScrollAction,
		)
		async def scroll_up(params: ScrollAction, app: App) -> ActionResult:
			try:
				# Get screen dimensions to calculate one page scroll
				size = app.driver.get_window_size()
				scroll_amount = params.amount or size['height'] // 2  # Half screen height as "one page"

				success = app.scroll_by_amount(scroll_amount, direction='up')

				if success:
					amount_str = f'{params.amount} pixels' if params.amount is not None else 'one page'
					msg = f'🔍 Scrolled up the page by {amount_str}'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = 'Failed to scroll up'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in scroll_up: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in scroll_up: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Get the current application state with all nodes',
			param_model=GetAppStateAction,
		)
		async def get_app_state(params: GetAppStateAction, app: App) -> ActionResult:
			try:
				app_state = app.get_app_state()

				node_info = []
				for highlight_index, node in app_state.selector_map.items():
					info = {
						'highlight_index': highlight_index,  # Use highlight_index as primary identifier
						'tag_name': getattr(node, 'tag_name', 'TextNode') if hasattr(node, 'tag_name') else 'TextNode',
						'is_interactive': getattr(node, 'is_interactive', False) if hasattr(node, 'is_interactive') else False,
						'text': node.text if hasattr(node, 'text') else None,
						'key': getattr(node, 'key', None) if hasattr(node, 'key') else None,
						'parent_highlight_index': node.parent.highlight_index
						if node.parent and hasattr(node.parent, 'highlight_index')
						else None,
					}
					node_info.append(info)

				msg = f'Retrieved app state with {len(app_state.selector_map)} nodes:\n{str(node_info)}'
				return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in get_app_state: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in get_app_state: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Send keyboard keys (Enter, Delete, Backspace, etc.) - useful for mobile navigation and completing text input',
			param_model=SendKeysAction,
		)
		async def send_keys(params: SendKeysAction, app: App) -> ActionResult:
			try:
				success = app.send_keys(params.keys)

				if success:
					msg = f'⌨️ Sent keys: {params.keys}'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = f'Failed to send keys: {params.keys}'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in send_keys: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in send_keys: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Perform a swipe gesture from start coordinates to end coordinates',
			param_model=SwipeCoordinatesAction,
		)
		async def swipe_coordinates(params: SwipeCoordinatesAction, app: App) -> ActionResult:
			try:
				success = app.swipe_coordinates(
					params.start_x,
					params.start_y,
					params.end_x,
					params.end_y,
					params.duration,
				)

				if success:
					msg = f'👆 Swiped from ({params.start_x}, {params.start_y}) to ({params.end_x}, {params.end_y})'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = f'Failed to swipe from ({params.start_x}, {params.start_y}) to ({params.end_x}, {params.end_y})'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except NotImplementedError as e:
				return ActionResult(success=False, error=str(e), include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in swipe_coordinates: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in swipe_coordinates: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Perform a pinch gesture (pinch in/out) at specified coordinates',
			param_model=PinchGestureAction,
		)
		async def pinch_gesture(params: PinchGestureAction, app: App) -> ActionResult:
			try:
				success = app.pinch_gesture(params.center_x, params.center_y, params.percent)

				if success:
					gesture_type = 'pinch in' if params.percent < 50 else 'pinch out'
					msg = f'🤏 Performed {gesture_type} gesture at ({params.center_x}, {params.center_y}) with {params.percent}% intensity'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = f'Failed to perform pinch gesture at ({params.center_x}, {params.center_y})'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except NotImplementedError as e:
				return ActionResult(success=False, error=str(e), include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in pinch_gesture: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in pinch_gesture: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Perform a long press gesture at specific coordinates',
			param_model=LongPressCoordinatesAction,
		)
		async def long_press_coordinates(params: LongPressCoordinatesAction, app: App) -> ActionResult:
			try:
				success = app.long_press_coordinates(params.x, params.y, params.duration)

				if success:
					msg = f'👆 Performed long press at ({params.x}, {params.y}) for {params.duration}ms'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = f'Failed to perform long press at ({params.x}, {params.y})'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except NotImplementedError as e:
				return ActionResult(success=False, error=str(e), include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in long_press_coordinates: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in long_press_coordinates: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Perform a drag and drop gesture from start coordinates to end coordinates',
			param_model=DragAndDropCoordinatesAction,
		)
		async def drag_and_drop_coordinates(params: DragAndDropCoordinatesAction, app: App) -> ActionResult:
			try:
				success = app.drag_and_drop_coordinates(
					params.start_x,
					params.start_y,
					params.end_x,
					params.end_y,
					params.duration,
				)

				if success:
					msg = f'🖱️ Dragged from ({params.start_x}, {params.start_y}) to ({params.end_x}, {params.end_y})'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
				else:
					error_msg = f'Failed to drag from ({params.start_x}, {params.start_y}) to ({params.end_x}, {params.end_y})'
					return ActionResult(success=False, error=error_msg, include_in_memory=True)
			except NotImplementedError as e:
				return ActionResult(success=False, error=str(e), include_in_memory=True)
			except Exception as e:
				logger.error(f'Error in drag_and_drop_coordinates: {str(e)}')
				return ActionResult(
					success=False,
					error=f'Exception in drag_and_drop_coordinates: {str(e)}',
					include_in_memory=True,
				)

		@self.registry.action(
			'Get all options from a dropdown element by its index',
			param_model=GetDropdownOptionsAction,
		)
		async def get_dropdown_options(params: GetDropdownOptionsAction, app: App) -> ActionResult:
			try:
				# Retrieve current UI state
				app_state = app.get_app_state()
				target_node = app_state.selector_map.get(params.index)
				if not target_node:
					return ActionResult(
						success=False,
						error=f'No element found with index {params.index}',
						include_in_memory=True,
					)

				# Ensure element is a dropdown (Spinner on Android, XCUIElementTypePickerWheel on iOS)
				expected_types = [
					'android.widget.Spinner',
					'XCUIElementTypePickerWheel',
				]
				if target_node.tag_name not in expected_types:
					return ActionResult(
						success=False,
						error=f'Element {params.index} is not a dropdown (type={target_node.tag_name})',
						include_in_memory=True,
					)

				# Scroll into view if needed
				app.scroll_into_view_by_highlight_index(params.index)  # index represents highlight_index

				# Gather option texts using native commands
				options_text: list[str] = []
				if app.platform_name.lower() == 'android':
					element = app.driver.find_element('xpath', app._build_xpath_for_node(target_node))
					option_elements = element.find_elements_by_xpath('//android.widget.CheckedTextView')
					options_text = [opt.text for opt in option_elements if opt.text is not None]
				else:
					# iOS picker wheels expose values via attribute 'values'
					element = app.driver.find_element('xpath', app._build_xpath_for_node(target_node))
					values = element.get_attribute('values')
					if isinstance(values, list):
						options_text = values

				if not options_text:
					msg = 'No options found in dropdown'
					return ActionResult(success=True, extracted_content=msg, include_in_memory=True)

				formatted = [f'{idx}: {text}' for idx, text in enumerate(options_text)]
				msg = '\n'.join(formatted)
				msg += '\nUse the exact text string in select_dropdown_option'
				return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
			except Exception as e:
				logger.error(f'Error getting dropdown options: {str(e)}')
				return ActionResult(success=False, error=str(e), include_in_memory=True)

		@self.registry.action(
			'Select dropdown option for element by the text of the option',
			param_model=SelectDropdownOptionAction,
		)
		async def select_dropdown_option(params: SelectDropdownOptionAction, app: App) -> ActionResult:
			try:
				selector_map = app.get_selector_map()
				target_node = selector_map.get(params.index)
				if not target_node:
					return ActionResult(
						success=False,
						error=f'No element found with index {params.index}',
						include_in_memory=True,
					)

				expected_types = [
					'android.widget.Spinner',
					'XCUIElementTypePickerWheel',
				]
				if target_node.tag_name not in expected_types:
					return ActionResult(
						success=False,
						error=f'Element {params.index} is not a dropdown (type={target_node.tag_name})',
						include_in_memory=True,
					)

				app.scroll_into_view_by_highlight_index(params.index)  # index represents highlight_index

				if app.platform_name.lower() == 'android':
					element = app.driver.find_element('xpath', app._build_xpath_for_node(target_node))
					element.click()
					# After opening spinner, find element by text and click
					option_xpath = f"//android.widget.CheckedTextView[@text='{params.text}']"
					option_el = app.driver.find_element('xpath', option_xpath)
					option_el.click()
				else:
					element = app.driver.find_element('xpath', app._build_xpath_for_node(target_node))
					element.send_keys(params.text)

				msg = f"Selected option '{params.text}' in dropdown {params.index}"
				return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
			except Exception as e:
				logger.error(f'Error selecting dropdown option: {str(e)}')
				return ActionResult(success=False, error=str(e), include_in_memory=True)

	def action(self, description: str, **kwargs) -> Callable:
		"""
		Decorator for registering custom actions

		Args:
		    description: Description of the action
		    **kwargs: Additional arguments to pass to the registry

		Returns:
		    Decorator function for registering actions
		"""
		return self.registry.action(description, **kwargs)

	@time_execution_sync('--act')
	async def act(
		self,
		action: ActionModel,
		app: App,
		context: Optional[Context] = None,
	) -> ActionResult:
		"""
		Execute an action

		Args:
		    action: The action model to execute
		    app: The app instance to execute the action against
		    context: Optional context for the action

		Returns:
		    ActionResult containing the result of the action
		"""
		try:
			result = None
			for action_name, params in action.model_dump(exclude_unset=True).items():
				if params is not None:
					result = await self.registry.execute_action(
						action_name,
						params,
						app=app,
						context=context,
					)

			if isinstance(result, str):
				return ActionResult(success=True, extracted_content=result, include_in_memory=True)
			elif isinstance(result, ActionResult):
				return result
			elif result is None:
				return ActionResult(success=True, include_in_memory=True)
			else:
				error_msg = f'Invalid action result type: {type(result)} of {result}'
				logger.error(error_msg)
				return ActionResult(success=False, error=error_msg, include_in_memory=True)
		except Exception as e:
			error_msg = f'Error executing action: {str(e)}'
			logger.error(error_msg)
			return ActionResult(success=False, error=error_msg, include_in_memory=True)
