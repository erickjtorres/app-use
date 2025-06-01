import logging
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.common.actions import interaction

logger = logging.getLogger("AppGestures")


class GestureService:
    """
    Handles advanced touch gestures beyond basic taps and scrolls
    """
    
    def __init__(self, driver):
        """
        Initialize the gesture service with an Appium driver
        
        Args:
            driver: Appium WebDriver instance
        """
        self.driver = driver
        # Detect if this is an iOS driver (XCUITest doesn't support mobile gestures)
        self.is_ios = False
        try:
            caps = driver.capabilities
            self.is_ios = caps.get('platformName', '').lower() == 'ios'
        except:
            pass
    
    def swipe(self, start_x, start_y, end_x, end_y, duration=300):
        """
        Perform a swipe gesture
        
        Args:
            start_x: Starting x coordinate
            start_y: Starting y coordinate
            end_x: Ending x coordinate
            end_y: Ending y coordinate
            duration: Duration of the swipe in milliseconds
            
        Returns:
            bool: True if the swipe was performed successfully
        """
        try:
            logger.info(f"Performing swipe from ({start_x}, {start_y}) to ({end_x}, {end_y}) with duration {duration}ms")
            
            # For iOS, skip mobile gestures and go directly to W3C Actions
            if self.is_ios:
                return self._swipe_with_w3c_actions(start_x, start_y, end_x, end_y, duration)
            
            # Try W3C Mobile Gestures Commands first for Android
            try:
                self.driver.execute_script('mobile: swipeGesture', {
                    'left': min(start_x, end_x),
                    'top': min(start_y, end_y),
                    'width': abs(end_x - start_x),
                    'height': abs(end_y - start_y),
                    'direction': 'up' if start_y > end_y else 'down',
                    'percent': 0.8
                })
                logger.info("Swipe gesture completed successfully using mobile gestures")
                return True
            except Exception as mobile_error:
                logger.info(f"Mobile gesture failed, trying W3C Actions: {mobile_error}")
                return self._swipe_with_w3c_actions(start_x, start_y, end_x, end_y, duration)
                
        except Exception as e:
            logger.error(f"All swipe methods failed: {str(e)}")
            return False
    
    def _swipe_with_w3c_actions(self, start_x, start_y, end_x, end_y, duration):
        """Helper method to perform swipe using W3C Actions API"""
        try:
            touch_input = PointerInput(interaction.POINTER_TOUCH, 'touch')
            action_builder = ActionBuilder(self.driver, mouse=touch_input)
            
            # Create the swipe sequence
            action_builder.pointer_action.move_to_location(start_x, start_y)
            action_builder.pointer_action.pointer_down()
            action_builder.pointer_action.pause(duration / 1000)  # Convert ms to seconds
            action_builder.pointer_action.move_to_location(end_x, end_y)
            action_builder.pointer_action.pointer_up()
            
            action_builder.perform()
            logger.info("Swipe gesture completed successfully using W3C Actions")
            return True
        except Exception as w3c_error:
            logger.info(f"W3C Actions failed, trying legacy method: {w3c_error}")
            
            # Final fallback to older Appium method
            self.driver.swipe(start_x, start_y, end_x, end_y, duration)
            logger.info("Swipe gesture completed successfully using fallback method")
            return True
    
    def pinch(self, element=None, percent=50, steps=10):
        """
        Perform a pinch gesture
        
        Args:
            element: Element to pinch (optional)
            percent: Pinch percentage (0-100)
            steps: Number of steps in the gesture
            
        Returns:
            bool: True if the pinch was performed successfully
        """
        try:
            if element:
                rect = element.rect
                center_x = rect['x'] + rect['width'] // 2
                center_y = rect['y'] + rect['height'] // 2
                
                distance = min(rect['width'], rect['height']) // 4
                left_x = center_x - distance
                left_y = center_y
                right_x = center_x + distance
                right_y = center_y
            else:
                # Use screen center and dimensions
                size = self.driver.get_window_size()
                center_x = size['width'] // 2
                center_y = size['height'] // 2
                
                # Calculate pinch coordinates
                distance = min(size['width'], size['height']) // 4
                left_x = center_x - distance
                left_y = center_y
                right_x = center_x + distance
                right_y = center_y
            
            # For iOS, skip mobile gestures and use dual swipe approach
            if self.is_ios:
                return self._pinch_with_dual_swipe(center_x, center_y, left_x, left_y, right_x, right_y, percent)
            
            # Try mobile gesture first for Android
            try:
                gesture_type = 'pinchCloseGesture' if percent < 50 else 'pinchOpenGesture'
                self.driver.execute_script(f'mobile: {gesture_type}', {
                    'left': left_x,
                    'top': center_y - distance//2,
                    'width': distance * 2,
                    'height': distance,
                    'percent': abs(percent - 50) / 50
                })
                return True
            except Exception:
                logger.info("Mobile pinch gesture failed, using dual swipe approach")
                return self._pinch_with_dual_swipe(center_x, center_y, left_x, left_y, right_x, right_y, percent)
                
        except Exception as e:
            logger.error(f"Error performing pinch: {str(e)}")
            return False
    
    def _pinch_with_dual_swipe(self, center_x, center_y, left_x, left_y, right_x, right_y, percent):
        """Helper method to perform pinch using dual swipe approach"""
        if percent < 50:  # Pinch in - swipe from sides to center
            # Perform two simultaneous swipes toward center
            success1 = self.swipe(left_x, left_y, center_x, center_y, 500)
            success2 = self.swipe(right_x, right_y, center_x, center_y, 500)
            return success1 and success2
        else:  # Pinch out - swipe from center to sides
            # Perform two simultaneous swipes away from center
            success1 = self.swipe(center_x, center_y, left_x, left_y, 500)
            success2 = self.swipe(center_x, center_y, right_x, right_y, 500)
            return success1 and success2
    
    def zoom(self, element=None, percent=200, steps=10):
        """
        Perform a zoom gesture
        
        Args:
            element: Element to zoom (optional)
            percent: Zoom percentage (100-300)
            steps: Number of steps in the gesture
            
        Returns:
            bool: True if the zoom was performed successfully
        """
        try:
            # Zoom is essentially a pinch out
            return self.pinch(element, 100, steps)
        except Exception as e:
            logger.error(f"Error performing zoom: {str(e)}")
            return False
    
    def long_press(self, x, y, duration=1000):
        """
        Perform a long press gesture
        
        Args:
            x: x coordinate
            y: y coordinate
            duration: Duration of the long press in milliseconds
            
        Returns:
            bool: True if the long press was performed successfully
        """
        try:
            # For iOS, skip mobile gestures and go directly to W3C Actions
            if self.is_ios:
                return self._long_press_with_w3c_actions(x, y, duration)
            
            # Try mobile gesture first for Android
            try:
                self.driver.execute_script('mobile: longClickGesture', {
                    'x': x, 
                    'y': y, 
                    'duration': duration
                })
                return True
            except Exception:
                return self._long_press_with_w3c_actions(x, y, duration)
                
        except Exception as e:
            logger.error(f"Error performing long press: {str(e)}")
            return False
    
    def _long_press_with_w3c_actions(self, x, y, duration):
        """Helper method to perform long press using W3C Actions API"""
        try:
            touch_input = PointerInput(interaction.POINTER_TOUCH, 'touch')
            action_builder = ActionBuilder(self.driver, mouse=touch_input)
            
            # Perform long press
            action_builder.pointer_action.move_to_location(x, y)
            action_builder.pointer_action.pointer_down()
            action_builder.pointer_action.pause(duration/1000)  # Convert ms to seconds
            action_builder.pointer_action.pointer_up()
            
            action_builder.perform()
            return True
        except Exception as e:
            logger.error(f"Error performing long press with W3C Actions: {e}")
            return False
    
    def drag_and_drop(self, start_x, start_y, end_x, end_y, duration=1000):
        """
        Perform a drag and drop gesture
        
        Args:
            start_x: Starting x coordinate
            start_y: Starting y coordinate
            end_x: Ending x coordinate
            end_y: Ending y coordinate
            duration: Duration of the drag in milliseconds
            
        Returns:
            bool: True if the drag and drop was performed successfully
        """
        try:
            # For iOS, skip mobile gestures and go directly to W3C Actions
            if self.is_ios:
                return self._drag_and_drop_with_w3c_actions(start_x, start_y, end_x, end_y, duration)
            
            # Try mobile gesture first for Android
            try:
                self.driver.execute_script('mobile: dragGesture', {
                    'startX': start_x,
                    'startY': start_y,
                    'endX': end_x,
                    'endY': end_y,
                    'speed': 500
                })
                return True
            except Exception:
                return self._drag_and_drop_with_w3c_actions(start_x, start_y, end_x, end_y, duration)
                
        except Exception as e:
            logger.error(f"Error performing drag and drop: {str(e)}")
            return False
    
    def _drag_and_drop_with_w3c_actions(self, start_x, start_y, end_x, end_y, duration):
        """Helper method to perform drag and drop using W3C Actions API"""
        try:
            touch_input = PointerInput(interaction.POINTER_TOUCH, 'touch')
            action_builder = ActionBuilder(self.driver, mouse=touch_input)
            
            # Perform drag and drop
            action_builder.pointer_action.move_to_location(start_x, start_y)
            action_builder.pointer_action.pointer_down()
            action_builder.pointer_action.pause(0.1)  # Brief pause after touch down
            action_builder.pointer_action.move_to_location(end_x, end_y)
            action_builder.pointer_action.pointer_up()
            
            action_builder.perform()
            return True
        except Exception as e:
            logger.error(f"Error performing drag and drop with W3C Actions: {e}")
            return False