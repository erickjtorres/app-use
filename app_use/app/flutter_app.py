from app_use.app.app import App
from app_use.nodes.widget_tree_builder import WidgetTreeBuilder
from app_use.nodes.app_node import NodeState, AppElementNode
from dart_vm_client import DartVmServiceManager, DartVmServiceClient
import atexit


class FlutterApp(App):
    """
    Implementation of App for Flutter applications using the Dart VM Service
    """
    
    def __init__(self, client=None, vm_service_uri=None):
        """
        Initialize the FlutterApp with a client or create a new client and connect to a VM service URI.
        
        Args:
            client: An existing DartVmServiceClient instance, or None to create a new one
            vm_service_uri: The WebSocket URI of the VM service to connect to (if client is None)
        
        Raises:
            ValueError: If both client and vm_service_uri are None, or if connection fails
        """
        self._manage_client = False
        self.timeout = 30  # Default timeout in seconds
        
        if client is None:
            if vm_service_uri is None:
                raise ValueError("Either client or vm_service_uri must be provided")

            self.service_manager = None
            self.client = None
            
            try:
                self.service_manager = DartVmServiceManager(port=50052)
                if not self.service_manager.start():
                    raise ValueError("Failed to start Dart VM Service Manager on port 50052")

                print(f"Using DartVmServiceClient to connect to {vm_service_uri}")
                self.client = DartVmServiceClient("localhost:50052")
                response = self.client.connect(vm_service_uri)
                if not hasattr(response, 'success') or not response.success:
                    error_msg = getattr(response, 'message', 'Unknown error')
                    raise ValueError(f"Failed to connect to Flutter app: {error_msg}")

                self._manage_client = True
                atexit.register(self.close)
            except Exception as e:
                self.close()  # Clean up any resources that were created
                raise ValueError(f"Failed to initialize Flutter app: {str(e)}")
        else:
            self.client = client
            
        self.app_state = {}
        
    def get_app_state(self) -> NodeState:
        """
        Get the current state of the app
        
        Returns:
            NodeState: A NodeState object containing the element tree and selector map
        """
        builder = WidgetTreeBuilder(self.client)
        node_state = builder.build_widget_tree("flutter")
        return node_state
    
    def _execute_with_timeout(self, operation_name, operation_func, timeout=None):
        """
        Execute a function with timeout handling
        
        Args:
            operation_name: Name of the operation for error reporting
            operation_func: Function to execute
            timeout: Optional timeout in seconds to override default timeout
            
        Returns:
            The result of the operation function
            
        Raises:
            TimeoutError: If the operation times out
            Exception: Any exception raised by the operation function
        """
        import concurrent.futures
        import time
        
        timeout = timeout or self.timeout
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(operation_func)
            try:
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if future.done():
                        return future.result()
                    time.sleep(0.1)
                    
                # If we get here, the operation timed out
                raise TimeoutError(f"Operation '{operation_name}' timed out after {timeout} seconds")
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"Operation '{operation_name}' timed out after {timeout} seconds")
        
    def enter_text_with_unique_id(self, node_state: NodeState, unique_id: int, text: str, timeout=None) -> bool:
        """
        Finds a widget by its unique_id and triggers a text entry action, 
        prioritizing enter_text_by_ancestor_and_descendant method
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to enter text
            text: The text to enter
            timeout: Optional timeout in seconds to override default timeout
        
        Returns:
            Boolean indicating success or failure
        
        Raises:
            ValueError: If the widget with the given unique_id is not found
            RuntimeError: If all text entry methods fail due to critical errors
            TimeoutError: If the operation times out
        """
        timeout = timeout or self.timeout
        target_node = node_state.selector_map.get(unique_id)
            
        if not target_node:
            error_msg = f"No widget found with unique_id: {unique_id}"
            print(error_msg)
            raise ValueError(error_msg)
        
        self.ensure_widget_visible(node_state, unique_id)

        # Ensure the TextField is focused by tapping it before typing. In many Flutter apps
        # a TextField does not accept programmatic text entry unless it currently has
        # focus, which is typically obtained via a tap gesture. We attempt a silent tap
        # (best-effort) and then proceed with the existing text-entry strategies. Any
        # errors from tapping are swallowed so we still fall back to the other methods.
        try:
            self.click_widget_by_unique_id(node_state, unique_id)
        except Exception:
            # Ignore tap failures; the subsequent text-entry attempts will handle errors
            pass
        
        print(f"Attempting to enter text in {target_node.node_type}")
        
        critical_errors = []
        
        if target_node.key:
            try:
                print(f"Trying enter text by Flutter key: {target_node.key}")
                
                def operation():
                    return self.client.enter_text_by_key(target_node.key, text)
                
                response = self._execute_with_timeout(
                    f"enter_text_by_key({target_node.key})", operation, timeout
                )
                    
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully entered text using Flutter key")
                    return True
            except Exception as e:
                error_msg = f"Error entering text by Flutter key: {e}"
                print(error_msg)
                critical_errors.append(error_msg)
        
        if target_node.text:
            try:
                print(f"Trying enter text by text: '{target_node.text}'")
                
                def operation():
                    return self.client.enter_text_by_text(target_node.text, text)
                
                response = self._execute_with_timeout(
                    f"enter_text_by_text({target_node.text})", operation, timeout
                )
                        
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully entered text using text content")
                    return True
            except Exception as e:
                error_msg = f"Error entering text by text: {e}"
                print(error_msg)
                critical_errors.append(error_msg)
        
        if target_node.parent_node:
            ancestor_type = target_node.parent_node.node_type.split(' ')[0]
            descendant_type = target_node.node_type.split(' ')[0]
            
            try:
                print(f"Trying enter text by ancestor-descendant: {ancestor_type} -> {descendant_type}")
                
                def operation():
                    return self.client.enter_text_by_ancestor_and_descendant(
                        ancestor_type, descendant_type, text
                    )
                
                response = self._execute_with_timeout(
                    f"enter_text_by_ancestor_and_descendant({ancestor_type}, {descendant_type})", operation, timeout
                )
                        
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully entered text using ancestor-descendant method")
                    return True
            except Exception as e:
                error_msg = f"Error with ancestor-descendant text entry: {e}"
                print(error_msg)
                critical_errors.append(error_msg)
        
        try:
            node_type = target_node.node_type.split(' ')[0]  # Use main widget type
            print(f"Trying enter text by widget type: {node_type}")
            
            def operation():
                return self.client.enter_text_by_type(node_type, text)
            
            response = self._execute_with_timeout(
                f"enter_text_by_type({node_type})", operation, timeout
            )
                    
            if hasattr(response, 'success') and response.success:
                print(f"Successfully entered text using widget type")
                return True
        except Exception as e:
            error_msg = f"Error entering text by widget type: {e}"
            print(error_msg)
            critical_errors.append(error_msg)
            
        # Try tooltip if available
        if hasattr(target_node, 'tooltip') and target_node.tooltip:
            try:
                print(f"Trying enter text by tooltip: {target_node.tooltip}")
                
                def operation():
                    return self.client.enter_text_by_tooltip(target_node.tooltip, text)
                
                response = self._execute_with_timeout(
                    f"enter_text_by_tooltip({target_node.tooltip})", operation, timeout
                )
                
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully entered text using tooltip")
                    return True
            except Exception as e:
                error_msg = f"Error entering text by tooltip: {e}"
                print(error_msg)
                critical_errors.append(error_msg)
        
        # Try generic enter_text method as a fallback
        try:
            print(f"Trying generic enter_text method as fallback")
            identifier = target_node.key or target_node.text or target_node.node_type
            
            def operation():
                return self.client.enter_text(identifier, text)
            
            response = self._execute_with_timeout(
                f"enter_text({identifier})", operation, timeout
            )
            
            if hasattr(response, 'success') and response.success:
                print(f"Successfully entered text using generic method")
                return True
        except Exception as e:
            error_msg = f"Error with generic text entry method: {e}"
            print(error_msg)
            critical_errors.append(error_msg)
        
        error_summary = f"Failed to enter text in widget with unique_id: {unique_id}. All methods failed with errors."
        print(error_summary)
        if critical_errors:
            error_details = "\n".join(critical_errors)
            print(f"Error details:\n{error_details}")
            
        return False
    
    
    def click_widget_by_unique_id(self, node_state: NodeState, unique_id: int) -> bool:
        """
        Finds a widget by its unique_id and triggers a tap action, 
        prioritizing tap_widget_by_ancestor_and_descendant method
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to click
        
        Returns:
            Boolean indicating success or failure
        """
        # Find the node with the matching unique_id using the selector map
        target_node = node_state.selector_map.get(unique_id)
            
        if not target_node:
            print(f"No widget found with unique_id: {unique_id}")
            return False
        
        # Ensure the widget is visible
        self.ensure_widget_visible(node_state, unique_id)
        
        # Check if the node is interactive
        widget_likely_interactive = self._is_widget_interactive(target_node)
        if not widget_likely_interactive:
            print(f"Widget with unique_id {unique_id} does not appear to be interactive")
            # We'll still try to click it as our check might not be perfect
        
        print(f"Attempting to click on {target_node.node_type}")
        
        
        # Try by Flutter key if available
        if target_node.key:
            try:
                print(f"Trying tap by Flutter key: {target_node.key}")
                response = self.client.tap_widget_by_key(target_node.key)
                if hasattr(response, 'success') and response.success:
                    print("Successfully tapped using Flutter key")
                    return True
            except Exception as e:
                print(f"Error tapping by Flutter key: {e}")
        
        # Try by text content if available
        if target_node.text:
            try:
                print(f"Trying tap by text: '{target_node.text}'")
                response = self.client.tap_widget_by_text(target_node.text)
                if hasattr(response, 'success') and response.success:
                    print("Successfully tapped using text content")
                    return True
            except Exception as e:
                print(f"Error tapping by text: {e}")
        
        
        # Try with ancestor-descendant approach (preferred method)
        if target_node.parent_node:
            # Get ancestor type (parent widget type)
            ancestor_type = target_node.parent_node.node_type.split(' ')[0]  # Get main type without description
            # Get descendant type (current widget type)
            descendant_type = target_node.node_type.split(' ')[0]  # Get main type without description
            
            try:
                print(f"Trying tap by ancestor-descendant: {ancestor_type} -> {descendant_type}")
                response = self.client.tap_widget_by_ancestor_and_descendant(ancestor_type, descendant_type)
                if hasattr(response, 'success') and response.success:
                    print("Successfully tapped using ancestor-descendant method")
                    return True
            except Exception as e:
                print(f"Error with ancestor-descendant tap: {e}")
                
        
        # Try by widget type
        try:
            print(f"Trying tap by widget type: {target_node.node_type}")
            response = self.client.tap_widget_by_type(target_node.node_type.split(' ')[0])  # Use main widget type
            if hasattr(response, 'success') and response.success:
                print("Successfully tapped using widget type")
                return True
        except Exception as e:
            print(f"Error tapping by widget type: {e}")
        
        
        # If all attempts fail, check if there's an interactive parent we could tap instead
        if target_node.parent_node and self._is_widget_interactive(target_node.parent_node):
            print(f"Current widget couldn't be tapped, trying parent: {target_node.parent_node.node_type}")
            return self.click_widget_by_unique_id(node_state, target_node.parent_node.unique_id)
        
        print(f"Failed to click on widget with unique_id: {unique_id}")
        return False

    def _is_widget_interactive(self, node: AppElementNode) -> bool:
        """
        Determine if a widget is likely to be interactive based on its properties and type.
        
        Args:
            node: The node to check for interactivity
            
        Returns:
            Boolean indicating whether the widget is likely interactive
        """
        # Check based on widget type
        interactive_types = [
            'button', 'gesturedetector', 'inkwell', 'iconbutton', 'flatbutton', 'elevatedbutton',
            'outlinedbutton', 'textbutton', 'floatingactionbutton', 'checkbox', 'radio',
            'switch', 'slider', 'togglebutton', 'expansiontile', 'listtile', 'card',
            'actionchip', 'choicechip', 'filterchip', 'inputchip', 'dropdownbutton',
            'popupmenubutton', 'menuitem', 'menubutton', 'rawmaterialbutton', 'materialbutton',
            'cupertino', 'taparea', 'clickable', 'selectable'
        ]
        
        node_type_lower = node.node_type.lower()
        if any(interactive_type in node_type_lower for interactive_type in interactive_types):
            return True
            
        # Check for interactive properties
        if getattr(node, 'properties', None):
            interactive_properties = [
                'onpressed', 'ontap', 'onchanged', 'onselected', 'ondoubletap', 
                'onlongpress', 'onfocuschange', 'enabled', 'clickable', 'focusable'
            ]
            
            for prop_name, prop_value in node.properties.items():
                prop_name_lower = prop_name.lower()
                if any(interactive_property in prop_name_lower for interactive_property in interactive_properties):
                    # Check if the property is not explicitly disabled (e.g., "enabled: false")
                    if isinstance(prop_value, bool) and not prop_value and 'enabled' in prop_name_lower:
                        continue
                    return True
        
        # Check if node has listeners or handlers
        if hasattr(node, 'is_interactive') and node.is_interactive:
            return True
            
        # Fall back to the existing check
        return bool(getattr(node, 'is_interactive', False))

    def scroll_into_view(self, node_state: NodeState, unique_id: int) -> bool:
        """
        Scroll a widget into view by trying different methods in order of expected reliability.

        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to scroll into view

        Returns:
            Boolean indicating success or failure
        """
        # Find the node with the matching unique_id using the selector map
        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            print(f"No widget found with unique_id: {unique_id}")
            return False

        print(f"Attempting to scroll into view: {target_node.node_type}")

        # Try by Flutter key if available
        if target_node.key:
            try:
                print(f"Trying scroll into view by key: {target_node.key}")
                response = self.client.scroll_into_view_by_key(target_node.key)
                if hasattr(response, 'success') and response.success:
                    print("Successfully scrolled into view using key")
                    return True
            except Exception as e:
                print(f"Error scrolling into view by key: {e}")

        # Try by text content if available
        if target_node.text:
            try:
                print(f"Trying scroll into view by text: '{target_node.text}'")
                response = self.client.scroll_into_view_by_text(target_node.text)
                if hasattr(response, 'success') and response.success:
                    print("Successfully scrolled into view using text")
                    return True
            except Exception as e:
                print(f"Error scrolling into view by text: {e}")

        # Try by widget type
        try:
            print(f"Trying scroll into view by type: {target_node.node_type}")
            response = self.client.scroll_into_view_by_type(target_node.node_type)
            if hasattr(response, 'success') and response.success:
                print("Successfully scrolled into view using type")
                return True
        except Exception as e:
            print(f"Error scrolling into view by type: {e}")

        # Try by tooltip if available
        if 'tooltip' in target_node.properties:
            try:
                tooltip = target_node.properties['tooltip']
                print(f"Trying scroll into view by tooltip: {tooltip}")
                response = self.client.scroll_into_view_by_tooltip(tooltip)
                if hasattr(response, 'success') and response.success:
                    print("Successfully scrolled into view using tooltip")
                    return True
            except Exception as e:
                print(f"Error scrolling into view by tooltip: {e}")

        # Try with ancestor-descendant approach
        if target_node.parent_node:
            # Get ancestor type (parent widget type)
            ancestor_type = target_node.parent_node.node_type.split(' ')[0]  # Get main type without description
            # Get descendant type (current widget type)
            descendant_type = target_node.node_type.split(' ')[0]  # Get main type without description
            
            try:
                print(f"Trying scroll into view by ancestor-descendant: {ancestor_type} -> {descendant_type}")
                response = self.client.scroll_into_view_by_ancestor_and_descendant(ancestor_type, descendant_type)
                if hasattr(response, 'success') and response.success:
                    print("Successfully scrolled into view using ancestor-descendant")
                    return True
            except Exception as e:
                print(f"Error with ancestor-descendant scroll into view: {e}")

        print(f"Failed to scroll into view for widget with unique_id: {unique_id}")
        return False

    def scroll_up_or_down(self, node_state: NodeState, unique_id: int, direction: str = "down") -> bool:
        """
        Scroll a widget up or down by trying different methods in order of expected reliability.

        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to scroll
            direction: "up" or "down" scroll direction

        Returns:
            Boolean indicating success or failure
        """
        # Find the node with the matching unique_id using the selector map
        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            print(f"No widget found with unique_id: {unique_id}")
            return False

        print(f"Attempting to scroll {direction}: {target_node.node_type}")

        # Try by Flutter key if available
        if target_node.key:
            try:
                print(f"Trying scroll {direction} by key: {target_node.key}")
                if direction == "down":
                    response = self.client.scroll_down_by_key(target_node.key)
                else:
                    response = self.client.scroll_up_by_key(target_node.key)
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully scrolled {direction} using key")
                    return True
            except Exception as e:
                print(f"Error scrolling {direction} by key: {e}")

        # Try by text content if available
        if target_node.text:
            try:
                print(f"Trying scroll {direction} by text: '{target_node.text}'")
                if direction == "down":
                    response = self.client.scroll_down_by_text(target_node.text)
                else:
                    response = self.client.scroll_up_by_text(target_node.text)
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully scrolled {direction} using text")
                    return True
            except Exception as e:
                print(f"Error scrolling {direction} by text: {e}")

        # Try by widget type
        try:
            print(f"Trying scroll {direction} by type: {target_node.node_type}")
            if direction == "down":
                response = self.client.scroll_down_by_type(target_node.node_type)
            else:
                response = self.client.scroll_up_by_type(target_node.node_type)
            if hasattr(response, 'success') and response.success:
                print(f"Successfully scrolled {direction} using type")
                return True
        except Exception as e:
            print(f"Error scrolling {direction} by type: {e}")

        # Try by tooltip if available
        if 'tooltip' in target_node.properties:
            try:
                tooltip = target_node.properties['tooltip']
                print(f"Trying scroll {direction} by tooltip: {tooltip}")
                if direction == "down":
                    response = self.client.scroll_down_by_tooltip(tooltip)
                else:
                    response = self.client.scroll_up_by_tooltip(tooltip)
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully scrolled {direction} using tooltip")
                    return True
            except Exception as e:
                print(f"Error scrolling {direction} by tooltip: {e}")

        # Try with ancestor-descendant approach
        if target_node.parent_node:
            # Get ancestor type (parent widget type)
            ancestor_type = target_node.parent_node.node_type.split(' ')[0]  # Get main type without description
            # Get descendant type (current widget type)
            descendant_type = target_node.node_type.split(' ')[0]  # Get main type without description

            try:
                print(f"Trying scroll {direction} by ancestor-descendant: {ancestor_type} -> {descendant_type}")
                if direction == "down":
                    response = self.client.scroll_down_by_ancestor_and_descendant(ancestor_type, descendant_type)
                else:
                    response = self.client.scroll_up_by_ancestor_and_descendant(ancestor_type, descendant_type)
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully scrolled {direction} using ancestor-descendant")
                    return True
            except Exception as e:
                print(f"Error with ancestor-descendant scroll {direction}: {e}")

        print(f"Failed to scroll {direction} for widget with unique_id: {unique_id}")
        return False

    def scroll_up_or_down_extended(self, node_state: NodeState, unique_id: int, direction: str = "down", dx: int = 0, dy: int = 100, duration_microseconds: int = 300000, frequency: int = 60) -> bool:
        """
        Scroll a widget up or down with extended parameters by trying different methods in order of expected reliability.

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
        """
        # Adjust dy based on direction if not explicitly set
        if direction == "up" and dy > 0:
            dy = -dy
        elif direction == "down" and dy < 0:
            dy = -dy

        # Find the node with the matching unique_id using the selector map
        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            print(f"No widget found with unique_id: {unique_id}")
            return False

        print(f"Attempting to scroll {direction} with extended parameters: {target_node.node_type}")

        # Try by Flutter key if available
        if target_node.key:
            try:
                print(f"Trying scroll {direction} by key with extended parameters: {target_node.key}")
                if direction == "down":
                    response = self.client.scroll_down_by_key_extended(target_node.key, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
                else:
                    response = self.client.scroll_up_by_key_extended(target_node.key, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully scrolled {direction} using key with extended parameters")
                    return True
            except Exception as e:
                print(f"Error scrolling {direction} by key with extended parameters: {e}")

        # Try by text content if available
        if target_node.text:
            try:
                print(f"Trying scroll {direction} by text with extended parameters: '{target_node.text}'")
                if direction == "down":
                    response = self.client.scroll_down_by_text_extended(target_node.text, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
                else:
                    response = self.client.scroll_up_by_text_extended(target_node.text, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully scrolled {direction} using text with extended parameters")
                    return True
            except Exception as e:
                print(f"Error scrolling {direction} by text with extended parameters: {e}")

        # Try by widget type
        try:
            print(f"Trying scroll {direction} by type with extended parameters: {target_node.node_type}")
            if direction == "down":
                response = self.client.scroll_down_by_type_extended(target_node.node_type, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
            else:
                response = self.client.scroll_up_by_type_extended(target_node.node_type, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
            if hasattr(response, 'success') and response.success:
                print(f"Successfully scrolled {direction} using type with extended parameters")
                return True
        except Exception as e:
            print(f"Error scrolling {direction} by type with extended parameters: {e}")

        # Try by tooltip if available
        if 'tooltip' in target_node.properties:
            try:
                tooltip = target_node.properties['tooltip']
                print(f"Trying scroll {direction} by tooltip with extended parameters: {tooltip}")
                if direction == "down":
                    response = self.client.scroll_down_by_tooltip_extended(tooltip, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
                else:
                    response = self.client.scroll_up_by_tooltip_extended(tooltip, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully scrolled {direction} using tooltip with extended parameters")
                    return True
            except Exception as e:
                print(f"Error scrolling {direction} by tooltip with extended parameters: {e}")

        # Try with ancestor-descendant approach
        if target_node.parent_node:
            # Get ancestor type (parent widget type)
            ancestor_type = target_node.parent_node.node_type.split(' ')[0]  # Get main type without description
            # Get descendant type (current widget type)
            descendant_type = target_node.node_type.split(' ')[0]  # Get main type without description

            try:
                print(f"Trying scroll {direction} by ancestor-descendant with extended parameters: {ancestor_type} -> {descendant_type}")
                if direction == "down":
                    response = self.client.scroll_down_by_ancestor_and_descendant_extended(ancestor_type, descendant_type, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
                else:
                    response = self.client.scroll_up_by_ancestor_and_descendant_extended(ancestor_type, descendant_type, dx=dx, dy=dy, duration_microseconds=duration_microseconds, frequency=frequency)
                if hasattr(response, 'success') and response.success:
                    print(f"Successfully scrolled {direction} using ancestor-descendant with extended parameters")
                    return True
            except Exception as e:
                print(f"Error with ancestor-descendant scroll {direction} with extended parameters: {e}")

        print(f"Failed to scroll {direction} with extended parameters for widget with unique_id: {unique_id}")
        return False

    def find_ancestor_with_scroll(self, node: AppElementNode):
        """
        Find the closest ancestor of a node that is likely to be scrollable.
        
        Args:
            node: The node to find a scrollable ancestor for
            
        Returns:
            The closest scrollable ancestor node or None if none found
        """
        if not node or not node.parent_node:
            return None
            
        # Define types that are commonly scrollable
        scrollable_types = [
            'scrollview', 'listview', 'gridview', 'pageview', 'singlechildscrollview',
            'customscrollview', 'nestedscrollview', 'refreshindicator', 'scrollable',
            'tabbarview', 'reorderablelistview', 'draggablescrollablesheet',
            'scrollconfiguration', 'scrollphysics', 'scrollbar', 'scrollcontroller',
            'scrollnotification', 'scrollable', 'overscroll'
        ]
        
        # Start with the immediate parent
        current = node.parent_node
        
        # Go up the tree looking for scrollable ancestors
        while current:
            # Check if the current node is likely scrollable
            current_type = current.node_type.lower()
            if any(scroll_type in current_type for scroll_type in scrollable_types):
                return current
                
            # Check for scrollable properties in the node
            if any(prop in current.properties for prop in ['scroll', 'overflow', 'scrollable']):
                return current
                
            # Move up to the parent
            current = current.parent_node
            
        # No scrollable ancestor found
        return None
        
    def find_descendant_with_scroll(self, node: AppElementNode):
        """
        Find the first descendant of a node that is likely to be scrollable.
        
        Args:
            node: The node to find a scrollable descendant for
            
        Returns:
            The first scrollable descendant node or None if none found
        """
        if not node or not node.child_nodes:
            return None
            
        # Define types that are commonly scrollable
        scrollable_types = [
            'scrollview', 'listview', 'gridview', 'pageview', 'singlechildscrollview',
            'customscrollview', 'nestedscrollview', 'refreshindicator', 'scrollable',
            'tabbarview', 'reorderablelistview', 'draggablescrollablesheet',
            'scrollconfiguration', 'scrollphysics', 'scrollbar', 'scrollcontroller',
            'scrollnotification', 'scrollable', 'overscroll'
        ]
        
        # Helper function for DFS traversal
        def find_scrollable_dfs(current):
            # Check if the current node is likely scrollable
            current_type = current.node_type.lower()
            if any(scroll_type in current_type for scroll_type in scrollable_types):
                return current
                
            # Check for scrollable properties in the node
            if any(prop in current.properties for prop in ['scroll', 'overflow', 'scrollable']):
                return current
                
            # Check children recursively
            for child in current.child_nodes:
                result = find_scrollable_dfs(child)
                if result:
                    return result
                    
            return None
            
        # Start search from the node's children
        return find_scrollable_dfs(node)

    def ensure_widget_visible(self, node_state: NodeState, unique_id: int) -> bool:
        """
        Ensures a widget is visible by scrolling it into view if necessary.
        This should be called before interacting with widgets that might be off-screen.
        Fails silently if the widget doesn't need to be scrolled or can't be scrolled.
        
        Args:
            node_state: NodeState object containing the element tree and selector map
            unique_id: The unique identifier of the widget to make visible
            
        Returns:
            Boolean indicating success or failure to make the widget visible
        """
        target_node = node_state.selector_map.get(unique_id)
        
        # Silently return True if widget doesn't exist (will be handled by calling method)
        if not target_node:
            return True
            
        # Try to scroll into view without verbose logging
        try:
            self.scroll_into_view(node_state, unique_id)
        except Exception:
            pass
            
        # Always return True to allow interaction to proceed
        return True
    
    def take_screenshot(self) -> str:
        """
        Take a screenshot of the current app state.

        Returns:
            Base64 encoded string of the screenshot
        """
        try:
            # Get the root widget to obtain its ID
            root_response = self.client.get_root_widget("flutter")
            
            widget_id = None
            if hasattr(root_response, 'data') and root_response.data:
                try:
                    import json
                    data = json.loads(root_response.data)
                    if 'result' in data:
                        if isinstance(data['result'], str):
                            widget_id = data['result']
                        elif isinstance(data['result'], dict) and 'id' in data['result']:
                            widget_id = data['result']['id']
                        elif isinstance(data['result'], dict) and 'valueId' in data['result']:
                            widget_id = data['result']['valueId']
                except json.JSONDecodeError:
                    pass
            
            # Fallback to default if we can't get the root widget ID
            if not widget_id:
                widget_id = 'inspector-8'
                print(f"Could not determine root widget ID, using fallback: {widget_id}")
            else:
                print(f"Using root widget ID for screenshot: {widget_id}")
            
            # Take screenshot with reasonable dimensions and zero margin
            screenshot_params = {
                'id': widget_id,
                'width': 400,  # Reasonable width
                'height': 800,  # Reasonable height
                'margin': 0.0,  # Zero margin as requested
                'maxPixelRatio': None,
                'debugPaint': False
            }
            
            response = self.client.screenshot(**screenshot_params)
            print(f"Screenshot taken with params: {screenshot_params}")
            return response
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            # Fallback to original method if there's an error
            response = self.client.screenshot(widget_id='inspector-24')
            return response
    

    def close(self):
        """Close client and stop service manager if managed by this class"""
        if self._manage_client and hasattr(self, 'client') and self.client:
            try:
                self.client.close()
            except Exception:
                pass
        if hasattr(self, 'service_manager'):
            try:
                self.service_manager.stop()
            except Exception:
                pass