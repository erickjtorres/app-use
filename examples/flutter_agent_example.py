#!/usr/bin/env python3
"""
Flutter App Control Example using app_use Agent with x.ai (Grok).

This example shows how to use the Agent to control a Flutter app using
the dart-vm-client package with x.ai as the LLM. Make sure you have 
a Flutter app running with the VM service enabled.

Usage:
    python flutter_agent_example.py
"""

import asyncio
import logging
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app_use.agent.service import Agent
from app_use.app.flutter_app import FlutterApp
from app_use.controller.service import Controller
from app_use.controller.views import ActionResult


load_dotenv()

logging.basicConfig(level=logging.DEBUG)


async def main():
    VM_SERVICE_URI = "ws://127.0.0.1:50640/EP9CcWgxw08=/ws"
    api_key = os.getenv("GROK_API_KEY")
    
    llm = ChatOpenAI(
        api_key=SecretStr(api_key),
        base_url="https://api.x.ai/v1",
        model='grok-3-beta'
    )
    
    app = FlutterApp(vm_service_uri=VM_SERVICE_URI)
    
    
    # Create an agent to control the app
    agent = Agent(
        task="What do you see?", 
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