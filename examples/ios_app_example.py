#!/usr/bin/env python3
"""
Mobile App Control Example using app_use Agent with x.ai (Grok).

This example shows how to use the Agent to control a ios mobile app using
the appium package with x.ai as the LLM. Make sure you have
a mobile app running with the appium server enabled.

Usage:
    python mobile_app_example.py
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
		'udid': 'udid'  # Hardware UDID for physical device
	}

	llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash-preview-05-20')


	app = App(
		platform_name='ios',
		device_name='Erickiphone',
		bundle_id='com.atebits.Tweetie2',
		appium_server_url='http://localhost:4723',
		**cap_kwargs,
	)

	agent = Agent(
		task='Can you like one post on? Need to first click on a post to open it then like it.',
		llm=llm,
		app=app,
		generate_gif=True,
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
	finally:
		await agent.close()
		app.close()


if __name__ == '__main__':
	asyncio.run(main())
