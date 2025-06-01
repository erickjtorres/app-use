import logging
import time

from app_use.nodes.app_node import AppElementNode, NodeState, CoordinateSet, ViewportInfo
logger = logging.getLogger("AppiumApp")

class AppiumElementTreeBuilder:
    """
    Builds element trees from Appium page source XML, with highlight indices and visibility tracking
    """
    
    def __init__(self, driver):
        """
        Initialize the element tree builder with an Appium driver
        
        Args:
            driver: Appium WebDriver instance
        """
        self.driver = driver
        self._id_counter = 0
        self._highlight_index = 0
        self._selector_map = {}
        self._perf_metrics = {
            'build_tree_time': 0,
            'node_count': 0,
            'highlighted_count': 0,
        }
        
    def build_element_tree(self, platform_type: str, viewport_expansion: int = 0, debug_mode: bool = False):
        """
        Build an element tree from the current app state, with highlight indices and selector map
        """
        self._id_counter = 0
        self._highlight_index = 0
        self._selector_map = {}
        self._perf_metrics = {
            'build_tree_time': 0,
            'node_count': 0,
            'highlighted_count': 0,
        }
        start_time = time.time()
        try:
            page_source = self.driver.page_source
            import xml.etree.ElementTree as ET
            root = ET.fromstring(page_source)
            
            # Get screen dimensions for viewport calculations
            try:
                size = self.driver.get_window_size()
                screen_width = size['width']
                screen_height = size['height']
                viewport_info = ViewportInfo(width=screen_width, height=screen_height)
            except Exception:
                screen_width = screen_height = 0
                viewport_info = ViewportInfo(width=0, height=0)
            
            root_node = self._parse_element(
                root, None, platform_type, screen_width, screen_height, viewport_expansion, debug_mode, viewport_info
            )
            all_nodes = self._collect_all_nodes(root_node)
            selector_map = self._selector_map.copy()
            self._perf_metrics['build_tree_time'] = time.time() - start_time
            self._perf_metrics['node_count'] = len(all_nodes)
            self._perf_metrics['highlighted_count'] = len(selector_map)
            logger.info(f"Built element tree with {len(all_nodes)} nodes, {len(selector_map)} highlighted")
            
            return NodeState(element_tree=root_node, selector_map=selector_map)
            
        except Exception as e:
            logger.error(f"Error building element tree: {str(e)}")
            empty_node = AppElementNode(
                unique_id=0,
                node_type="Error",
                is_interactive=False,
                properties={},
                parent_node=None
            )
            return NodeState(element_tree=empty_node, selector_map={0: empty_node})
    
    def _parse_element(self, element, parent, platform_type, screen_width, screen_height, viewport_expansion, debug_mode, viewport_info):
        """
        Parse an XML element into an AppElementNode
        
        Args:
            element: XML element to parse
            parent: Parent AppElementNode
            platform_type: The platform type (e.g., "android", "ios")
            screen_width: Screen width
            screen_height: Screen height
            viewport_expansion: Viewport expansion
            debug_mode: Debug mode
            viewport_info: ViewportInfo object with screen dimensions
            
        Returns:
            AppElementNode: The parsed element node
        """
        current_unique_id = self._id_counter
        self._id_counter += 1
        
        attributes = element.attrib
        
        if platform_type.lower() == "android":
            node_type = attributes.get("class", "Unknown")
        elif platform_type.lower() == "ios":
            node_type = attributes.get("type", "Unknown")
        else:
            node_type = "Unknown"
        
        text = attributes.get("text", None) or attributes.get("content-desc", None) or attributes.get("name", None) or attributes.get("value", None)
        
        key = None
        if platform_type.lower() == "android":
            key = attributes.get("resource-id", None)
        elif platform_type.lower() == "ios":
            key = attributes.get("name", None)
        
        is_interactive = self._is_element_interactive(attributes, node_type, platform_type)
        
        # Parse bounds and calculate coordinates
        bounds = attributes.get("bounds", None)
        viewport_coordinates = None
        page_coordinates = None
        is_visible = True
        is_in_viewport = True
        
        if bounds and screen_width and screen_height:
            try:
                # Android/iOS bounds: [x1,y1][x2,y2]
                import re
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
                if m:
                    x1, y1, x2, y2 = map(int, m.groups())
                    width = x2 - x1
                    height = y2 - y1
                    is_visible = width > 0 and height > 0
                    
                    # For mobile apps, viewport coordinates and page coordinates are the same
                    # since there's no scrolling offset like in web browsers
                    viewport_coordinates = CoordinateSet(x=x1, y=y1, width=width, height=height)
                    page_coordinates = CoordinateSet(x=x1, y=y1, width=width, height=height)
                    
                    # Calculate if element is in expanded viewport
                    expanded_top = -viewport_expansion
                    expanded_bottom = screen_height + viewport_expansion
                    expanded_left = -viewport_expansion
                    expanded_right = screen_width + viewport_expansion
                    is_in_viewport = (
                        x2 > expanded_left and x1 < expanded_right and
                        y2 > expanded_top and y1 < expanded_bottom
                    )
            except Exception as e:
                logger.debug(f"Error parsing bounds '{bounds}': {e}")
        
        highlight_index = None
        if is_interactive and is_visible and is_in_viewport:
            highlight_index = self._highlight_index
            self._selector_map[highlight_index] = None
            self._highlight_index += 1
        
        props = dict(attributes)
        props['_is_visible'] = is_visible
        props['_is_in_viewport'] = is_in_viewport
        
        node = AppElementNode(
            unique_id=current_unique_id,
            node_type=node_type,
            is_interactive=is_interactive,
            properties=props,
            parent_node=parent,
            text=text,
            key=key,
            viewport_coordinates=viewport_coordinates,
            page_coordinates=page_coordinates,
            viewport_info=viewport_info,
            is_in_viewport=is_in_viewport
        )
        node.highlight_index = highlight_index
        node.child_nodes = []
        
        for child_element in element:
            child_node = self._parse_element(
                child_element, node, platform_type, screen_width, screen_height, viewport_expansion, debug_mode, viewport_info
            )
            if child_node:
                node.child_nodes.append(child_node)
        
        if highlight_index is not None:
            self._selector_map[highlight_index] = node
        
        return node
    
    def _is_element_interactive(self, attributes, node_type, platform_type):
        """
        Determine if an element is likely to be interactive based on its attributes and type
        
        Args:
            attributes: Element attributes
            node_type: Element node type
            platform_type: The platform type (e.g., "android", "ios")
            
        Returns:
            bool: True if the element is likely interactive, False otherwise
        """
        if platform_type.lower() == "android":
            interactive_types = [
                "android.widget.Button",
                "android.widget.ImageButton",
                "android.widget.EditText",
                "android.widget.CheckBox",
                "android.widget.RadioButton",
                "android.widget.Switch",
                "android.widget.Spinner",
                "android.widget.SeekBar"
            ]
            
            if attributes.get("clickable", "false").lower() == "true":
                return True
            
            if any(interactive_type in node_type for interactive_type in interactive_types):
                return True
            
            if attributes.get("has-click-listener", "false").lower() == "true":
                return True
                
        elif platform_type.lower() == "ios":
            interactive_types = [
                "XCUIElementTypeButton",
                "XCUIElementTypeTextField",
                "XCUIElementTypeSecureTextField",
                "XCUIElementTypeSwitch",
                "XCUIElementTypeSlider",
                "XCUIElementTypeCell",
                "XCUIElementTypeLink",
                "XCUIElementTypeSearchField",
                "XCUIElementTypeKey"
            ]
            
            if attributes.get("enabled", "false").lower() == "true":
                if node_type in interactive_types:
                    return True
                
            if "XCUIElementTypeControl" in node_type:
                return True
        
        return False
    
    def _collect_all_nodes(self, root_node):
        """
        Collect all nodes in the element tree
        
        Args:
            root_node: Root node of the element tree
            
        Returns:
            list: List of all nodes in the element tree
        """
        all_nodes = []
        
        def traverse(node):
            all_nodes.append(node)
            for child in node.child_nodes:
                traverse(child)
        
        traverse(root_node)
        return all_nodes