from typing import Optional, Union, Tuple, Dict, List, Any, TypeVar, Generic
import os
import atexit
import logging
import time
import base64
from io import BytesIO
from PIL import Image
from app_use.nodes.appium_tree_builder import AppiumElementTreeBuilder, GestureService, VisionService
import numpy as np
import cv2
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from appium.options.ios import XCUITestOptions
from appium.options.android import UiAutomator2Options

from app_use.app.app import App
from app_use.nodes.app_node import NodeState, AppElementNode

logger = logging.getLogger("AppiumApp")


class MobileApp(App):
    """
    Implementation of App for native mobile applications using Appium
    """

    def __init__(self,
                 platform_name="Android",
                 device_name=None,
                 app_package=None,
                 app_activity=None,
                 bundle_id=None,
                 app_path=None,
                 appium_server_url="http://localhost:4723/wd/hub",
                 timeout=30,
                 **capabilities):
        self.platform_name = platform_name
        self.device_name = device_name
        self.app_package = app_package
        self.app_activity = app_activity
        self.bundle_id = bundle_id
        self.app_path = app_path
        self.appium_server_url = appium_server_url
        self.timeout = timeout
        self.additional_capabilities = capabilities

        self.driver = None
        self.element_tree_builder = None
        self.vision_service = None
        self.gesture_service = None

        if platform_name.lower() == "android":
            if not device_name:
                raise ValueError("device_name is required for Android")
            if not (app_package and app_activity) and not app_path:
                raise ValueError("Either app_package and app_activity, or app_path is required for Android")
        elif platform_name.lower() == "ios":
            if not device_name:
                raise ValueError("device_name is required for iOS")
            if not bundle_id and not app_path:
                raise ValueError("Either bundle_id or app_path is required for iOS")
        else:
            raise ValueError("platform_name must be 'Android' or 'iOS'")

        self._initialize_driver()
        atexit.register(self.close)

    def _initialize_driver(self):
        try:
            desired_caps = {
                "platformName": self.platform_name
            }

            if self.device_name:
                desired_caps["deviceName"] = self.device_name

            if self.platform_name.lower() == "android":
                if self.app_path:
                    desired_caps["app"] = os.path.abspath(self.app_path)
                else:
                    desired_caps["appPackage"] = self.app_package
                    desired_caps["appActivity"] = self.app_activity
                desired_caps["automationName"] = "UiAutomator2"
                desired_caps["autoGrantPermissions"] = True
            elif self.platform_name.lower() == "ios":
                if self.app_path:
                    desired_caps["app"] = os.path.abspath(self.app_path)
                else:
                    desired_caps["bundleId"] = self.bundle_id
                desired_caps["automationName"] = "XCUITest"
                desired_caps["autoAcceptAlerts"] = True

            desired_caps.update(self.additional_capabilities)

            logger.info(f"Initializing Appium driver with capabilities: {desired_caps}")
            if self.platform_name.lower() == "android":
                options = UiAutomator2Options().load_capabilities(desired_caps)
            else:
                options = XCUITestOptions().load_capabilities(desired_caps)
            self.driver = webdriver.Remote(self.appium_server_url, options=options)
            self.driver.implicitly_wait(self.timeout)

            self.element_tree_builder = AppiumElementTreeBuilder(self.driver)
            self.vision_service = VisionService(self.driver)
            self.gesture_service = GestureService(self.driver)

            logger.info("Appium driver initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Appium driver: {str(e)}")
            raise

    def get_app_state(self, viewport_expansion: int = 0, debug_mode: bool = False) -> NodeState:
        return self.element_tree_builder.build_element_tree(
            self.platform_name.lower(), viewport_expansion=viewport_expansion, debug_mode=debug_mode
        )

    def get_selector_map(self, viewport_expansion: int = 0, debug_mode: bool = False):
        state = self.get_app_state(viewport_expansion=viewport_expansion, debug_mode=debug_mode)
        return state.selector_map

    def click_by_highlight_index(self, highlight_index: int, viewport_expansion: int = 0, debug_mode: bool = False) -> bool:
        selector_map = self.get_selector_map(viewport_expansion=viewport_expansion, debug_mode=debug_mode)
        node = selector_map.get(highlight_index)
        if not node:
            logger.error(f"No element found with highlight_index: {highlight_index}")
            return False
        return self.click_widget_by_unique_id(self.get_app_state().selector_map, node.unique_id)

    def input_text_by_highlight_index(self, highlight_index: int, text: str, viewport_expansion: int = 0, debug_mode: bool = False) -> bool:
        selector_map = self.get_selector_map(viewport_expansion=viewport_expansion, debug_mode=debug_mode)
        node = selector_map.get(highlight_index)
        if not node:
            logger.error(f"No element found with highlight_index: {highlight_index}")
            return False
        return self.enter_text_with_unique_id(self.get_app_state().selector_map, node.unique_id, text)

    def scroll_to_highlight_index(self, highlight_index: int, viewport_expansion: int = 0, debug_mode: bool = False) -> bool:
        selector_map = self.get_selector_map(viewport_expansion=viewport_expansion, debug_mode=debug_mode)
        node = selector_map.get(highlight_index)
        if not node:
            logger.error(f"No element found with highlight_index: {highlight_index}")
            return False
        return self.scroll_into_view(self.get_app_state().selector_map, node.unique_id)

    def enter_text_with_unique_id(self, node_state: NodeState, unique_id: int, text: str) -> bool:
        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            logger.error(f"No element found with unique_id: {unique_id}")
            return False

        self.ensure_widget_visible(node_state, unique_id)
        logger.info(f"Attempting to enter text in {target_node.node_type}")

        if target_node.key:
            try:
                logger.info(f"Trying to enter text by key: {target_node.key}")
                if self.platform_name.lower() == "android":
                    element = self.driver.find_element(AppiumBy.ID, target_node.key)
                else:
                    element = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, target_node.key)
                element.clear()
                element.send_keys(text)
                logger.info("Successfully entered text using key")
                return True
            except Exception as e:
                logger.error(f"Error entering text by key: {str(e)}")

        if target_node.text:
            try:
                logger.info(f"Trying to enter text by text: '{target_node.text}'")
                if self.platform_name.lower() == "android":
                    element = self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{target_node.text}")')
                else:
                    element = self.driver.find_element(AppiumBy.XPATH, f'//*[@name="{target_node.text}" or @label="{target_node.text}" or @value="{target_node.text}"]')
                element.clear()
                element.send_keys(text)
                logger.info("Successfully entered text using text content")
                return True
            except Exception as e:
                logger.error(f"Error entering text by text: {str(e)}")

        try:
            logger.info(f"Trying to enter text by type: {target_node.node_type}")
            if self.platform_name.lower() == "android":
                element = self.driver.find_element(AppiumBy.CLASS_NAME, target_node.node_type)
            else:
                element = self.driver.find_element(AppiumBy.CLASS_NAME, target_node.node_type)
            element.clear()
            element.send_keys(text)
            logger.info("Successfully entered text using type")
            return True
        except Exception as e:
            logger.error(f"Error entering text by type: {str(e)}")

        try:
            logger.info("Trying to enter text by XPath")
            xpath = self._build_xpath_for_node(target_node)
            element = self.driver.find_element(AppiumBy.XPATH, xpath)
            element.clear()
            element.send_keys(text)
            logger.info("Successfully entered text using XPath")
            return True
        except Exception as e:
            logger.error(f"Error entering text by XPath: {str(e)}")

        logger.error(f"Failed to enter text in element with unique_id: {unique_id}")
        return False

    def click_widget_by_unique_id(self, node_state: NodeState, unique_id: int) -> bool:
        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            for node in node_state.selector_map.values():
                if getattr(node, "unique_id", None) == unique_id:
                    target_node = node
                    break

        if not target_node:
            logger.error(f"No element found with unique_id (or highlight index) {unique_id}")
            return False

        self.ensure_widget_visible(node_state, unique_id)
        logger.info(f"Attempting to click on {target_node.node_type}")

        if target_node.key:
            try:
                logger.info(f"Trying to click by key: {target_node.key}")
                if self.platform_name.lower() == "android":
                    element = self.driver.find_element(AppiumBy.ID, target_node.key)
                else:
                    element = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, target_node.key)
                element.click()
                logger.info("Successfully clicked using key")
                return True
            except Exception as e:
                logger.error(f"Error clicking by key: {str(e)}")

        if target_node.text:
            try:
                logger.info(f"Trying to click by text: '{target_node.text}'")
                if self.platform_name.lower() == "android":
                    element = self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{target_node.text}")')
                else:
                    if target_node.node_type == "XCUIElementTypeCell":
                        cell_xpath = f'//XCUIElementTypeCell[@label="{target_node.text}" or @name="{target_node.text}" or @value="{target_node.text}"]'
                        logger.info(f"Trying to click iOS cell with XPath: {cell_xpath}")
                        element = self.driver.find_element(AppiumBy.XPATH, cell_xpath)
                    else:
                        element = self.driver.find_element(AppiumBy.XPATH, f'//*[@name="{target_node.text}" or @label="{target_node.text}" or @value="{target_node.text}"]')
                element.click()
                logger.info("Successfully clicked using text content")
                return True
            except Exception as e:
                logger.error(f"Error clicking by text: {str(e)}")

        try:
            logger.info(f"Trying to click by type: {target_node.node_type}")
            if self.platform_name.lower() == "android":
                element = self.driver.find_element(AppiumBy.CLASS_NAME, target_node.node_type)
            else:
                element = self.driver.find_element(AppiumBy.CLASS_NAME, target_node.node_type)
            element.click()
            logger.info("Successfully clicked using type")
            return True
        except Exception as e:
            logger.error(f"Error clicking by type: {str(e)}")

        try:
            logger.info("Trying to click by XPath")
            xpath = self._build_xpath_for_node(target_node)
            logger.info(f"Using fallback XPath: {xpath}")
            element = self.driver.find_element(AppiumBy.XPATH, xpath)
            element.click()
            logger.info("Successfully clicked using XPath")
            return True
        except Exception as e:
            logger.error(f"Error clicking by XPath: {str(e)}")

        if target_node.text:
            try:
                logger.info(f"Trying vision-based click for text: '{target_node.text}'")
                success = self.vision_service.tap_text_on_screen(target_node.text)
                if success:
                    logger.info("Successfully clicked using vision-based text detection")
                    return True
            except Exception as e:
                logger.error(f"Error with vision-based click: {str(e)}")

        logger.error(f"Failed to click on element with unique_id: {unique_id}")
        return False

    def scroll_into_view(self, node_state: NodeState, unique_id: int) -> bool:
        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            logger.error(f"No element found with unique_id: {unique_id}")
            return False

        logger.info(f"Attempting to scroll into view: {target_node.node_type}")

        try:
            if self.platform_name.lower() == "android":
                if target_node.text:
                    logger.info(f"Trying to scroll to text: '{target_node.text}'")
                    self.driver.find_element(
                        AppiumBy.ANDROID_UIAUTOMATOR,
                        f'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().text("{target_node.text}"))'
                    )
                    return True
                elif target_node.key:
                    logger.info(f"Trying to scroll to resource-id: {target_node.key}")
                    self.driver.find_element(
                        AppiumBy.ANDROID_UIAUTOMATOR,
                        f'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().resourceId("{target_node.key}"))'
                    )
                    return True
                else:
                    logger.info(f"Trying to scroll to class name: {target_node.node_type}")
                    self.driver.find_element(
                        AppiumBy.ANDROID_UIAUTOMATOR,
                        f'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().className("{target_node.node_type}"))'
                    )
                    return True
            elif self.platform_name.lower() == "ios":
                if target_node.text:
                    logger.info(f"Trying to scroll to text: '{target_node.text}'")
                    self.driver.execute_script(
                        'mobile: scroll',
                        {'direction': 'down', 'predicateString': f'label == "{target_node.text}" OR name == "{target_node.text}" OR value == "{target_node.text}"'}
                    )
                    return True
                elif target_node.key:
                    logger.info(f"Trying to scroll to accessibility id: {target_node.key}")
                    self.driver.execute_script(
                        'mobile: scroll',
                        {'direction': 'down', 'predicateString': f'name == "{target_node.key}"'}
                    )
                    return True
                else:
                    logger.info(f"Trying to scroll to type: {target_node.node_type}")
                    self.driver.execute_script(
                        'mobile: scroll',
                        {'direction': 'down', 'predicateString': f'type == "{target_node.node_type}"'}
                    )
                    return True
        except Exception as e:
            logger.error(f"Error scrolling to element: {str(e)}")

        try:
            logger.info("Trying generic scroll down")
            size = self.driver.get_window_size()
            start_x = size['width'] // 2
            start_y = size['height'] * 3 // 4
            end_x = size['width'] // 2
            end_y = size['height'] // 4
            self.gesture_service.swipe(start_x, start_y, end_x, end_y, 300)

            new_node_state = self.get_app_state()
            if unique_id in new_node_state.selector_map:
                logger.info("Successfully scrolled element into view")
                return True

            logger.info("Trying generic scroll up")
            self.gesture_service.swipe(start_x, end_y, start_x, start_y, 300)

            new_node_state = self.get_app_state()
            if unique_id in new_node_state.selector_map:
                logger.info("Successfully scrolled element into view")
                return True
        except Exception as e:
            logger.error(f"Error with generic scroll: {str(e)}")

        logger.error(f"Failed to scroll element with unique_id: {unique_id} into view")
        return False

    def scroll_up_or_down(self, node_state: NodeState, unique_id: int, direction: str = "down") -> bool:
        if direction not in ["up", "down"]:
            logger.error(f"Invalid direction: {direction}. Valid options are 'up' or 'down'.")
            return False

        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            logger.error(f"No element found with unique_id: {unique_id}")
            return False

        logger.info(f"Attempting to scroll {direction}: {target_node.node_type}")

        try:
            element = None
            if target_node.key:
                try:
                    if self.platform_name.lower() == "android":
                        element = self.driver.find_element(AppiumBy.ID, target_node.key)
                    else:
                        element = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, target_node.key)
                except Exception:
                    pass

            if not element and target_node.text:
                try:
                    if self.platform_name.lower() == "android":
                        element = self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{target_node.text}")')
                    else:
                        element = self.driver.find_element(AppiumBy.XPATH, f'//*[@name="{target_node.text}" or @label="{target_node.text}" or @value="{target_node.text}"]')
                except Exception:
                    pass

            if not element:
                try:
                    xpath = self._build_xpath_for_node(target_node)
                    element = self.driver.find_element(AppiumBy.XPATH, xpath)
                except Exception:
                    pass

            if element:
                rect = element.rect
                start_x = rect['x'] + rect['width'] // 2
                end_x = start_x
                if direction == "down":
                    start_y = rect['y'] + rect['height'] * 3 // 4
                    end_y = rect['y'] + rect['height'] // 4
                else:
                    start_y = rect['y'] + rect['height'] // 4
                    end_y = rect['y'] + rect['height'] * 3 // 4
                self.gesture_service.swipe(start_x, start_y, end_x, end_y, 300)
                logger.info(f"Successfully scrolled {direction} on element")
                return True

            logger.info(f"Element not found, trying generic scroll {direction}")
            size = self.driver.get_window_size()
            start_x = size['width'] // 2
            end_x = start_x
            if direction == "down":
                start_y = size['height'] * 3 // 4
                end_y = size['height'] // 4
            else:
                start_y = size['height'] // 4
                end_y = size['height'] * 3 // 4
            self.gesture_service.swipe(start_x, start_y, end_x, end_y, 300)
            logger.info(f"Successfully performed generic scroll {direction}")
            return True
        except Exception as e:
            logger.error(f"Error scrolling {direction}: {str(e)}")
            return False

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
        if direction not in ["up", "down"]:
            logger.error(f"Invalid direction: {direction}. Valid options are 'up' or 'down'.")
            return False

        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            logger.error(f"No element found with unique_id: {unique_id}")
            return False

        logger.info(f"Attempting extended scroll {direction}: {target_node.node_type}")

        try:
            element = None
            if target_node.key:
                try:
                    if self.platform_name.lower() == "android":
                        element = self.driver.find_element(AppiumBy.ID, target_node.key)
                    else:
                        element = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, target_node.key)
                except Exception:
                    pass

            if not element and target_node.text:
                try:
                    if self.platform_name.lower() == "android":
                        element = self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{target_node.text}")')
                    else:
                        element = self.driver.find_element(AppiumBy.XPATH, f'//*[@name="{target_node.text}" or @label="{target_node.text}" or @value="{target_node.text}"]')
                except Exception:
                    pass

            if not element:
                try:
                    xpath = self._build_xpath_for_node(target_node)
                    element = self.driver.find_element(AppiumBy.XPATH, xpath)
                except Exception:
                    pass

            if element:
                rect = element.rect
                start_x = rect['x'] + rect['width'] // 2
                end_x = start_x + dx
                if direction == "down":
                    start_y = rect['y'] + rect['height'] * 3 // 4
                    end_y = start_y - dy
                else:
                    start_y = rect['y'] + rect['height'] // 4
                    end_y = start_y + dy
                duration_ms = duration_microseconds // 1000
                self.gesture_service.swipe(start_x, start_y, end_x, end_y, duration_ms)
                logger.info(f"Successfully performed extended scroll {direction} on element")
                return True

            logger.info(f"Element not found, trying generic extended scroll {direction}")
            size = self.driver.get_window_size()
            start_x = size['width'] // 2
            end_x = start_x + dx
            if direction == "down":
                start_y = size['height'] * 3 // 4
                end_y = start_y - dy
            else:
                start_y = size['height'] // 4
                end_y = start_y + dy
            duration_ms = duration_microseconds // 1000
            self.gesture_service.swipe(start_x, start_y, end_x, end_y, duration_ms)
            logger.info(f"Successfully performed generic extended scroll {direction}")
            return True
        except Exception as e:
            logger.error(f"Error performing extended scroll {direction}: {str(e)}")
            return False

    def ensure_widget_visible(self, node_state: NodeState, unique_id: int) -> bool:
        target_node = node_state.selector_map.get(unique_id)

        if not target_node:
            logger.error(f"No element found with unique_id: {unique_id}")
            return False

        logger.info(f"Ensuring widget is visible: {target_node.node_type}")

        try:
            if target_node.key:
                try:
                    if self.platform_name.lower() == "android":
                        element = self.driver.find_element(AppiumBy.ID, target_node.key)
                    else:
                        element = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, target_node.key)
                    if element.is_displayed():
                        logger.info("Element is already visible")
                        return True
                except Exception:
                    pass

            if target_node.text:
                try:
                    if self.platform_name.lower() == "android":
                        element = self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{target_node.text}")')
                    else:
                        element = self.driver.find_element(AppiumBy.XPATH, f'//*[@name="{target_node.text}" or @label="{target_node.text}" or @value="{target_node.text}"]')
                    if element.is_displayed():
                        logger.info("Element is already visible")
                        return True
                except Exception:
                    pass

            try:
                xpath = self._build_xpath_for_node(target_node)
                element = self.driver.find_element(AppiumBy.XPATH, xpath)
                if element.is_displayed():
                    logger.info("Element is already visible")
                    return True
            except Exception:
                pass

            logger.info("Element is not visible, scrolling into view")
            return self.scroll_into_view(node_state, unique_id)
        except Exception as e:
            logger.error(f"Error ensuring widget visibility: {str(e)}")
            return False

    def _build_xpath_for_node(self, node):
        xpath_parts = []
        if self.platform_name.lower() == "android":
            xpath_parts.append(f"@class='{node.node_type}'")
        else:
            xpath_parts.append(f"@type='{node.node_type}'")

        if node.key:
            if self.platform_name.lower() == "android":
                xpath_parts.append(f"@resource-id='{node.key}'")
            else:
                xpath_parts.append(f"@name='{node.key}'")

        if node.text:
            if self.platform_name.lower() == "android":
                xpath_parts.append(f"@text='{node.text}'")
            else:
                xpath_parts.append(f"(@name='{node.text}' or @label='{node.text}' or @value='{node.text}')")

        xpath_condition = " and ".join(xpath_parts)
        return f"//*[{xpath_condition}]"

    def close(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Appium driver closed")
            except Exception as e:
                logger.error(f"Error closing Appium driver: {str(e)}")
            finally:
                self.driver = None
