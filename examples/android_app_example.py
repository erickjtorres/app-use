#!/usr/bin/env python3
"""
Android App Control Example using app_use Agent with x.ai (Grok).

This example shows how to use the Agent to control an Android mobile app using
the appium package with x.ai as the LLM. Make sure you have 
an Android device/emulator running with the appium server enabled.

Prerequisites:
1. Android device connected via USB or Android emulator running
2. Appium server running (typically on http://localhost:4723)
3. Android app installed on the device/emulator
4. USB debugging enabled on Android device
5. GROK_API_KEY environment variable set

Usage:
    python android_app_example.py
"""

import asyncio
import logging
import os
import base64
import time
from io import BytesIO
from PIL import Image
import cv2
import numpy as np
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app_use.agent.service import Agent
from app_use.app.app import App
from app_use.controller.service import Controller
from app_use.controller.views import ActionResult
from app_use.nodes.app_node import NodeState

load_dotenv()

logging.basicConfig(level=logging.INFO)



#Creating actions to add to the model
controller = Controller()

@controller.action('Save Screenshot')
def save_screenshot(app: App) -> ActionResult:
    try:
        # Get the current screenshot as base64 string
        screenshot_base64 = app.take_screenshot()
        
        if not screenshot_base64:
            logging.error("Failed to get screenshot from app.")
            return ActionResult(
                success=False,
                error='Failed to get screenshot from app.',
                include_in_memory=True
            )
        
        # Decode base64 to bytes
        screenshot_bytes = base64.b64decode(screenshot_base64)
        
        # Save the screenshot to file
        screenshot_path = 'current_screenshot.png'
        with open(screenshot_path, 'wb') as f:
            f.write(screenshot_bytes)
        
        logging.info(f"Screenshot saved successfully to {screenshot_path}")
        return ActionResult(
            is_done=True,
            success=True,
            error=None,
            include_in_memory=True,
            extracted_content=f'Screenshot saved to {screenshot_path}.'
        )
    except Exception as e:
        logging.error(f"Error saving screenshot: {str(e)}")
        return ActionResult(
            success=False,
            error=f'Error saving screenshot: {str(e)}',
            include_in_memory=True
        )


async def main():
    api_key = os.getenv("GROK_API_KEY")
    
    # Android device capabilities for your specific device
    cap_kwargs = {
        "udid": 'hardware-udid',  # Your Android device UDID
        # Uncomment and set the following if needed:
        # "platformVersion": "13",  # Your Android version
        # "automationName": "UiAutomator2",  # Already set in App class
        # "autoGrantPermissions": True,  # Already set in App class
        "noReset": True,  # Don't reset app state between sessions
        # "fullReset": False,  # Don't uninstall app between sessions
    }
    
    # Set up x.ai (Grok) via OpenAI compatible API
    llm = ChatOpenAI(
        api_key=SecretStr(api_key),
        base_url="https://api.x.ai/v1",
        model='grok-3-beta'
    )
    
    # Twitter/X app configuration for your device
    app = App(
        platform_name="Android",
        device_name="VOY38B71304",  # Your device name
        app_package="com.twitter.android",  # Twitter package you found
        # app_activity is now automatically detected! No need to specify it manually
        appium_server_url='http://localhost:4723',
        timeout=30,
        **cap_kwargs,
    )

    # wait for the app to be ready
    time.sleep(5)  # Adjust as needed for your device/emulator
    
    # Create an agent to control the app
    agent = Agent(
        task="Save the screenshot of the current screen",
        llm=llm,
        app=app,
        controller=controller,
    )

    try:
        history = await agent.run()
        
        if history.is_successful():
            print("✅ Agent successfully completed the task!")
        else:
            print("⚠️ Agent couldn't complete the task.")
            
        print(f"Final result: {history.final_result()}")    
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("🧹 Cleaning up...")
        if 'agent' in locals():
            await agent.close()
        app.close()
if __name__ == "__main__":
    # Uncomment the line below to get help with finding Twitter activity info
    # get_twitter_activity_info()
    
    asyncio.run(main())