# [>] IOS TOOLS

**Cross-platform CLI & GUI utility for iOS development** - Convert apps to IPA, build DEB packages, compile dylibs, sign IPAs, and create standalone executables.

![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20BSD-lightgrey.svg)

## [*] Features

- [x] **Beautiful Dark UI** - Animated universe background with parallax stars
- [x] **app2ipa** - Convert .app bundles to unsigned .ipa files
- [x] **folder2deb** - Build Debian packages for iOS
- [x] **build-dylib** - Compile dynamic libraries with Theos or clang
- [x] **compile** - Create standalone executables (.exe, Linux, macOS, BSD)
- [x] **sign-annual** - Sign IPAs with Apple Developer Certificate (1 year validity)
- [x] **sign-weekly** - Sign IPAs with free Apple ID (7 days, like AltStore/Sideloadly)
- [x] **Cross-platform** - Works on Windows, Linux, macOS, and BSD
- [x] **CLI + GUI** - Use from terminal or graphical interface
- [x] **Modular Architecture** - Signing features are optional extensions

## [>] Installation

### Requirements

```bash
# Core dependencies (required)
pip install PyQt6 "typer[all]" pyinstaller

# Signing dependencies (optional - for IPA signing features)
pip install cryptography pyOpenSSL

# Weekly signing (Apple ID) - additional dependency
pip install requests
```

### Platform-specific requirements

<details>
<summary><b>[*] Linux (Debian/Ubuntu)</b></summary>

```bash
# For folder2deb
sudo apt update && sudo apt install dpkg

# For build-dylib (if not using Theos)
sudo apt install clang

# For PyQt6 (if not installed via pip)
sudo apt install python3-pyqt6
```
</details>

<details>
<summary><b>[*] macOS</b></summary>

```bash
# For folder2deb
brew install dpkg

# For build-dylib
xcode-select --install
```
</details>

<details>
<summary><b>[*] Windows</b></summary>

```bash
# For folder2deb, use WSL:
wsl --install
wsl sudo apt install dpkg

# Or run the entire tool in WSL for full compatibility
```
</details>

<details>
<summary><b>[*] BSD (FreeBSD/OpenBSD/NetBSD)</b></summary>

```bash
# FreeBSD
pkg install dpkg llvm python311 py311-qt6

# OpenBSD
pkg_add dpkg llvm python3

# NetBSD
pkgin install dpkg clang python311
```
</details>

## [>] Usage

### GUI Mode (Recommended)

```bash
# Launch GUI (no arguments)
python ios_tool.py

# Or explicitly
python ios_tool.py gui
```

The GUI features:
- 🌌 Animated space background with twinkling stars
- 📱 Tabbed interface for each tool
- 📋 Real-time console output
- 🎨 Modern dark theme

### CLI Mode

```bash
# Show all commands
python ios_tool.py --help

# Show command-specific help
python ios_tool.py app2ipa --help
```

---

## 📱 Commands

### 1. app2ipa - Convert .app to unsigned .ipa

```bash
# Basic usage
python ios_tool.py app2ipa "/path/to/MyApp.app"

# Specify output
python ios_tool.py app2ipa "/path/to/MyApp.app" -o "/output/MyApp-unsigned.ipa"

# With spaces in path
python ios_tool.py app2ipa "/path/to/My App.app" -o "My App.ipa"
```

**What it does:**
- ✅ Validates input is a `.app` directory
- 📁 Creates `Payload/` structure
- 🗑️ Removes `_CodeSignature/` and `embedded.mobileprovision`
- 🗜️ Creates ZIP archive with `.ipa` extension

---

### 2. folder2deb - Build .deb package

```bash
# Basic usage
python ios_tool.py folder2deb "/path/to/pkgroot"

# Specify output
python ios_tool.py folder2deb "/path/to/pkgroot" -o "mypackage.deb"
```

**Required structure:**
```
pkgroot/
├── DEBIAN/
│   └── control          # Required!
├── Library/
│   └── MobileSubstrate/
│       └── DynamicLibraries/
│           ├── MyTweak.dylib
│           └── MyTweak.plist
└── ...
```

