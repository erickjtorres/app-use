
![Whisk_storyboard7ea3db2beb6746db94891e4e (1)](https://github.com/user-attachments/assets/293c7ccb-62c6-40b9-9ff5-eeacaeb34aaa)


<h1 align="center">Enable AI to control your mobile apps 🤖</h1>


[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/erickjtorres/app-use)
[![Twitter Follow](https://img.shields.io/twitter/follow/Erick?style=social)](https://x.com/itsericktorres)
[![Discord](https://img.shields.io/discord/1381129368847384597?color=7289DA&label=Discord&logo=discord&logoColor=white)](https://discord.gg/V9mW8UJ6tx)


📱 App Use is the easiest way to connect AI agents with mobile applications.

Our goal is to provide a powerful yet simple interface for AI agent app automation.

## Quick start

With pip (Python>=3.11):

```bash
pip install app-use
```

For memory functionality (requires Python<3.13 due to PyTorch compatibility):  

```bash
pip install "app-use[memory]"
```

Install the necessary drivers and software: Check out our [environment setup](https://github.com/erickjtorres/app-use/blob/main/docs/env-setup.md) docs for more info!

Or feel free to try out our cli for a seamless setup:
```bash
pip install "app-use[cli]"

#install dependencies
app-use setup

# to check dependencies where installed correctly
app-use doctor
```

Define the app and mobile device you want to target:

```python
    app = App(
        platform_name="ios",
        device_name='Your Device Name',
        bundle_id="com.apple.calculator",
        appium_server_url='http://localhost:4723',
        {"udid": 'device-id'},
    )
```

Spin up your agent:

```python
import asyncio
from dotenv import load_dotenv
load_dotenv()
from app_use import Agent
from langchain_openai import ChatOpenAI

async def main():
    agent = Agent(
        task="What is 2+2?",
        llm=ChatOpenAI(model="gpt-4o"),
        app=app

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

## DEMOS

<table>
<tr>
<td width="15%">

**Ordering Shorts from the Lululemon App (iOS)**

![agent_history](https://github.com/user-attachments/assets/f6130f2e-48c6-4130-8146-1bd141ea101a)

</td>
<td width="15%">

**Ordering some tacos and a drink on DoorDash (IOS)**

![uber_eats_orders](https://github.com/user-attachments/assets/70789f61-ca55-4888-a87e-2dbba964cfc5)


</td>
</tr>
</table>


## Community & Support

Contributions are welcome! Please feel free to submit a Pull Request.

App Use is actively maintained and designed to make mobile app control as simple and reliable as possible.

        
<div align="center">
Made with ❤️ by Erick Torres
 </div>
