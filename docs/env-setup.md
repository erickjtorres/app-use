# Environment Setup Guide for App Testing

This guide will help you set up your environment for mobile app automation using Appium for both iOS and Android platforms.

## Prerequisites

- macOS (for iOS testing)
- Node.js (v16 or newer) and npm (for Appium)
- Java JDK 8+ (for Android)

## Appium Setup

1. Install Appium using npm:
   ```bash
   npm install -g appium
   ```

2. Start Appium server:
   ```bash
   appium
   ```

3. Install Appium Doctor to verify your setup:
   ```bash
   npm install -g appium-doctor
   appium-doctor
   ```

## iOS Setup

### Required Components

1. **Xcode** (Latest version recommended)
   - Install from the Mac App Store
   - Make sure Command Line Tools are installed:
     ```bash
     xcode-select --install
     ```

2. **WebDriverAgent Setup**
   - Navigate to WebDriverAgent directory:
     ```bash
     cd /opt/homebrew/lib/node_modules/appium/node_modules/appium-xcuitest-driver/node_modules/appium-webdriveragent
     ```
   - Open the project in Xcode:
     ```bash
     open WebDriverAgent.xcodeproj
     ```
   - Sign the WebDriverAgent with your Apple Developer account:
     1. In Xcode, select the WebDriverAgent project
     2. Select the WebDriverAgentLib and WebDriverAgentRunner targets
     3. Under Signing & Capabilities, select your team and update the bundle identifier if needed

### iOS Testing Utilities

1. **For Simulators**
   - List available simulators:
     ```bash
     xcrun simctl list devices
     ```
   - Launch a specific simulator:
     ```bash
     xcrun simctl boot "iPhone 14"
     ```

2. **For Real Devices**
   - Install libimobiledevice:
     ```bash
     brew install libimobiledevice
     ```
   - Get device UDID:
     ```bash
     idevice_id -l
     ```
   - Install ideviceinstaller to manage apps:
     ```bash
     brew install ideviceinstaller
     ```
   - On iOS 17 or later, enable **Developer Mode** on the device after the first deploy (Settings → Privacy & Security → Developer Mode).
   - List installed apps on device:
     ```bash
     ideviceinstaller -l
     ```
   - Search for specific apps:
     ```bash
     ideviceinstaller -l | grep -i <app-name>
     ```

## Android Setup

### Required Components

1. **Android Studio**
   - Download and install from [developer.android.com](https://developer.android.com/studio)
   - During installation, ensure you select:
     - Android SDK
     - Google Play system images (recommended)
     - At least one Android SDK Platform package
     - Android Virtual Device (AVD)

2. **Android SDK Platform Tools**
   ```bash
   brew install android-platform-tools
   ```

3. **Environment Variables**
   Add these to your `~/.zshrc` or `~/.bash_profile`:
   ```bash
   export JAVA_HOME=$(/usr/libexec/java_home)
   export ANDROID_HOME=$HOME/Library/Android/sdk
   export PATH=$PATH:$ANDROID_HOME/platform-tools
   export PATH=$PATH:$ANDROID_HOME/tools
   export PATH=$PATH:$ANDROID_HOME/tools/bin
   export PATH=$PATH:$ANDROID_HOME/emulator
   ```
   Then reload your shell configuration:
   ```bash
   source ~/.zshrc  # or source ~/.bash_profile
   ```

### Android Testing Utilities

1. **For Emulators**
   - Create an emulator through Android Studio:
     - Tools > Device Manager > Create Device
   - List available emulators:
     ```bash
     emulator -list-avds
     ```
   - Start an emulator:
     ```bash
     emulator -avd <avd_name>
     ```

2. **For Real Devices**
   - Enable Developer Options and USB Debugging on your device
   - Verify device connection:
     ```bash
     adb devices
     ```

## Installing Appium Drivers

1. **XCUITest Driver (iOS)**
   ```bash
   appium driver install xcuitest
   ```

2. **UiAutomator2 Driver (Android)**
   ```bash
   appium driver install uiautomator2
   ```

## Verification

Verify your setup is working:

1. For iOS:
   ```bash
   xcrun simctl list devices  # Should show available simulators
   # OR for real devices
   idevice_id -l  # Should show connected device UDID
   ```

2. For Android:
   ```bash
   adb devices  # Should show connected devices or emulators
   ```

## Troubleshooting

### iOS Issues

- If WebDriverAgent fails to build, make sure:
  - Xcode is updated to the latest version
  - You have valid Apple Developer credentials
  - Provisioning profiles are correctly set up
  - Try building WebDriverAgent manually in Xcode first

### Android Issues

- If ADB doesn't detect your device:
  - Ensure USB debugging is enabled on the device
  - Try different USB cables or ports
  - Restart ADB server:
    ```bash
    adb kill-server
    adb start-server
    ```

## Additional Tools (Recommended)

1. **Appium Inspector**
   - GUI tool to inspect app elements
   - Download from [GitHub releases](https://github.com/appium/appium-inspector/releases)

2. **Appium Desktop**
   - All-in-one Appium package with GUI
   - Download from [GitHub releases](https://github.com/appium/appium-desktop/releases)

3. **Xcode Command Line Tools**
   ```bash
   xcode-select --install
   ```

## Useful Commands Reference

### iOS
```bash
# List all iOS devices (real and simulators)
xcrun devicectl list devices

# List only simulators
xcrun simctl list devices

# Launch specific simulator
xcrun simctl boot "iPhone 14"

# Get UDID of connected real devices
idevice_id -l

# List installed apps on real device
ideviceinstaller -l
```

### Android
```bash
# List connected Android devices and emulators
adb devices

# List available Android emulators
emulator -list-avds

# Launch specific emulator
emulator -avd <emulator_name>

# Install APK on device
adb install path/to/app.apk

# Get device information
adb shell getprop
```

## Notes

- This setup is primarily for macOS, as iOS testing requires macOS
- For Android-only testing, Windows or Linux can also be used
- Keep Appium, Android Studio, and Xcode updated to avoid compatibility issues


## Getting Help

- **[Discord](https://discord.gg/V9mW8UJ6tx)** – chat with maintainers & the community.
- **GitHub Discussions / Issues** – ask technical questions.