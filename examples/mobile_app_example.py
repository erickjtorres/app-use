#!/usr/bin/env python3
"""
Mobile App Control Example using app_use Agent with x.ai (Grok).

This example shows how to use the Agent to control a mobile app using
the appium package with x.ai as the LLM. Make sure you have 
a mobile app running with the appium server enabled.

Usage:
    python mobile_app_example.py
"""

import asyncio
import logging
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
import time

from app_use.agent.service import Agent
from app_use.app.mobile_app import MobileApp
from app_use.app.flutter_app import FlutterApp

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def main():
    api_key = os.getenv("GROK_API_KEY")
    cap_kwargs = {}
    
    # Set up x.ai (Grok) via OpenAI compatible API
    llm = ChatOpenAI(
        api_key=SecretStr(api_key),
        base_url="https://api.x.ai/v1",
        model='grok-3-beta'
    )
    
    # Create a mobile app instance
    app = MobileApp(
        platform_name="ios",
        device_name='iPhone 16',
        bundle_id="com.apple.MobileSMS",
        appium_server_url='http://localhost:4723',
        **cap_kwargs,
    )
    
    # Create an agent to control the app
    agent = Agent(
        task="Send a message to (888) 555-1212 saying `'Hey Im an agent, How are you?'",
        llm=llm,
        app=app,
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
    finally:
        await agent.close()
        app.close()

if __name__ == "__main__":
    asyncio.run(main()) 