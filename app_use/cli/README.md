# App-Use CLI Module

This module contains the command-line interface for app-use

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

### Environment Management
```bash
# Install dependencies
app-use setup

# Check environment health
app-use doctor
```

### Interactive Setup
```bash
# Full interactive setup wizard
app-use start

# Setup with debug logging
app-use start --debug
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