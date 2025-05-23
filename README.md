# App Use - AI Control for Mobile Apps
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/5be052cf-beaf-4ba7-a76a-410b32e54e18">
    <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/ed4e98b3-5f75-428a-9bba-57192e1caee8">
    <img 
      alt="App Use Interface Screenshot" 
      src="https://github.com/user-attachments/assets/ed4e98b3-5f75-428a-9bba-57192e1caee8" 
      width="600"
    >
  </picture>
</p>





<h1 align="center">Enable AI to control your mobile apps 🤖</h1>

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/erickjtorres/app_use)
[![Twitter Follow](https://img.shields.io/twitter/follow/Erick?style=social)](https://x.com/itsericktorres)

📱 App Use is the easiest way to connect AI agents with mobile applications.

Our goal is to provide a powerful yet simple interface for AI agent app automation.

> **Warning:** This project is currently under active development. APIs will change! Currently in experimental stages.


## Quick start

Git clone the project:

```bash
git clone 
```

Install the required packages using pip:

```bash
pip install -r requirements.txt
```

### Install the necessary drivers

If wanting to navigate a real device you will need to install [Appium](https://appium.io/docs/en/latest/)

If just using flutter you will need to make sure you have the flutter driver installed (see below)

### Setting up

Choose the app you want to interact with and via your preferred needs:
```python
    # Create a Flutter app instance to interact with a flutter app via Dart VM service
    # Allows you access to dev tools
    app = FlutterApp(vm_service_uri=VM_SERVICE_URI)

    #or

    # Create a mobile app instance to interact with your real device
    app = MobileApp(
        platform_name="ios",
        device_name='Your Device Name',
        bundle_id="com.apple.calculator",
        appium_server_url='http://localhost:4723',
        {"udid": 'device-id'},
    )
```

```python
import asyncio
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from app_use.agent.service import Agent
from app_use.app.app import App

async def main():
    #...Define your app before...

    agent = Agent(
        task="Compare the price of gpt-4o and DeepSeek-V3",
        app=app,
        llm=ChatOpenAI(model="gpt-4o"),
    )
    await agent.run()

asyncio.run(main())

```

Add your API keys for the provider you want to use to your .env file.

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_KEY=
GOOGLE_API_KEY=
DEEPSEEK_API_KEY=
GROK_API_KEY=
NOVITA_API_KEY=
```


### Setting Up a Flutter App for Control

1. Make sure to enable the flutter driver extension in your mobile app

```dart
import 'package:flutter_driver/driver_extension.dart';

void main() {
  enableFlutterDriverExtension();
  runApp(const HomeScreen());
}
```

2. Run your Flutter app with the VM service enabled:

```bash
flutter run
```

3. Look for the VM service URI in the console output, which looks like:
   `ws://127.0.0.1:50505/ws`


## Community & Support

Contributions are welcome! Please feel free to submit a Pull Request.

App Use is actively maintained and designed to make mobile app control as simple and reliable as possible.

        
<div align="center">
Made with ❤️ by Erick Torres
 </div>
