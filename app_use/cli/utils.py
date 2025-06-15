"""
Common utilities and constants for app-use CLI.

Contains helper functions, constants, and shared functionality.
"""

import logging
import os
import sys
from typing import Any, Dict

import langchain_anthropic
import langchain_google_genai
import langchain_openai
from typing import List, Optional

# Logo components with styling for rich panels
APP_USE_LOGO = """
[white]  █████╗ ██████╗ ██████╗         ██╗   ██╗███████╗███████╗[/]
[white] ██╔══██╗██╔══██╗██╔══██╗        ██║   ██║██╔════╝██╔════╝[/]
[white] ███████║██████╔╝██████╔╝        ██║   ██║███████╗█████╗[/]  
[white] ██╔══██║██╔═══╝ ██╔═══╝         ██║   ██║╚════██║██╔══╝[/]  
[white] ██║  ██║██║     ██║             ╚██████╔╝███████║███████╗[/]
[white] ╚═╝  ╚═╝╚═╝     ╚═╝              ╚═════╝ ╚══════╝╚══════╝[/]
"""

# Common UI constants
TEXTUAL_BORDER_STYLES = {
    'logo': 'blue',
    'info': 'blue', 
    'input': 'orange3',
    'working': 'yellow',
    'completion': 'green'
}

# Check if readline is available
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    # readline not available on Windows by default
    READLINE_AVAILABLE = False


def setup_readline_history(history: list[str]) -> None:
    """Set up readline with command history."""
    if not READLINE_AVAILABLE:
        return

    # Add history items to readline
    for item in history:
        readline.add_history(item)


def get_llm(config: Dict[str, Any]):
    """Get the language model based on config and available API keys."""
    # Set API keys from config if available
    api_keys = config.get('model', {}).get('api_keys', {})
    model_name = config.get('model', {}).get('name')
    temperature = config.get('model', {}).get('temperature', 0.0)

    # Set environment variables if they're in the config but not in the environment
    if api_keys.get('OPENAI_API_KEY') and not os.getenv('OPENAI_API_KEY'):
        os.environ['OPENAI_API_KEY'] = api_keys['OPENAI_API_KEY']
    if api_keys.get('ANTHROPIC_API_KEY') and not os.getenv('ANTHROPIC_API_KEY'):
        os.environ['ANTHROPIC_API_KEY'] = api_keys['ANTHROPIC_API_KEY']
    if api_keys.get('GOOGLE_API_KEY') and not os.getenv('GOOGLE_API_KEY'):
        os.environ['GOOGLE_API_KEY'] = api_keys['GOOGLE_API_KEY']

    if model_name:
        if model_name.startswith('gpt'):
            if not os.getenv('OPENAI_API_KEY'):
                print('⚠️  OpenAI API key not found. Please update your config or set OPENAI_API_KEY environment variable.')
                sys.exit(1)
            return langchain_openai.ChatOpenAI(model=model_name, temperature=temperature)
        elif model_name.startswith('claude'):
            if not os.getenv('ANTHROPIC_API_KEY'):
                print('⚠️  Anthropic API key not found. Please update your config or set ANTHROPIC_API_KEY environment variable.')
                sys.exit(1)
            return langchain_anthropic.ChatAnthropic(model=model_name, temperature=temperature)
        elif model_name.startswith('gemini'):
            if not os.getenv('GOOGLE_API_KEY'):
                print('⚠️  Google API key not found. Please update your config or set GOOGLE_API_KEY environment variable.')
                sys.exit(1)
            return langchain_google_genai.ChatGoogleGenerativeAI(model=model_name, temperature=temperature)

    # Auto-detect based on available API keys
    if os.getenv('OPENAI_API_KEY'):
        return langchain_openai.ChatOpenAI(model='gpt-4o', temperature=temperature)
    elif os.getenv('ANTHROPIC_API_KEY'):
        return langchain_anthropic.ChatAnthropic(model='claude-3.5-sonnet-exp', temperature=temperature)
    elif os.getenv('GOOGLE_API_KEY'):
        return langchain_google_genai.ChatGoogleGenerativeAI(model='gemini-2.0-flash-lite', temperature=temperature)
    else:
        print(
            '⚠️  No API keys found. Please update your config or set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY.'
        )
        sys.exit(1)


def configure_logging(debug: bool = False) -> None:
    """Configure logging for the CLI application."""
    # Set environment variable for logging level
    os.environ['APP_USE_LOGGING_LEVEL'] = 'result'
    
    # Configure console logging
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S'))

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO if not debug else logging.DEBUG)
    root_logger.addHandler(console_handler)


def silence_third_party_loggers() -> None:
    """Silence noisy third-party loggers."""
    for logger_name in [
        'WDM', 'httpx', 'selenium', 'appium', 'urllib3', 'asyncio',
        'langchain', 'openai', 'httpcore', 'charset_normalizer',
        'anthropic._base_client',
    ]:
        third_party = logging.getLogger(logger_name)
        third_party.setLevel(logging.ERROR)
        third_party.propagate = False
        third_party.handlers = [] 
        

def prompt_selection(prompt: str, options: List[str], allow_empty: bool = False) -> Optional[int]:
    """Prompt user to select from a list of options."""
    if not options:
        if allow_empty:
            return None
        print("❌ No options available")
        return None
    
    print(f"\n{prompt}")
    for i, option in enumerate(options, 1):
        print(f"  {i}. {option}")
    
    while True:
        try:
            if allow_empty:
                choice = input(f"\nEnter choice (1-{len(options)}, or press Enter to skip): ").strip()
                if not choice:
                    return None
            else:
                choice = input(f"\nEnter choice (1-{len(options)}): ").strip()
            
            if choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(options):
                    return choice_num - 1
            
            print("❌ Invalid choice. Please try again.")
        except KeyboardInterrupt:
            print("\n❌ Setup cancelled")
            sys.exit(1) 