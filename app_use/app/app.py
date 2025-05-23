from abc import ABC, abstractmethod
from typing import Optional, Union, Tuple, Dict, List, Any, TypeVar, Generic

from app_use.nodes.app_node import NodeState

class App(ABC):
    """
    Abstract base class for app automation.
    Defines the interface that all app implementations must provide.
    """
    
    @abstractmethod
    def get_app_state(self) -> NodeState:
        """
        Get the current state of the app
        
        Returns:
            NodeState: A NodeState object containing the element tree and selector map
        
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement get_app_state()")
    
    @abstractmethod
    def enter_text_with_unique_id(self, node_state: NodeState, unique_id: int, text: str) -> bool:
        """
        Find a widget by its unique_id and enter text into it
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to enter text
            text: The text to enter
        
        Returns:
            Boolean indicating success or failure
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement enter_text_with_unique_id()")
    
    @abstractmethod
    def click_widget_by_unique_id(self, node_state: NodeState, unique_id: int) -> bool:
        """
        Find a widget by its unique_id and click it
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to click
        
        Returns:
            Boolean indicating success or failure
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement click_widget_by_unique_id()")

    @abstractmethod
    def scroll_into_view(self, node_state: NodeState, unique_id: int) -> bool:
        """
        Scroll a widget into view
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to scroll into view
            
        Returns:
            Boolean indicating success or failure
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement scroll_into_view()")
        
    @abstractmethod
    def scroll_up_or_down(self, node_state: NodeState, unique_id: int, direction: str = "down") -> bool:
        """
        Scroll a widget up or down
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to scroll
            direction: "up" or "down" scroll direction
            
        Returns:
            Boolean indicating success or failure
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement scroll_up_or_down()")
        
    @abstractmethod
    def scroll_up_or_down_extended(
        self, 
        node_state: NodeState, 
        unique_id: int, 
        direction: str = "down", 
        dx: int = 0, 
        dy: int = 100, 
        duration_microseconds: int = 300000, 
        frequency: int = 60
    ) -> bool:
        """
        Scroll a widget up or down with extended parameters
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to scroll
            direction: "up" or "down" scroll direction
            dx: Horizontal scroll amount (positive = right, negative = left)
            dy: Vertical scroll amount (positive = down, negative = up)
            duration_microseconds: Duration of the scroll gesture in microseconds
            frequency: Frequency of scroll events
            
        Returns:
            Boolean indicating success or failure
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement scroll_up_or_down_extended()")
        
    @abstractmethod
    def ensure_widget_visible(self, node_state: NodeState, unique_id: int) -> bool:
        """
        Ensures a widget is visible by scrolling it into view if necessary
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to make visible
            
        Returns:
            Boolean indicating success or failure
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement ensure_widget_visible()")
        
    @abstractmethod
    def close(self) -> None:
        """
        Close the connection to the app
        
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement close()")
        
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        
    def __del__(self):
        """Destructor to ensure resources are properly released"""
        try:
            self.close()
        except:
            pass