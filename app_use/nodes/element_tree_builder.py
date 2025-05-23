import json
import logging
from react_native_debugger_client import ReactNativeDebuggerClient
from app_use.nodes.app_node import (
    AppElementNode,
    AppTextNode,
    NodeState,
    SelectorMap,
)

logger = logging.getLogger("ElementTreeBuilder")

# Components that should be skipped as they're mostly UI plumbing or layout machinery
IRRELEVANT_TYPES = {
    # Pure plumbing / semantics components
    'React.Fragment', 'AnimatedComponent', 'ForwardRef',
    'AppContainer', 'LogBox', 'DevMenu', 'PerformanceLoggerContext',
    
    # Navigation infrastructure
    'NavigationContent', 'PreventRemoveProvider', 'EnsureSingleNavigator',
    'StaticContainer', 'Route()', 'RouteNode', 'SafeAreaProviderCompat',
    
    # Context providers
    'ThemeContext', 'SafeAreaFrameContext', 'SafeAreaInsetsContext', 'HeaderHeightContext',
    'HeaderShownContext', 'HeaderBackContext', 'LinkingContext', 'LocaleDirContext',
    'UnhandledLinkingContext', 'TextAncestorContext', 'VirtualizedListContext', 'ScrollViewContext',
    
    # Animation and screen components
    'Animated(View)', 'Animated(Anonymous)', 'ScreenStack', 'RNSScreenStack',
    'ScreenStackHeaderConfig', 'RNSScreenStackHeaderConfig', 'ScreenContentWrapper', 'RNSScreenContentWrapper',
    
    # Debug components
    'PressabilityDebugView', 'DebugContainer', 'withDevTools(ErrorOverlay)', 'ErrorOverlay', 'ErrorToastContainer',
    'ImperativeApiEmitter', 'DebuggingOverlay', 'LogBoxStateSubscription', 
    
    # Wrapper components without direct UI value
    'DelayedFreeze', 'Freeze', 'Suspender', 'RootTagContext', 'VirtualizedListCellContextProvider',
    'CellRenderer',  # List item container without direct UI value

    # These are excluded from filtering as they often contain important content 
    # that would be lost if filtered out completely
    # 'View', 'RCTView', 'Memo', 'RCTSafeAreaView', 'RCTVirtualText', 'Unknown',
    # 'SafeAreaView', 'ThemeProvider', 'PortalProvider', 'GestureHandlerRootView'
}

# Canonicalization map for functionally equivalent components
CANONICAL_NAMES = {
    'RCTVirtualText': 'Text',
    'RCTText': 'Text',
    'RCTView': 'View',
    'RCTScrollView': 'ScrollView'
}

