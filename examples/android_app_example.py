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
5. Environment variables set for LLM provider

Usage:
    python android_app_example.py
"""

import asyncio
import logging

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from app_use.agent.service import Agent
from app_use.app.app import App

load_dotenv()

logging.basicConfig(level=logging.INFO)


async def main():
	cap_kwargs = {
		'noReset': True,
	}

	llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash-preview-05-20')

	app = App(
		platform_name='Android',
		udid='emulator-5554',
		app_package='org.wikipedia',
		appium_server_url='http://localhost:4723',
		timeout=30,
		**cap_kwargs,
	)

	agent = Agent(
		task='Can you search for a article on Wikipedia?',
		llm=llm,
		app=app,
		generate_gif=True,  # Enable GIF generation for actions
	)

	try:
		history = await agent.run()

		if history.is_successful():
			print('✅ Agent successfully completed the task!')
		else:
			print("⚠️ Agent couldn't complete the task.")

		print(f'Final result: {history.final_result()}')

	except Exception as e:
		print(f'❌ Error: {e}')
		import traceback

		traceback.print_exc()
	finally:
		print('🧹 Cleaning up...')
		if 'agent' in locals():
			await agent.close()
		app.close()


if __name__ == '__main__':
	asyncio.run(main())
