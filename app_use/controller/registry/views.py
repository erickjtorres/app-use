from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from app_use.app.app import App

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


class SpecialActionParameters(BaseModel):
	"""Model defining all special parameters that can be injected into actions"""

	model_config = ConfigDict(arbitrary_types_allowed=True)

	# optional user-provided context object passed down from Agent(context=...)
	context: Any | None = None

	# app-use app object, can be used to interact with mobile apps
	app: App | None = None
