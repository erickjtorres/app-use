# App-Use CLI Module

This module contains the command-line interface for app-use, organized using clean architecture principles and modular design.

## Architecture

The CLI module is structured into several focused components:

```
cli/
├── __init__.py          # Module exports
├── cli.py              # Main CLI orchestrator and entry point  
├── config.py           # Configuration management
├── utils.py            # Common utilities and helpers
├── start.py            # Interactive setup wizard
├── gui.py              # Textual TUI interface
├── setup.py            # Environment setup command
├── doctor.py           # Environment verification command
├── appium.py           # Appium server management
├── devices.py          # Device and app discovery
├── selection.py        # User selection prompts
└── README.md           # This file
```

## Commands

### Main Commands

- **`app-use`** - Launch the interactive GUI (default)
- **`app-use start`** - Interactive setup wizard
- **`app-use setup`** - Install and configure dependencies
- **`app-use doctor`** - Verify environment setup

### Options

- **`-p, --prompt TEXT`** - Run a single task without GUI
- **`--model TEXT`** - Specify LLM model to use
- **`--platform [Android|iOS]`** - Target platform
- **`--device-name TEXT`** - Device name or ID
- **`--app-package TEXT`** - Android app package name
- **`--bundle-id TEXT`** - iOS app bundle ID
- **`--debug`** - Enable verbose logging
- **`--version`** - Show version and exit

## Usage Examples

### Interactive Setup
```bash
# Full interactive setup wizard
app-use start

# Setup with debug logging
app-use start --debug
```

### Environment Management
```bash
# Install dependencies
app-use setup

# Check environment health
app-use doctor
```

### Direct Launch
```bash
# Launch GUI with specific configuration
app-use --platform Android --device-name emulator-5554 --app-package com.example.app

# Run single task without GUI
app-use -p "Open the settings menu" --platform iOS --device-name iPhone
```

### Model Configuration
```bash
# Use specific LLM model
app-use --model gpt-4o

# Use Claude with prompt mode
app-use -p "Take a screenshot" --model claude-3-opus-20240229
```

## Configuration

Configuration is stored in `~/.config/appuse/config.json` and includes:

- **Model settings** (LLM selection, API keys, temperature)
- **App settings** (platform, device, app identifiers)
- **Agent settings** (behavior configuration)
- **Command history** (for input history in GUI)

## Error Handling

The CLI module implements comprehensive error handling:

- **Graceful degradation** for missing dependencies
- **Clear error messages** with actionable solutions
- **Debug mode** for detailed troubleshooting
- **Cleanup procedures** for resource management

## Extensibility

The modular design allows for easy extension:

- **New commands** can be added to `cli.py`
- **Additional platforms** can be supported in `devices.py`
- **Enhanced prompts** can be implemented in `selection.py`
- **Custom configurations** can be added to `config.py`

## Dependencies

### Core Dependencies
- **click** - Command-line interface framework
- **textual** - Terminal user interface framework
- **dotenv** - Environment variable management

### LLM Dependencies
- **langchain-openai** - OpenAI integration
- **langchain-anthropic** - Anthropic integration  
- **langchain-google-genai** - Google AI integration

### System Dependencies
- **requests** - HTTP client for Appium status checks
- **subprocess** - System command execution
- **json** - Configuration file handling 