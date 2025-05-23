#!/usr/bin/env python3
"""
React App Control Example using app_use Agent with x.ai (Grok).

This example shows how to use the Agent to control a React app using
the dart-vm-client package with x.ai as the LLM. Make sure you have 
a React app running with the VM service enabled.

Usage:
    python react_agent_example.py
"""

import asyncio
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app_use.agent.service import Agent
from app_use.app.react_native_app import ReactNativeApp


load_dotenv()

async def main():
    api_key = os.getenv("GROK_API_KEY")
    
    
    llm = ChatOpenAI(
        api_key=SecretStr(api_key),
        base_url="https://api.x.ai/v1",
        model='grok-3-beta'
    )
    
    
    app = ReactNativeApp(device_ip="localhost", metro_port=8081)
    
    app_state = app.get_app_state()
    print(app_state)
    
    
    agent = Agent(
        task="What do you see on the screen?", 
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