import asyncio
import logging
from typing import Generic, TypeVar, Any, List, Dict, Optional, Union, Callable, Awaitable

from pydantic import BaseModel, Field, ValidationError

from app_use.controller.registry.service import Registry
from app_use.controller.views import (
    ActionModel, 
    ActionResult, 
    DoneAction,
    ClickWidgetAction,
    EnterTextAction,
    ScrollIntoViewAction,
    ScrollUpOrDownAction,
    ScrollExtendedAction,
    FindScrollableAncestorAction,
    FindScrollableDescendantAction,
    GetAppStateAction
)
from app_use.nodes.app_node import AppElementNode, NodeState, AppBaseNode
from app_use.app.flutter_app import App

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
            class ExtendedOutputModel(BaseModel):
                success: bool = True
                data: output_model

            @self.registry.action(
                'Complete task - with return text and if the task is finished (success=True) or not yet completely finished (success=False)',
                param_model=ExtendedOutputModel,
            )
            async def done(params: ExtendedOutputModel) -> ActionResult:
                try:
                    output_dict = params.data.model_dump()
                    return ActionResult(is_done=True, success=params.success, extracted_content=str(output_dict), include_in_memory=True)
                except Exception as e:
                    logger.error(f"Error in done action: {str(e)}")
                    return ActionResult(is_done=True, success=False, error=f"Error in done action: {str(e)}", include_in_memory=True)
        else:
            @self.registry.action(
                'Complete task - with return text and if the task is finished (success=True) or not yet completely finished (success=False)',
                param_model=DoneAction,
            )
            async def done(params: DoneAction) -> ActionResult:
                try:
                    return ActionResult(is_done=True, success=params.success, extracted_content=params.text, include_in_memory=True)
                except Exception as e:
                    logger.error(f"Error in done action: {str(e)}")
                    return ActionResult(is_done=True, success=False, error=f"Error in done action: {str(e)}", include_in_memory=True)

        @self.registry.action(
            'Click a widget element by its unique ID - DO NOT use this for text input fields, use enter_text instead',
            param_model=ClickWidgetAction,
        )
        async def click_widget(params: ClickWidgetAction, app: App) -> ActionResult:
            try:
                if params.unique_id is None:
                    return ActionResult(success=False, error="Missing required unique_id", include_in_memory=True)
                
                node_state = app.get_app_state()
                
                success = app.click_widget_by_unique_id(node_state, params.unique_id)
                
                if success:
                    msg = f"🖱️ Clicked widget with unique ID {params.unique_id}"
                    return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
                else:
                    error_msg = f"Failed to click widget with unique ID {params.unique_id}"
                    return ActionResult(success=False, error=error_msg, include_in_memory=True)
            except Exception as e:
                logger.error(f"Error in click_widget: {str(e)}")
                return ActionResult(success=False, error=f"Exception in click_widget: {str(e)}", include_in_memory=True)

        @self.registry.action(
            'Enter text into a widget element by its unique ID',
            param_model=EnterTextAction,
        )
        async def enter_text(params: EnterTextAction, app: App) -> ActionResult:
            try:
                if params.unique_id is None:
                    return ActionResult(success=False, error="Missing required unique_id", include_in_memory=True)
                if params.text is None:
                    return ActionResult(success=False, error="Missing required text", include_in_memory=True)
                
                node_state = app.get_app_state()
                
                if params.unique_id not in node_state.selector_map:
                    return ActionResult(success=False, error=f"Widget with unique ID {params.unique_id} not found", include_in_memory=True)
                
                success = app.enter_text_with_unique_id(node_state, params.unique_id, params.text)
                
                if success:
                    msg = f"⌨️ Entered text '{params.text}' into widget with unique ID {params.unique_id}"
                    return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
                else:
                    error_msg = f"Failed to enter text into widget with unique ID {params.unique_id}"
                    return ActionResult(success=False, error=error_msg, include_in_memory=True)
            except Exception as e:
                logger.error(f"Error in enter_text: {str(e)}")
                return ActionResult(success=False, error=f"Exception in enter_text: {str(e)}", include_in_memory=True)

        @self.registry.action(
            'Scroll a widget into view by its unique ID',
            param_model=ScrollIntoViewAction,
        )
        async def scroll_into_view(params: ScrollIntoViewAction, app: App) -> ActionResult:
            try:
                if params.unique_id is None:
                    return ActionResult(success=False, error="Missing required unique_id", include_in_memory=True)
                
                node_state = app.get_app_state()
                
                if params.unique_id not in node_state.selector_map:
                    return ActionResult(success=False, error=f"Widget with unique ID {params.unique_id} not found", include_in_memory=True)
                
                success = app.scroll_into_view(node_state, params.unique_id)
                
                if success:
                    msg = f"🔍 Scrolled widget with unique ID {params.unique_id} into view"
                    return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
                else:
                    error_msg = f"Failed to scroll widget with unique ID {params.unique_id} into view"
                    return ActionResult(success=False, error=error_msg, include_in_memory=True)
            except Exception as e:
                logger.error(f"Error in scroll_into_view: {str(e)}")
                return ActionResult(success=False, error=f"Exception in scroll_into_view: {str(e)}", include_in_memory=True)

        @self.registry.action(
            'Scroll a widget up or down',
            param_model=ScrollUpOrDownAction,
        )
        async def scroll_up_or_down(params: ScrollUpOrDownAction, app: App) -> ActionResult:
            try:
                if params.unique_id is None:
                    return ActionResult(success=False, error="Missing required unique_id", include_in_memory=True)
                
                if params.direction not in ["up", "down"]:
                    return ActionResult(success=False, error=f"Invalid scroll direction: {params.direction}. Must be 'up' or 'down'.", include_in_memory=True)
                
                node_state = app.get_app_state()
                
                if params.unique_id not in node_state.selector_map:
                    return ActionResult(success=False, error=f"Widget with unique ID {params.unique_id} not found", include_in_memory=True)
                
                success = app.scroll_up_or_down(node_state, params.unique_id, params.direction)
                
                if success:
                    msg = f"🔍 Scrolled {params.direction} with widget unique ID {params.unique_id}"
                    return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
                else:
                    error_msg = f"Failed to scroll {params.direction} with widget unique ID {params.unique_id}"
                    return ActionResult(success=False, error=error_msg, include_in_memory=True)
            except Exception as e:
                logger.error(f"Error in scroll_up_or_down: {str(e)}")
                return ActionResult(success=False, error=f"Exception in scroll_up_or_down: {str(e)}", include_in_memory=True)

        @self.registry.action(
            'Perform an extended scroll with more parameters on a widget',
            param_model=ScrollExtendedAction,
        )
        async def scroll_extended(params: ScrollExtendedAction, app: App) -> ActionResult:
            try:
                if params.unique_id is None:
                    return ActionResult(success=False, error="Missing required unique_id", include_in_memory=True)
                
                if params.direction not in ["up", "down"]:
                    return ActionResult(success=False, error=f"Invalid scroll direction: {params.direction}. Must be 'up' or 'down'.", include_in_memory=True)
                
                node_state = app.get_app_state()
                
                if params.unique_id not in node_state.selector_map:
                    return ActionResult(success=False, error=f"Widget with unique ID {params.unique_id} not found", include_in_memory=True)
                
                success = app.scroll_up_or_down_extended(
                    node_state, 
                    params.unique_id, 
                    params.direction, 
                    params.dx, 
                    params.dy, 
                    params.duration_microseconds,
                    params.frequency
                )
                
                if success:
                    msg = f"🔍 Performed extended {params.direction} scroll on widget {params.unique_id} with parameters: dx={params.dx}, dy={params.dy}"
                    return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
                else:
                    error_msg = f"Failed to perform extended {params.direction} scroll on widget {params.unique_id}"
                    return ActionResult(success=False, error=error_msg, include_in_memory=True)
            except Exception as e:
                logger.error(f"Error in scroll_extended: {str(e)}")
                return ActionResult(success=False, error=f"Exception in scroll_extended: {str(e)}", include_in_memory=True)

        @self.registry.action(
            'Find the closest scrollable ancestor of a widget',
            param_model=FindScrollableAncestorAction,
        )
        async def find_scrollable_ancestor(params: FindScrollableAncestorAction, app: App) -> ActionResult:
            try:
                if params.unique_id is None:
                    return ActionResult(success=False, error="Missing required unique_id", include_in_memory=True)
                
                node_state = app.get_app_state()
                
                target_node = node_state.selector_map.get(params.unique_id)
                        
                if not target_node:
                    return ActionResult(success=False, error=f"No widget found with unique_id: {params.unique_id}", include_in_memory=True)
                
                try:
                    scrollable_ancestor = app.find_ancestor_with_scroll(target_node)
                
                    if scrollable_ancestor:
                        msg = f"Found scrollable ancestor with unique ID {scrollable_ancestor.unique_id} and type {scrollable_ancestor.node_type}"
                        return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
                    else:
                        msg = f"No scrollable ancestor found for widget with unique ID {params.unique_id}"
                        return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
                except AttributeError:
                    return ActionResult(
                        success=False, 
                        error="This app implementation does not support finding scrollable ancestors", 
                        include_in_memory=True
                    )
            except Exception as e:
                logger.error(f"Error in find_scrollable_ancestor: {str(e)}")
                return ActionResult(success=False, error=f"Exception in find_scrollable_ancestor: {str(e)}", include_in_memory=True)
                
        @self.registry.action(
            'Find the first scrollable descendant of a widget',
            param_model=FindScrollableDescendantAction,
        )
        async def find_scrollable_descendant(params: FindScrollableDescendantAction, app: App) -> ActionResult:
            try:
                if params.unique_id is None:
                    return ActionResult(success=False, error="Missing required unique_id", include_in_memory=True)
                
                node_state = app.get_app_state()
                
                target_node = node_state.selector_map.get(params.unique_id)
                        
                if not target_node:
                    return ActionResult(success=False, error=f"No widget found with unique_id: {params.unique_id}", include_in_memory=True)
                
                try:
                    scrollable_descendant = app.find_descendant_with_scroll(target_node)
                
                    if scrollable_descendant:
                        msg = f"Found scrollable descendant with unique ID {scrollable_descendant.unique_id} and type {scrollable_descendant.node_type}"
                        return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
                    else:
                        msg = f"No scrollable descendant found for widget with unique ID {params.unique_id}"
                        return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
                except AttributeError:
                    return ActionResult(
                        success=False, 
                        error="This app implementation does not support finding scrollable descendants", 
                        include_in_memory=True
                    )
            except Exception as e:
                logger.error(f"Error in find_scrollable_descendant: {str(e)}")
                return ActionResult(success=False, error=f"Exception in find_scrollable_descendant: {str(e)}", include_in_memory=True)

        @self.registry.action(
            'Get the current application state with all widget nodes',
            param_model=GetAppStateAction,
        )
        async def get_app_state(params: GetAppStateAction, app: App) -> ActionResult:
            try:
                node_state = app.get_app_state()
                
                node_info = []
                for uid, node in node_state.selector_map.items():
                    info = {
                        "unique_id": node.unique_id,
                        "node_type": getattr(node, 'node_type', 'TextNode') if hasattr(node, 'node_type') else 'TextNode',
                        "is_interactive": getattr(node, 'is_interactive', False) if hasattr(node, 'is_interactive') else False,
                        "text": node.text if hasattr(node, 'text') else None,
                        "key": getattr(node, 'key', None) if hasattr(node, 'key') else None,
                        "parent": node.parent_node.unique_id if node.parent_node else None,
                    }
                    node_info.append(info)
                
                msg = f"Retrieved app state with {len(node_state.selector_map)} nodes:\n{str(node_info)}"
                return ActionResult(success=True, extracted_content=msg, include_in_memory=True)
            except Exception as e:
                logger.error(f"Error in get_app_state: {str(e)}")
                return ActionResult(success=False, error=f"Exception in get_app_state: {str(e)}", include_in_memory=True)

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
            error_msg = f"Error executing action: {str(e)}"
            logger.error(error_msg)
            return ActionResult(success=False, error=error_msg, include_in_memory=True)