**Minimal control file:**
```
Package: com.example.mypackage
Name: My Package
Version: 1.0.0
Architecture: iphoneos-arm
Description: A short description
Maintainer: Your Name <your@email.com>
Author: Your Name <your@email.com>
Section: Tweaks
Depends: mobilesubstrate
```

---

### 3. build-dylib - Build dynamic library

```bash
# Using Theos (if available)
python ios_tool.py build-dylib "/path/to/project" -o tweak.dylib

# Specify source file
python ios_tool.py build-dylib "/path/to/project" -s tweak.m -o tweak.dylib

# Simple C library
python ios_tool.py build-dylib "/path/to/project" -s mylib.c -o mylib.dylib
```

**Build methods:**
1. **Theos** (recommended): If `$THEOS` is set, uses `make` to build
2. **Clang**: Falls back to direct clang compilation if SDK is available

**Environment variables for clang build:**
```bash
export SDKROOT=/path/to/iPhoneOS.sdk
export CFLAGS="-target arm64-apple-ios14.0"
export LDFLAGS="-target arm64-apple-ios14.0"
```

---

### 4. compile - Create Standalone Executable

```bash
# Compile for current platform (auto-detects OS and architecture)
python ios_tool.py compile

# Specify output name
python ios_tool.py compile -o my_ios_tool

# Specify target architecture
python ios_tool.py compile -a arm64
python ios_tool.py compile -a amd64

# Create folder instead of single file
python ios_tool.py compile --no-onefile
```

**Output by platform and architecture:**

| Platform | AMD64 (x86_64) | ARM64 |
|----------|----------------|-------|
| Windows  | `ios_tool-win-amd64.exe` | `ios_tool-win-arm64.exe` |
| Linux    | `ios_tool-linux-amd64` | `ios_tool-linux-arm64` |
| macOS    | `ios_tool-macos-amd64` | `ios_tool-macos-arm64` |
| BSD      | `ios_tool-bsd-amd64` | `ios_tool-bsd-arm64` |

---

### 5. sign-annual - Sign IPA with Developer Certificate

Sign IPAs using your Apple Developer Certificate (valid for 1 year).

```bash
# Basic usage
python ios_tool.py sign-annual input.ipa -p certificate.p12 -m app.mobileprovision

# With password
python ios_tool.py sign-annual input.ipa -p cert.p12 -m app.mobileprovision -w "mypassword"

# Specify output
python ios_tool.py sign-annual input.ipa -p cert.p12 -m app.mobileprovision -o signed.ipa

# Change bundle ID
python ios_tool.py sign-annual input.ipa -p cert.p12 -m app.mobileprovision -b com.new.bundleid
```

**Requirements:**
- `.p12` certificate file (export from Keychain Access or Apple Developer Portal)
- `.mobileprovision` file (download from Apple Developer Portal)
- Optional: P12 password

**Supported Certificate Types:**
- Apple Development
- Apple Distribution  
- iOS Development
- iOS Distribution
- Enterprise Distribution

---

### 6. sign-weekly - Sign IPA with Apple ID (7 Days)

Sign IPAs using a free Apple ID, similar to AltStore/Sideloadly (valid for 7 days).

```bash
# Basic usage
python ios_tool.py sign-weekly input.ipa -a "email@icloud.com" -w "password" -u "DEVICE-UDID"

# With 2FA code
python ios_tool.py sign-weekly input.ipa -a "email@icloud.com" -w "password" -u "UDID" -c 123456

# Specify output
python ios_tool.py sign-weekly input.ipa -a "email@icloud.com" -w "password" -u "UDID" -o signed.ipa
```

**Requirements:**
- Apple ID (free account works)
- Apple ID password or App-Specific Password
- Target device UDID (40-character hex string)
- Internet connection

**How to get Device UDID:**
1. Connect device to computer
2. Open iTunes/Finder
3. Click on device serial number until UDID appears
4. Copy the 40-character string

