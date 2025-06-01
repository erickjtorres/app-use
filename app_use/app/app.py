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
    def take_screenshot(self) -> str:
        """
        Returns a base64 encoded screenshot of the current page.
        """
        raise NotImplementedError("Subclasses must implement take_screenshot()")
    
    @abstractmethod
    def close(self) -> None:
        """
        Close the connection to the app
        
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement close()")
    
    # Gesture methods
    @abstractmethod
    def swipe_coordinates(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 300) -> bool:
        """
        Perform a swipe gesture from start coordinates to end coordinates
        
        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate
            duration: Swipe duration in milliseconds
            
        Returns:
            bool: True if swipe was successful
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement swipe_coordinates()")
    
    @abstractmethod
    def pinch_gesture(self, center_x: int = None, center_y: int = None, percent: int = 50) -> bool:
        """
        Perform a pinch gesture (pinch in/out)
        
        Args:
            center_x: Center X coordinate (optional, uses screen center if None)
            center_y: Center Y coordinate (optional, uses screen center if None)
            percent: Pinch percentage (0-50 = pinch in, 50-100 = pinch out)
            
        Returns:
            bool: True if pinch was successful
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement pinch_gesture()")
    
    @abstractmethod
    def long_press_coordinates(self, x: int, y: int, duration: int = 1000) -> bool:
        """
        Perform a long press gesture at specific coordinates
        
        Args:
            x: X coordinate
            y: Y coordinate
            duration: Duration of long press in milliseconds
            
        Returns:
            bool: True if long press was successful
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement long_press_coordinates()")
    
    @abstractmethod
    def drag_and_drop_coordinates(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 1000) -> bool:
        """
        Perform a drag and drop gesture from start coordinates to end coordinates
        
        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate
            duration: Drag duration in milliseconds
            
        Returns:
            bool: True if drag and drop was successful
            
        Raises:
            NotImplementedError: This method must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement drag_and_drop_coordinates()")
        
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