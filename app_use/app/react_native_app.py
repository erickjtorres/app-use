from app_use.app.app import App
from app_use.nodes.element_tree_builder import ElementTreeBuilder
from app_use.nodes.app_node import NodeState, AppBaseNode, AppElementNode
from react_native_debugger_client import ReactNativeDebuggerClient
import atexit
import logging
from typing import Tuple, Optional

logger = logging.getLogger("ReactNativeApp")

class ReactNativeApp(App):
    """
    Implementation of App for React Native applications using the React Native Debugger Client
    """
    
    def __init__(self, client=None, device_ip="localhost", metro_port=8081):
        """
        Initialize the ReactNativeApp with a client or create a new one and connect to a device.
        
        Args:
            client: An existing ReactNativeDebuggerClient instance, or None to create a new one
            device_ip: The IP address of the device running the React Native app
            metro_port: The port on which the Metro bundler is running
        
        Raises:
            ValueError: If connection fails
        """
        self._manage_client = False
        
        if client is None:
            print(f"Using ReactNativeDebuggerClient to connect to {device_ip}:{metro_port}")
            self.client = ReactNativeDebuggerClient(device_ip=device_ip, metro_port=metro_port)
            success, message = self.client.connect()
            if not success:
                raise ValueError(f"Failed to connect to React Native app: {message}")

            self._manage_client = True
            atexit.register(self.close)
        else:
            self.client = client
            
        self.app_state = {}
        
    def get_app_state(self) -> NodeState:
        """
        Get the current state of the app
        
        Returns:
            NodeState: A NodeState object containing the element tree and selector map
        """
        builder = ElementTreeBuilder(self.client)
        node_state = builder.build_element_tree("react-native")
        return node_state
    
    def enter_text_with_unique_id(self, node_state: NodeState, unique_id: int, text: str) -> Tuple[bool, str]:
        """
        Finds a widget by its unique_id and triggers a text entry action
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to enter text
            text: The text to enter
        
        Returns:
            Tuple[bool, str]: (success flag, message)
        """
        target_node = node_state.selector_map.get(unique_id)
            
        if not target_node:
            message = f"No component found with unique_id: {unique_id}"
            print(message)
            return False, message
        
        self.ensure_widget_visible(node_state, unique_id)
        
        print(f"Attempting to enter text in {target_node.node_type}")
        
        if target_node.key:
            try:
                print(f"Trying enter text by testID: {target_node.key}")
                success, message = self.client.enter_text_by_testid(target_node.key, text)
                    
                if success:
                    print(f"Successfully entered text using testID")
                    return True, "Text entered successfully using testID"
                else:
                    print(f"Failed to enter text by testID: {message}")
            except Exception as e:
                print(f"Error entering text by testID: {e}")
        
        if target_node.text:
            try:
                print(f"Trying enter text by text: '{target_node.text}'")
                success, message = self.client.enter_text_by_text(target_node.text, text)
                        
                if success:
                    print(f"Successfully entered text using text content")
                    return True, "Text entered successfully using text content"
                else:
                    print(f"Failed to enter text by text content: {message}")
            except Exception as e:
                print(f"Error entering text by text: {e}")
        
        try:
            node_type = target_node.node_type
            print(f"Trying enter text by component type: {node_type}")
            
            success, message = self.client.enter_text_by_type(node_type, text)
                    
            if success:
                print(f"Successfully entered text using component type")
                return True, "Text entered successfully using component type"
            else:
                print(f"Failed to enter text by component type: {message}")
        except Exception as e:
            print(f"Error entering text by component type: {e}")
            
        message = f"Failed to enter text in component with unique_id: {unique_id}"
        print(message)
        return False, message
    
    
    def click_widget_by_unique_id(self, node_state: NodeState, unique_id: int) -> Tuple[bool, str]:
        """
        Finds a widget by its unique_id and triggers a tap action
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to click
        
        Returns:
            Tuple[bool, str]: (success flag, message)
        """
        target_node = node_state.selector_map.get(unique_id)
            
        if not target_node:
            message = f"No component found with unique_id: {unique_id}"
            print(message)
            return False, message
        
        self.ensure_widget_visible(node_state, unique_id)
        
        if not target_node.is_interactive:
            has_press_handler = any(prop.lower().find('press') >= 0 for prop in target_node.properties.keys())
            has_on_click = any(prop.lower().find('click') >= 0 for prop in target_node.properties.keys())
            has_touchable = target_node.node_type.lower().find('touchable') >= 0
            has_button = target_node.node_type.lower().find('button') >= 0
            
            if not (has_press_handler or has_on_click or has_touchable or has_button):
                print(f"Warning: Component with unique_id {unique_id} doesn't appear to be interactive")
        
        print(f"Attempting to tap on {target_node.node_type}")
        
        if target_node.key:
            try:
                print(f"Trying tap by testID: {target_node.key}")
                success, message = self.client.tap_by_testid(target_node.key)
                if success:
                    print("Successfully tapped using testID")
                    return True, "Successfully tapped using testID"
                else:
                    print(f"Failed to tap by testID: {message}")
            except Exception as e:
                print(f"Error tapping by testID: {e}")
        
        if target_node.text:
            try:
                print(f"Trying tap by text: '{target_node.text}'")
                success, message = self.client.tap_by_text(target_node.text)
                if success:
                    print("Successfully tapped using text content")
                    return True, "Successfully tapped using text content"
                else:
                    print(f"Failed to tap by text content: {message}")
            except Exception as e:
                print(f"Error tapping by text: {e}")
        
        try:
            print(f"Trying tap by component type: {target_node.node_type}")
            success, message = self.client.tap_by_type(target_node.node_type)
            if success:
                print("Successfully tapped using component type")
                return True, "Successfully tapped using component type"
            else:
                print(f"Failed to tap by component type: {message}")
        except Exception as e:
            print(f"Error tapping by component type: {e}")
        
        if target_node.parent_node and target_node.parent_node.is_interactive:
            print(f"Current component couldn't be tapped, trying parent: {target_node.parent_node.node_type}")
            return self.click_widget_by_unique_id(node_state, target_node.parent_node.unique_id)
        
        message = f"Failed to tap on component with unique_id: {unique_id}"
        print(message)
        return False, message

    def scroll_into_view(self, node_state: NodeState, unique_id: int) -> Tuple[bool, str]:
        """
        Scroll a widget into view

        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to scroll into view

        Returns:
            Tuple[bool, str]: (success flag, message)
        """
        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            message = f"No component found with unique_id: {unique_id}"
            print(message)
            return False, message

        print(f"Attempting to scroll into view: {target_node.node_type}")

        scrollable_ancestor = self._find_scrollable_ancestor(target_node)
        if not scrollable_ancestor:
            message = f"No scrollable ancestor found for component with unique_id: {unique_id}"
            print(message)
            return False, message

        if scrollable_ancestor.key:
            try:
                print(f"Scrolling down with scrollable ancestor (testID: {scrollable_ancestor.key})")
                success, message = self.client.scroll_by_testid(scrollable_ancestor.key, direction="down")
                if success:
                    return True, "Successfully scrolled down with scrollable ancestor"
                
                print(f"Scrolling up with scrollable ancestor (testID: {scrollable_ancestor.key})")
                success, message = self.client.scroll_by_testid(scrollable_ancestor.key, direction="up")
                if success:
                    return True, "Successfully scrolled up with scrollable ancestor"
                
                print(f"Failed to scroll with scrollable ancestor: {message}")
            except Exception as e:
                print(f"Error scrolling with scrollable ancestor: {e}")
                
        try:
            print("Trying general scroll down")
            success, message = self.client.scroll(direction="down")
            if success:
                print("Successfully scrolled down")
                return True, "Successfully scrolled down"
                
            print("Trying general scroll up")
            success, message = self.client.scroll(direction="up")
            if success:
                print("Successfully scrolled up")
                return True, "Successfully scrolled up"
                
            print(f"Failed to scroll: {message}")
        except Exception as e:
            print(f"Error with general scroll: {e}")

        message = f"Failed to scroll into view for component with unique_id: {unique_id}"
        print(message)
        return False, message

    def scroll_up_or_down(self, node_state: NodeState, unique_id: int, direction: str = "down") -> Tuple[bool, str]:
        """
        Scroll a widget up or down

        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to scroll
            direction: "up" or "down" scroll direction

        Returns:
            Tuple[bool, str]: (success flag, message)
        """
        if direction not in ["up", "down"]:
            message = f"Invalid direction: {direction}. Valid options are 'up' or 'down'."
            print(message)
            return False, message

        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            message = f"No component found with unique_id: {unique_id}"
            print(message)
            return False, message

        print(f"Attempting to scroll {direction}: {target_node.node_type}")

        if target_node.key:
            try:
                print(f"Trying scroll {direction} by testID: {target_node.key}")
                success, message = self.client.scroll_by_testid(target_node.key, direction=direction)
                if success:
                    print(f"Successfully scrolled {direction} using testID")
                    return True, f"Successfully scrolled {direction} using testID"
                else:
                    print(f"Failed to scroll by testID: {message}")
            except Exception as e:
                print(f"Error scrolling by testID: {e}")
        
        scrollable_ancestor = self._find_scrollable_ancestor(target_node)
        if scrollable_ancestor and scrollable_ancestor.key:
            try:
                print(f"Trying scroll {direction} with scrollable ancestor (testID: {scrollable_ancestor.key})")
                success, message = self.client.scroll_by_testid(scrollable_ancestor.key, direction=direction)
                if success:
                    print(f"Successfully scrolled {direction} using scrollable ancestor")
                    return True, f"Successfully scrolled {direction} using scrollable ancestor"
                else:
                    print(f"Failed to scroll with scrollable ancestor: {message}")
            except Exception as e:
                print(f"Error scrolling with scrollable ancestor: {e}")
                
        try:
            print(f"Trying general scroll {direction}")
            success, message = self.client.scroll(direction=direction)
            if success:
                print(f"Successfully scrolled {direction} using general scroll")
                return True, f"Successfully scrolled {direction} using general scroll"
            else:
                print(f"Failed to scroll: {message}")
        except Exception as e:
            print(f"Error with general scroll: {e}")

        message = f"Failed to scroll {direction} for component with unique_id: {unique_id}"
        print(message)
        return False, message

    def scroll_up_or_down_extended(self, node_state: NodeState, unique_id: int, direction: str = "down", dx: int = 0, dy: int = 100, duration_microseconds: int = 300000, frequency: int = 60) -> Tuple[bool, str]:
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
            Tuple[bool, str]: (success flag, message)
        """
        if direction not in ["up", "down"]:
            message = f"Invalid direction: {direction}. Valid options are 'up' or 'down'."
            print(message)
            return False, message

        duration_ms = duration_microseconds / 1000
        
        if direction == "up" and dy > 0:
            dy = -dy
        elif direction == "down" and dy < 0:
            dy = -dy

        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            message = f"No component found with unique_id: {unique_id}"
            print(message)
            return False, message

        print(f"Attempting to scroll {direction} with extended parameters: {target_node.node_type}")

        if target_node.key:
            try:
                print(f"Trying scroll {direction} by testID with extended parameters: {target_node.key}")
                success, message = self.client.scroll_by_testid(
                    target_node.key, 
                    direction=direction,
                    dx=dx, 
                    dy=dy, 
                    duration_ms=duration_ms
                )
                if success:
                    print(f"Successfully scrolled {direction} using testID with extended parameters")
                    return True, f"Successfully scrolled {direction} using testID with extended parameters"
                else:
                    print(f"Failed to scroll by testID with extended parameters: {message}")
            except Exception as e:
                print(f"Error scrolling by testID with extended parameters: {e}")
        
        scrollable_ancestor = self._find_scrollable_ancestor(target_node)
        if scrollable_ancestor and scrollable_ancestor.key:
            try:
                print(f"Trying scroll {direction} with scrollable ancestor (testID: {scrollable_ancestor.key}) with extended parameters")
                success, message = self.client.scroll_by_testid(
                    scrollable_ancestor.key, 
                    direction=direction,
                    dx=dx, 
                    dy=dy, 
                    duration_ms=duration_ms
                )
                if success:
                    print(f"Successfully scrolled {direction} using scrollable ancestor with extended parameters")
                    return True, f"Successfully scrolled {direction} using scrollable ancestor with extended parameters"
                else:
                    print(f"Failed to scroll with scrollable ancestor with extended parameters: {message}")
            except Exception as e:
                print(f"Error scrolling with scrollable ancestor with extended parameters: {e}")
                
        try:
            print(f"Trying general scroll {direction} with extended parameters")
            success, message = self.client.scroll(
                direction=direction, 
                dx=dx, 
                dy=dy, 
                duration_ms=duration_ms
            )
            if success:
                print(f"Successfully scrolled {direction} using general scroll with extended parameters")
                return True, f"Successfully scrolled {direction} using general scroll with extended parameters"
            else:
                print(f"Failed to scroll with extended parameters: {message}")
        except Exception as e:
            print(f"Error with general scroll with extended parameters: {e}")

        message = f"Failed to scroll {direction} with extended parameters for component with unique_id: {unique_id}"
        print(message)
        return False, message

    def _find_scrollable_ancestor(self, node) -> Optional[AppElementNode]:
        """
        Find the closest ancestor of a node that is likely to be scrollable.
        
        Args:
            node: The node to find a scrollable ancestor for
            
        Returns:
            Optional[AppElementNode]: The closest scrollable ancestor node or None if none found
        """
        if not node:
            return None
            
        if not hasattr(node, 'parent_node') or node.parent_node is None:
            return None
            
        scrollable_types = [
            'scrollview', 'flatlist', 'sectionlist', 'virtualizedlist', 
            'recyclerlistview', 'scrollableview', 'horizontalscrollview',
            'swiper', 'carousel', 'pager', 'viewpager'
        ]
        
        current = node.parent_node
        
        while current:
            try:
                if hasattr(current, 'node_type'):
                    current_type = current.node_type.lower()
                    if any(scroll_type in current_type for scroll_type in scrollable_types):
                        return current
                    
                if hasattr(current, 'properties'):
                    if any(prop.lower().find('scroll') >= 0 for prop in current.properties.keys()):
                        return current
                
                if not hasattr(current, 'parent_node'):
                    break
                current = current.parent_node
            except Exception as e:
                logger.warning(f"Error in _find_scrollable_ancestor: {e}")
                break
            
        return None

    def ensure_widget_visible(self, node_state: NodeState, unique_id: int) -> Tuple[bool, str]:
        """
        Ensures a widget is visible by scrolling it into view if necessary.
        This should be called before interacting with widgets that might be off-screen.
        Fails silently if the widget doesn't need to be scrolled or can't be scrolled.
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to make visible
            
        Returns:
            Tuple[bool, str]: (success flag, message)
        """
        target_node = node_state.selector_map.get(unique_id)
        
        if not target_node:
            return True, "Widget not found, visibility check skipped"
            
        try:
            success, message = self.scroll_into_view(node_state, unique_id)
            if success:
                return True, "Widget scrolled into view successfully"
            else:
                return True, "Widget may not be fully visible, but proceeding with interaction"
        except Exception as e:
            return True, f"Error ensuring widget visibility: {e}"

    def close(self):
        """Close client if managed by this class"""
        if self._manage_client and hasattr(self, 'client') and self.client:
            try:
                self.client.close()
            except Exception:
                pass 