**Limitations (Apple-imposed):**
| Limit | Value |
|-------|-------|
| Signature Validity | 7 days |
| Max Apps Simultaneously | 3 |
| Max App IDs per Week | 10 |
| Re-signing Required | Every 7 days |

---

### 7. sign-info - Show Signing Module Status

```bash
python ios_tool.py sign-info
```

Shows:
- Module availability status
- Installed dependencies
- Available signing methods

---

## 🔐 Signing Module Architecture

The signing system is designed as a **modular extension** that doesn't affect existing functionality:

```
signing/
├── __init__.py       # Module loader and availability checks
├── models.py         # Data classes (Certificate, Profile, etc.)
├── crypto_utils.py   # Cryptographic utilities (P12, CMS)
├── core.py           # Core signing operations (shared)
├── annual.py         # Annual signing (P12 + Provisioning)
├── weekly.py         # Weekly signing (Apple ID)
└── apple_auth.py     # Apple ID authentication
```

**Key Features:**
- ✅ Completely optional - doesn't break existing features if not installed
- ✅ Lazy loading - only loads when signing commands are used
- ✅ Cross-platform - works on Windows, Linux, macOS, BSD
- ✅ No Apple server bypass - follows Apple's Terms of Service
- ✅ Modular design - easy to extend with new signing methods

**Architecture Guide:**
| Architecture | Description | Examples |
|-------------|-------------|----------|
| `amd64` | 64-bit Intel/AMD | Most Windows PCs, Intel Macs, Linux servers |
| `arm64` | 64-bit ARM | Apple Silicon (M1/M2/M3/M4), Raspberry Pi 4+, Surface Pro X |
| `arm` | 32-bit ARM | Raspberry Pi 3, older ARM devices |
| `x86` | 32-bit Intel | Legacy 32-bit systems |

**Important Notes:**
- Native builds recommended (build on target platform)
- Windows .exe must be built on Windows
- macOS binaries must be built on macOS
- Use GitHub Actions for multi-platform CI/CD builds
- Requires: `pip install pyinstaller`

---

## [*] Linux Support

Full Linux support is included! Here's how to set up:

### Theos on Linux
```bash
# Install dependencies
sudo apt install build-essential git perl libc6-dev libncurses5

# Clone Theos
git clone --recursive https://github.com/theos/theos.git ~/theos

# Set environment
echo "export THEOS=~/theos" >> ~/.bashrc
source ~/.bashrc

# Install iOS SDK (download from Xcode or third-party)
# Place in ~/theos/sdks/
```

### Using clang directly on Linux
```bash
# Install clang
sudo apt install clang

# Set up environment for iOS cross-compilation
export SDKROOT=/path/to/iPhoneOS.sdk
export CFLAGS="-target arm64-apple-ios14.0 -arch arm64"
export LDFLAGS="-target arm64-apple-ios14.0 -arch arm64"
```

---

## 📊 Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (invalid input, missing files, etc.) |
| >1 | Tool-specific error (dpkg-deb, make, clang exit codes) |

---

## 💡 Examples

```bash
# Convert extracted app to IPA
python ios_tool.py app2ipa "~/Desktop/Payload/MyApp.app" -o ~/Desktop/MyApp.ipa

# Build tweak package
python ios_tool.py folder2deb ~/mytweak/package -o ~/mytweak/com.me.tweak_1.0.0.deb

# Compile tweak with Theos
export THEOS=~/theos
python ios_tool.py build-dylib ~/mytweak -o Tweak.dylib

# Launch GUI
python ios_tool.py
```

---

## 📸 Screenshots

The GUI features a stunning Grok AI-style interface with:
- Animated milky way galaxy band flowing across the screen
- Hundreds of twinkling stars at multiple depth layers
- Floating cosmic dust particles
- Clean, minimal dark UI with glass-morphism elements
- Blinking cursor animation in the subtitle
- No system emojis - clean text-based design

---

## 🛠️ Development

```bash
# Clone the repository
git clone https://github.com/yourusername/ios-tool.git
cd ios-tool

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

---

## 📄 License

MIT License - Feel free to use, modify, and distribute!