class ElementTreeBuilder:
    """
    Builds a tree of AppNode objects from the React Native component tree using react-native-debugger-client.
    
    This class uses the ReactNativeDebuggerClient to retrieve component information 
    from a running React Native application and constructs a tree of AppNode objects
    representing the UI elements.
    """
    def __init__(self, service_client: ReactNativeDebuggerClient):
        self.service_client = service_client
        self._id_counter = 0

    def _extract_react_native_data(self, element_data):
        """Extract React Native specific data from the component tree"""
        if not isinstance(element_data, dict):
            return {}
        
        result = {}
        
        if 'displayName' in element_data:
            result['display_name'] = element_data['displayName']
        
        if 'instance' in element_data and isinstance(element_data['instance'], dict):
            instance = element_data['instance']
            
            if 'memoizedProps' in instance:
                result['props'] = instance['memoizedProps']
            
            if 'memoizedState' in instance:
                result['state'] = instance['memoizedState']
        
        if 'fiber' in element_data and isinstance(element_data['fiber'], dict):
            fiber = element_data['fiber']
            
            if 'type' in fiber:
                result['type'] = fiber['type']
            
            if 'memoizedProps' in fiber and not result.get('props'):
                result['props'] = fiber['memoizedProps']
        
        return result

    def build_element_tree(self, object_group="react-native"):
        """Build a tree of AppNode objects from the React Native component tree"""
        self._id_counter = 0
        
        try:
            logger.info("Requesting UI tree from React Native app...")
            ui_tree = self.service_client.get_ui_tree()
            
            if not ui_tree:
                logger.warning("Received empty UI tree from React Native app")
                return NodeState(element_tree=None, selector_map={})
            
            if isinstance(ui_tree, dict) and 'error' in ui_tree:
                logger.warning(f"Failed to get UI tree: {ui_tree.get('error')}")
                return NodeState(element_tree=None, selector_map={})
            
            if isinstance(ui_tree, dict):
                logger.info(f"UI tree root: type={ui_tree.get('type', 'Unknown')}, has_children={bool(ui_tree.get('children'))}")
                if 'children' in ui_tree and isinstance(ui_tree['children'], list):
                    logger.info(f"Root has {len(ui_tree['children'])} direct children")
                    for i, child in enumerate(ui_tree['children'][:3]):  # Log first 3 children
                        if isinstance(child, dict):
                            logger.info(f"Child {i}: type={child.get('type', 'Unknown')}")
            
            rn_data = self._extract_react_native_data(ui_tree)
            if rn_data:
                logger.info(f"Found React Native specific data: {json.dumps(rn_data)[:200]}...")
            
            raw_tree_str = json.dumps(ui_tree)[:1000] if isinstance(ui_tree, (dict, list)) else str(ui_tree)[:1000]
            logger.debug(f"Raw UI tree (truncated): {raw_tree_str}...")
            
            logger.info("Parsing component structure...")
            root_node = self._parse_element_structure(ui_tree, None, object_group)
            
            if not root_node:
                logger.warning("Failed to parse component structure: no root node")
                return NodeState(element_tree=None, selector_map={})
            
            logger.info("Collecting all nodes...")
            all_nodes = self._collect_all_nodes(root_node)
            
            logger.info(f"Collected {len(all_nodes)} total nodes before filtering")
            
            if len(all_nodes) <= 15: # Log more verbosely for smaller trees
                for node in all_nodes:
                    node_type = getattr(node, 'node_type', 'Unknown')
                    node_text = getattr(node, 'text', None)
                    child_ids = [c.unique_id for c in node.child_nodes] if hasattr(node, 'child_nodes') else []
                    logger.info(f"Node (pre-filter/hierarchy): id={node.unique_id}, type={node_type}, text='{node_text}', children={child_ids}")
            
            logger.info("Post-processing to extract more text from hierarchy...")
            self._extract_text_from_hierarchy(all_nodes) # Ensure this is called
            
            logger.info("Filtering nodes...")
            relevant_nodes = self._filter_relevant_nodes(all_nodes)
            
            logger.info("Pruning redundant containers...")
            pruned_nodes = self._prune_redundant_views(relevant_nodes)
            
            self._setup_sibling_relationships(pruned_nodes)
            
            selector_map: SelectorMap = {node.unique_id: node for node in pruned_nodes}
            
            logger.info(
                "Built element tree with %s total nodes, filtered to %s relevant nodes, pruned to %s nodes",
                len(all_nodes),
                len(relevant_nodes),
                len(pruned_nodes),
            )
            
            return NodeState(element_tree=root_node, selector_map=selector_map)
            
        except Exception as e:
            logger.error(f"Error building element tree: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return NodeState(element_tree=None, selector_map={})

    def _extract_text_from_numbered_props(self, props):
        """Extract text from numbered properties (used in React Native text nodes)"""
        if not isinstance(props, dict):
            return None
            
        numbered_keys = [k for k in props.keys() if isinstance(k, str) and k.isdigit()]
        if not numbered_keys:
            return None
            
        numbered_keys.sort(key=lambda x: int(x))
        text_parts = []
        
        for k in numbered_keys:
            value = props[k]
            if isinstance(value, str):
                text_parts.append(value)
            else:
                text_parts.append(str(value))
        
        return ''.join(text_parts)

    def _extract_text_from_text_children(self, children_data, depth=0, max_depth=10, visited_children_reprs=None):
        """Extract text from a list of children with cycle detection."""
        if visited_children_reprs is None:
            visited_children_reprs = set()

        if depth > max_depth:
            logger.warning(f"Max depth {max_depth} reached in _extract_text_from_text_children for item: {str(children_data)[:60]}")
            return None
            
        if not isinstance(children_data, list):
            logger.debug(f"_extract_text_from_text_children expects a list, got {type(children_data)}")
            return None 
            
        text_parts = []
        
        for child_element in children_data:
            if isinstance(child_element, str):
                stripped_child_str = child_element.strip()
                if stripped_child_str: 
                    text_parts.append(stripped_child_str)
                continue
            
            if not isinstance(child_element, dict):
                continue

            try:
                child_repr_str = json.dumps(child_element, sort_keys=True)
            except TypeError:
                child_repr_str = str(child_element)
            
            child_hash = hash(child_repr_str[:200])

            if child_hash in visited_children_reprs:
                logger.debug(f"Skipping already visited child (cycle based on hash) in _extract_text_from_text_children: {child_repr_str[:60]}")
                continue
            visited_children_reprs.add(child_hash)
            
            current_child_text_parts = []

            if 'text' in child_element and isinstance(child_element['text'], str) and child_element['text'].strip():
                current_child_text_parts.append(child_element['text'].strip())
            
            child_props = child_element.get('props', {})
            if isinstance(child_props, dict):
                numbered_text = self._extract_text_from_numbered_props(child_props)
                if numbered_text and numbered_text.strip():
                    current_child_text_parts.append(numbered_text.strip())
                
                if 'children' in child_props and isinstance(child_props['children'], str) and child_props['children'].strip():
                    current_child_text_parts.append(child_props['children'].strip())
                elif 'children' in child_props and isinstance(child_props['children'], list):
                    nested_text_from_props_children = self._extract_text_from_text_children(
                        child_props['children'], depth + 1, max_depth, visited_children_reprs.copy()
                    )
                    if nested_text_from_props_children and nested_text_from_props_children.strip():
                        current_child_text_parts.append(nested_text_from_props_children.strip())

                for text_prop_key in ['accessibilityLabel', 'label', 'title', 'placeholder', 'value']:
                    prop_val = child_props.get(text_prop_key)
                    if prop_val and isinstance(prop_val, str) and prop_val.strip():
                        current_child_text_parts.append(prop_val.strip())
            
            if 'children' in child_element and isinstance(child_element['children'], list):
                is_same_children_list = isinstance(child_props, dict) and child_props.get('children') is child_element['children']
                if not is_same_children_list:
                    nested_text_from_el_children = self._extract_text_from_text_children(
                        child_element['children'], depth + 1, max_depth, visited_children_reprs.copy()
                    )
                    if nested_text_from_el_children and nested_text_from_el_children.strip():
                        current_child_text_parts.append(nested_text_from_el_children.strip())
            
            if current_child_text_parts:
                text_parts.append(" ".join(filter(None, current_child_text_parts)).strip())

        if text_parts:
            return " ".join(filter(None, text_parts)).strip()
        
        return None

    def _extract_deep_memoized_props(self, element_data, visited=None):
        """Extract text deeply from memoizedProps in React components"""
        if visited is None:
            visited = set()
        
        if not isinstance(element_data, dict) or id(element_data) in visited:
            return None
        
        visited.add(id(element_data))
        
        if 'text' in element_data and isinstance(element_data['text'], str):
            return element_data['text']
        
        text = None
        
        if 'memoizedProps' in element_data:
            props = element_data['memoizedProps']
            
            if isinstance(props, str):
                return props
            
            if isinstance(props, dict):
                for key in ['text', 'children', 'value', 'label', 'title', 'placeholder']:
                    if key in props:
                        if isinstance(props[key], str):
                            return props[key]
                        elif isinstance(props[key], dict):
                            nested_text = self._extract_deep_memoized_props(props[key], visited)
                            if nested_text:
                                return nested_text
                        elif isinstance(props[key], list):
                            text_parts = []
                            for item in props[key]:
                                if isinstance(item, str):
                                    text_parts.append(item)
                                elif isinstance(item, dict):
                                    nested_text = self._extract_deep_memoized_props(item, visited)
                                    if nested_text:
                                        text_parts.append(nested_text)
                            if text_parts:
                                return ''.join(text_parts)
        
        if 'props' in element_data and isinstance(element_data['props'], dict):
            props = element_data['props']
            
            for key in ['text', 'children', 'value', 'label', 'title', 'placeholder']:
                if key in props:
                    if isinstance(props[key], str):
                        return props[key]
                    elif isinstance(props[key], dict):
                        nested_text = self._extract_deep_memoized_props(props[key], visited)
                        if nested_text:
                            return nested_text
                    elif isinstance(props[key], list):
                        text_parts = []
                        for item in props[key]:
                            if isinstance(item, str):
                                text_parts.append(item)
                            elif isinstance(item, dict):
                                nested_text = self._extract_deep_memoized_props(item, visited)
                                if nested_text:
                                    text_parts.append(nested_text)
                        if text_parts:
                            return ''.join(text_parts)
        
        if 'stateNode' in element_data and isinstance(element_data['stateNode'], dict):
            state_node = element_data['stateNode']
            return self._extract_deep_memoized_props(state_node, visited)
        
        for key in ['child', 'sibling']:
            if key in element_data and isinstance(element_data[key], dict):
                child_text = self._extract_deep_memoized_props(element_data[key], visited)
                if child_text:
                    return child_text
        
        return text

    def _parse_element_structure(self, element_data, parent, object_group, processed_nodes=None, depth=0):
        """Parse a component from the React Native UI tree with cycle detection"""
        if processed_nodes is None:
            processed_nodes = set()
        
        if depth > 150:
            logger.warning(f"Reached maximum recursion depth in _parse_element_structure at depth {depth} for element: {str(element_data)[:100]}")
            return None
        
        current_unique_id = self._id_counter
        self._id_counter += 1

        if isinstance(element_data, str):
            if element_data.strip():
                return AppTextNode(
                    unique_id=current_unique_id,
                    text=element_data.strip(),
                    parent=parent,
                )
            return None 

        if not isinstance(element_data, dict):
            logger.debug(f"Skipping non-dictionary element: {str(element_data)[:100]} at depth {depth}")
            if element_data is not None:
                 return AppElementNode(
                    unique_id=current_unique_id,
                    node_type="UnknownPrimitive", 
                    is_interactive=False,
                    properties={'value': str(element_data)[:100]}, 
                    parent_node=parent
                )
            return None

        node_type_from_element = element_data.get('type')
        display_name = element_data.get('displayName')
        
        node_type = display_name or node_type_from_element or 'Unknown'
        
        props = element_data.get('props', {})
        if not isinstance(props, dict):
            props = {}

        text = None
        key = element_data.get('key') or props.get('key')
        test_id = props.get('testID')

        if 'text' in element_data and isinstance(element_data['text'], str) and element_data['text'].strip():
            text = element_data['text'].strip()
            logger.debug(f"Extracted text '{text}' from element_data.text for node_type {node_type}")

        if not text:
            deep_text = self._extract_deep_memoized_props(element_data)
            if deep_text and isinstance(deep_text, str) and deep_text.strip():
                text = deep_text.strip()
                logger.debug(f"Extracted text '{text}' from _extract_deep_memoized_props for node_type {node_type}")
            
        if not text:
            acc_label = props.get('accessibilityLabel')
            if acc_label and isinstance(acc_label, str) and acc_label.strip():
                text = acc_label.strip()
                logger.debug(f"Extracted text '{text}' from accessibilityLabel for node_type {node_type}")

        if not text:
            for text_prop_key in ['label', 'title', 'placeholder', 'value', 'alt', 'caption', 'aria-label']:
                prop_val = props.get(text_prop_key)
                if prop_val and isinstance(prop_val, str) and prop_val.strip():
                    text = prop_val.strip()
                    logger.debug(f"Extracted text '{text}' from props.{text_prop_key} for node_type {node_type}")
                    break
        
        if not text:
            text_from_numbered = self._extract_text_from_numbered_props(props)
            if text_from_numbered and text_from_numbered.strip():
                text = text_from_numbered.strip()
                logger.debug(f"Extracted text '{text}' from numbered props for node_type {node_type}")

        if not text and 'children' in props and isinstance(props['children'], str) and props['children'].strip():
            text = props['children'].strip()
            logger.debug(f"Extracted text '{text}' from props.children (string) for node_type {node_type}")
        
        if not text and 'children' in element_data and isinstance(element_data['children'], str) and element_data['children'].strip():
            text = element_data['children'].strip()
            logger.debug(f"Extracted text '{text}' from element_data.children (string) for node_type {node_type}")

        properties = {}
        for p_key, p_value in element_data.items():
            if p_key not in ['children', 'type', 'props', 'testID', 'key', 'displayName', 'text', 'instance', 'fiber', '_owner', '_store', '_source']:
                if not isinstance(p_value, (dict, list)) or isinstance(p_value, (str, int, float, bool)):
                     properties[p_key] = p_value

        if isinstance(props, dict):
            for p_key, p_value in props.items():
                if p_key not in ['children', 'accessibilityLabel', 'label', 'title', 'placeholder', 'value', 'alt', 'caption', 'style', 'className'] and p_key not in properties:
                    if not isinstance(p_value, (dict, list)) or isinstance(p_value, (str, int, float, bool)):
                        properties[p_key] = p_value
                elif isinstance(p_value, (str, int, float, bool)) and p_key not in properties:
                     properties[p_key] = p_value


        is_interactive = self._is_component_interactive(node_type, props, properties)
        clean_node_type = CANONICAL_NAMES.get(node_type, node_type)

        if clean_node_type == "Text" and text:
            current_node = AppTextNode(unique_id=current_unique_id, text=text, parent=parent)
        else:
            node_key_to_use = test_id or key
            current_node = AppElementNode(
                unique_id=current_unique_id,
                node_type=clean_node_type,
                is_interactive=is_interactive,
                properties=properties,
                parent_node=parent,
                text=text, 
                key=node_key_to_use
            )
        
        if isinstance(element_data, dict):
            element_id = id(element_data)
            if element_id in processed_nodes:
                logger.warning(f"Cycle detected: Element object with id {element_id} (type: {node_type}, key: {key}) at depth {depth} already processed in this path. Skipping.")
                return None 
            processed_nodes.add(element_id)
        
        children_source = None
        if 'children' in element_data and isinstance(element_data['children'], list):
            children_source = element_data['children']
        elif 'children' in props and isinstance(props['children'], list):
            children_source = props['children']

        if children_source:
            for child_data_item in children_source:
                child_node = self._parse_element_structure(child_data_item, current_node, object_group, processed_nodes.copy(), depth + 1)
                if child_node:
                    current_node.child_nodes.append(child_node)
        
        if not current_node.text and clean_node_type in ['View', 'ThemedText', 'TextAncestorContext', 'RCTView'] and len(current_node.child_nodes) == 1:
            single_child = current_node.child_nodes[0]
            if hasattr(single_child, 'text') and single_child.text and not single_child.is_interactive:
                current_node.text = single_child.text
                logger.debug(f"Node {current_node.unique_id} ({current_node.node_type}) adopted text '{current_node.text}' from its single child {single_child.unique_id} ({single_child.node_type}).")


        if current_node.is_interactive and not current_node.text and current_node.child_nodes:
            child_texts_for_interactive = []
            for child in current_node.child_nodes:
                if hasattr(child, 'text') and child.text:
                    child_texts_for_interactive.append(child.text.strip())
            if child_texts_for_interactive:
                concatenated_text = " ".join(child_texts_for_interactive).strip()
                if concatenated_text:
                    current_node.text = concatenated_text
                    logger.debug(f"Interactive node {current_node.unique_id} ({current_node.node_type}) adopted concatenated text '{current_node.text}' from children.")
            
        return current_node
    
    def _is_component_interactive(self, node_type, props, properties):
        """Determine if a component is interactive based on its type and props"""
        interactive_components = [
            'Button', 'TouchableOpacity', 'TouchableHighlight', 'TouchableWithoutFeedback',
            'TouchableNativeFeedback', 'Pressable', 'TouchableComponent',
            
            'TextInput', 'Switch', 'Checkbox', 'Slider', 'Input',
            
            'Picker', 'CheckBox', 'RadioButton', 'SegmentedControl', 'Select',
            
            'TabBar', 'BottomTabBar', 'DrawerItem', 'Link', 'NavigationItem',
            
            'FlatList', 'SectionList', 'ScrollView', 'VirtualizedList', 'SwipeableRow',
            
            'Form', 'FormInput', 'SelectDropdown',
        ]
        
        if any(component.lower() in node_type.lower() for component in interactive_components):
            return True
        
        if 'touchable' in node_type.lower() or 'button' in node_type.lower() or 'pressable' in node_type.lower():
            return True
        
        interactive_props = [
            'onPress', 'onLongPress', 'onPressIn', 'onPressOut',
            'onFocus', 'onBlur', 'onChange', 'onChangeText',
            'onValueChange', 'onSelect', 'onSubmitEditing',
            'onEndEditing', 'onContentSizeChange', 'onScroll',
            'onClick', 'onTap', 'onTouch', 'onSwipe',
        ]
        
        for prop in interactive_props:
            if prop in props or prop in properties:
                return True
        
        for key in props:
            if 'on' in key.lower() and ('press' in key.lower() or 'click' in key.lower() or 'touch' in key.lower()):
                return True
        
        if props.get('accessible') is True:
            return True
        
        accessibility_role = props.get('accessibilityRole', '')
        if isinstance(accessibility_role, str):
            interactive_roles = ['button', 'link', 'checkbox', 'radio', 'menuitem', 'tab', 'switch', 'slider']
            if accessibility_role.lower() in interactive_roles:
                return True
        
        if any(key in props for key in ['hitSlop', 'clickable', 'focusable', 'touchSoundDisabled']):
            return True
        
        if props.get('clickable') is True or props.get('focusable') is True:
            return True
        
        return False

    def _collect_all_nodes(self, root, visited=None):
        """Recursively collect all nodes in a flat list with cycle detection"""
        if not root:
            return []
            
        if visited is None:
            visited = set()
            
        if root.unique_id in visited:
            return []
            
        visited.add(root.unique_id)
            
        result = [root]
        for child in root.child_nodes:
            if child.unique_id not in visited:
                result.extend(self._collect_all_nodes(child, visited))
        return result

    def _setup_sibling_relationships(self, all_nodes):
        """Set up previous/next sibling relationships with safety checks"""
        nodes_by_parent = {}
        for node in all_nodes:
            parent = node.parent_node
            
            if parent is None or (hasattr(parent, 'unique_id') and parent.unique_id == node.unique_id):
                continue
                
            if parent not in nodes_by_parent:
                nodes_by_parent[parent] = []
            nodes_by_parent[parent].append(node)
        
        for parent, siblings in nodes_by_parent.items():
            for i in range(len(siblings)):
                if i > 0 and siblings[i].unique_id != siblings[i-1].unique_id:
                    siblings[i].previous_sibling = siblings[i-1]
                if i < len(siblings) - 1 and siblings[i].unique_id != siblings[i+1].unique_id:
                    siblings[i].next_sibling = siblings[i+1]

    def _filter_relevant_nodes(self, nodes):
        """Filter the component nodes to only include relevant ones"""
        if not nodes:
            return []
        
        result = []
        for node in nodes:
            if hasattr(node, 'node_type'):
                if node.node_type.startswith('_'):
                    continue
                    
                if node.node_type in IRRELEVANT_TYPES:
                    continue
                    
                if node.node_type == 'Unknown' and not getattr(node, 'text', None) and not getattr(node, 'is_interactive', False):
                    has_interactive_children = False
                    for child in node.child_nodes:
                        if getattr(child, 'is_interactive', False) or getattr(child, 'text', None):
                            has_interactive_children = True
                            break
                    if not has_interactive_children:
                        continue
                
                if node.node_type in CANONICAL_NAMES:
                    node.node_type = CANONICAL_NAMES[node.node_type]
                
                if not node.text and node.child_nodes:
                    for child in node.child_nodes:
                        if hasattr(child, 'text') and child.text:
                            node.text = child.text
                            break
                
                result.append(node)
            elif isinstance(node, AppTextNode):
                result.append(node)
        
        logger.info(f"Filtered element tree from {len(nodes)} to {len(result)} relevant nodes")
        return result

    def _extract_text_from_hierarchy(self, all_nodes):
        """Extract text from component hierarchy by analyzing parent-child relationships.
           This is a post-processing step after initial node creation.
        """
        for node in all_nodes:
            if (hasattr(node, 'text') and node.text) or isinstance(node, AppTextNode):
                continue

            if len(node.child_nodes) == 1:
                child = node.child_nodes[0]
                if hasattr(child, 'text') and child.text and not (hasattr(child, 'is_interactive') and child.is_interactive):
                    if not node.text:
                        node.text = child.text
                        logger.debug(f"Hierarchy: Node {node.unique_id} ({node.node_type}) adopted text '{node.text}' from single child {child.unique_id} ({getattr(child, 'node_type', 'Unknown')}).")

            if hasattr(node, 'is_interactive') and node.is_interactive and not node.text:
                child_texts = [child.text.strip() for child in node.child_nodes if hasattr(child, 'text') and child.text and child.text.strip()]
                if child_texts:
                    node.text = " ".join(child_texts)
                    logger.debug(f"Hierarchy: Interactive Node {node.unique_id} ({node.node_type}) adopted concatenated text '{node.text}' from children.")

            if hasattr(node, 'node_type') and node.node_type in ['Button', 'TouchableOpacity', 'Pressable', 'TouchableHighlight'] and not node.text:
                for child in node.child_nodes:
                    if hasattr(child, 'node_type') and child.node_type == 'Text' and hasattr(child, 'text') and child.text:
                        node.text = child.text.strip()
                        logger.debug(f"Hierarchy: Button-like Node {node.unique_id} ({node.node_type}) adopted text '{node.text}' from child Text node {child.unique_id}.")
                        break

            if hasattr(node, 'node_type') and node.node_type in ['ListItem', 'MenuItem', 'TabBarItem', 'NavItem'] and hasattr(node, 'properties'):
                for prop_name in ['label', 'title', 'value', 'name']:
                    prop_text = node.properties.get(prop_name)
                    if isinstance(prop_text, str) and prop_text.strip():
                        if not node.text or len(prop_text) > len(node.text):
                            node.text = prop_text.strip()
                            logger.debug(f"Hierarchy: List/Tab Item Node {node.unique_id} ({node.node_type}) adopted/updated text '{node.text}' from prop '{prop_name}'.")
                            break

    def _prune_redundant_views(self, nodes):
        """Prune redundant View containers that just pass through content."""
        nodes_to_prune = set()
        
        for node in nodes:
            if (node.node_type in ['View', 'ThemedView'] and 
                len(node.child_nodes) == 1 and 
                not node.is_interactive and 
                not node.text):
                
                child = node.child_nodes[0]
                
                if (child.node_type in ['View', 'ThemedView'] or 
                    (node.text == getattr(child, 'text', None) and not node.is_interactive)):
                    nodes_to_prune.add(node.unique_id)
                    
                    if hasattr(child, 'parent_node') and node.parent_node:
                        child.parent_node = node.parent_node
                        child.parent = node.parent_node
                        
                        if node.parent_node and hasattr(node.parent_node, 'child_nodes'):
                            for i, sibling in enumerate(node.parent_node.child_nodes):
                                if sibling.unique_id == node.unique_id:
                                    node.parent_node.child_nodes[i] = child
                                    break
        
        pruned_result = [node for node in nodes if node.unique_id not in nodes_to_prune]
        logger.info(f"Pruned {len(nodes) - len(pruned_result)} redundant view containers")
        return pruned_result
