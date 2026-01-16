#!/usr/bin/env python3
"""
IOS TOOLS - CLI & GUI utility for iOS development tasks.
Supports: app2ipa, folder2deb, build-dylib, compile
Cross-platform: Windows, Linux, macOS, BSD

Usage:
    CLI Mode: python ios_tool.py <command> [options]
    GUI Mode: python ios_tool.py gui
             python ios_tool.py (no arguments)

Commands:
    app2ipa     - Convert .app to .ipa
    folder2deb  - Build .deb package
    build-dylib - Compile dynamic library
    compile     - Create standalone executable

Requirements:
    pip install PyQt6 typer[all] pyinstaller
"""

import os
import sys
import shutil
import subprocess
import tempfile
import zipfile
import random
import math
from pathlib import Path
from typing import Optional, Callable, List
from dataclasses import dataclass

# ============================================================================
# Core Logic (Shared between CLI and GUI)
# ============================================================================

class IOSToolCore:
    """Core functionality for IOS TOOLS operations."""
    
    MINIMAL_CONTROL_EXAMPLE = """# Minimal DEBIAN/control file example:
# =====================================
Package: com.example.mypackage
Name: My Package
Version: 1.0.0
Architecture: iphoneos-arm
Description: A short description of the package
Maintainer: Your Name <your@email.com>
Author: Your Name <your@email.com>
Section: Tweaks
Depends: mobilesubstrate"""

    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback or self._default_log
    
    def _default_log(self, message: str, level: str = "info") -> None:
        print(message)
    
    def log(self, message: str, level: str = "info") -> None:
        self.log_callback(message, level)
    
    def app2ipa(self, input_path: str, output_path: Optional[str] = None) -> tuple[bool, str]:
        """Convert .app directory to unsigned .ipa file."""
        app_path = Path(input_path).resolve()
        
        if not app_path.name.endswith(".app"):
            return False, f"Input path must end with .app (got: {app_path.name})"
        
        if not app_path.is_dir():
            return False, f"Input path is not a directory: {app_path}"
        
        app_name = app_path.stem
        if output_path:
            ipa_path = Path(output_path).resolve()
        else:
            ipa_path = app_path.parent / f"{app_name}-unsigned.ipa"
        
        ipa_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.log(f"[>] Processing: {app_path}")
        self.log(f"[>] Output: {ipa_path}")
        
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="app2ipa_")
            payload_dir = Path(temp_dir) / "Payload"
            payload_dir.mkdir()
            
            dest_app = payload_dir / app_path.name
            self.log(f"[*] Copying {app_path.name} to Payload...")
            shutil.copytree(app_path, dest_app, symlinks=False)
            
            code_sig_path = dest_app / "_CodeSignature"
            if code_sig_path.exists():
                self.log("[*] Removing _CodeSignature...")
                shutil.rmtree(code_sig_path)
            
            provision_path = dest_app / "embedded.mobileprovision"
            if provision_path.exists():
                self.log("[*] Removing embedded.mobileprovision...")
                provision_path.unlink()
            
            self.log("[*] Creating .ipa archive...")
            
            if ipa_path.exists():
                ipa_path.unlink()
            
            with zipfile.ZipFile(ipa_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in payload_dir.rglob("*"):
                    arcname = file_path.relative_to(temp_dir)
                    if file_path.is_file():
                        zf.write(file_path, arcname)
                    elif file_path.is_dir():
                        zf.write(file_path, str(arcname) + "/")
            
            size_mb = ipa_path.stat().st_size / 1024 / 1024
            self.log(f"[+] Success! Created: {ipa_path}", "success")
            self.log(f"[+] Size: {size_mb:.2f} MB", "success")
            
            return True, str(ipa_path)
            
        except PermissionError as e:
            return False, f"Permission denied - {e}"
        except Exception as e:
            return False, str(e)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    def folder2deb(self, input_path: str, output_path: Optional[str] = None) -> tuple[bool, str]:
        """Build .deb package from folder structure."""
        root_path = Path(input_path).resolve()
        
        if not root_path.is_dir():
            return False, f"Input path is not a directory: {root_path}"
        
        control_path = root_path / "DEBIAN" / "control"
        if not control_path.exists():
            error_msg = f"DEBIAN/control not found in: {root_path}\n\n{self.MINIMAL_CONTROL_EXAMPLE}"
            return False, error_msg
        
        if output_path:
            deb_path = Path(output_path).resolve()
        else:
            deb_path = root_path.parent / f"{root_path.name}.deb"
        
        deb_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.log(f"[>] Building package from: {root_path}")
        self.log(f"[>] Output: {deb_path}")
        
        dpkg_cmd = self._find_dpkg_deb()
        if dpkg_cmd is None:
            return False, self._get_dpkg_install_instructions()
        
        try:
            result = subprocess.run(
                [dpkg_cmd, "--build", str(root_path), str(deb_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            
            if result.stdout:
                self.log(result.stdout)
            
            size_kb = deb_path.stat().st_size / 1024
            self.log(f"[+] Success! Created: {deb_path}", "success")
            self.log(f"[+] Size: {size_kb:.2f} KB", "success")
            
            return True, str(deb_path)
            
        except subprocess.CalledProcessError as e:
            error = e.stderr if e.stderr else str(e)
            return False, f"dpkg-deb failed: {error}"
        except Exception as e:
            return False, str(e)
    
    def _find_dpkg_deb(self) -> Optional[str]:
        """Find dpkg-deb command, checking common locations."""
        if shutil.which("dpkg-deb"):
            return "dpkg-deb"
        
        linux_paths = [
            "/usr/bin/dpkg-deb",
            "/usr/local/bin/dpkg-deb",
            "/bin/dpkg-deb",
        ]
        
        macos_paths = [
            "/opt/homebrew/bin/dpkg-deb",
            "/usr/local/opt/dpkg/bin/dpkg-deb",
        ]
        
        all_paths = linux_paths + macos_paths
        
        for path in all_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        
        return None
    
    def _get_dpkg_install_instructions(self) -> str:
        """Get platform-specific dpkg installation instructions."""
        import platform
        system = platform.system().lower()
        
        instructions = "dpkg-deb not found.\n\nInstallation instructions:\n"
        
        if system == "linux":
            instructions += """
Linux (Debian/Ubuntu):
  sudo apt update && sudo apt install dpkg

Linux (Fedora/RHEL):
  sudo dnf install dpkg

Linux (Arch):
  sudo pacman -S dpkg
"""
        elif system == "darwin":
            instructions += """
macOS (Homebrew):
  brew install dpkg

macOS (MacPorts):
  sudo port install dpkg
"""
        elif system == "windows":
            instructions += """
Windows:
  Option 1: Use WSL (Windows Subsystem for Linux)
    wsl --install
    wsl sudo apt install dpkg
  
  Option 2: Use Cygwin with dpkg package
  
  Option 3: Use this tool inside WSL
"""
        elif "bsd" in system or "freebsd" in system or "openbsd" in system or "netbsd" in system:
            instructions += """
BSD (FreeBSD):
  pkg install dpkg

BSD (OpenBSD):
  pkg_add dpkg

BSD (NetBSD):
  pkgin install dpkg
"""
        
        return instructions
    
    def build_dylib(
        self, 
        input_path: str, 
        output_name: Optional[str] = None,
        source_file: Optional[str] = None
    ) -> tuple[bool, str]:
        """Build dynamic library from source."""
        project_path = Path(input_path).resolve()
        
        if not project_path.is_dir():
            return False, f"Input path is not a directory: {project_path}"
        
        output_name = output_name or "tweak.dylib"
        if not output_name.endswith(".dylib"):
            output_name += ".dylib"
        
        self.log(f"[>] Project path: {project_path}")
        self.log(f"[>] Output name: {output_name}")
        
        theos_path = os.environ.get("THEOS")
        theos_available = theos_path and Path(theos_path).exists()
        
        if theos_available:
            self.log(f"[*] Theos found at: {theos_path}")
            return self._build_with_theos(project_path, output_name)
        else:
            return self._build_with_clang(project_path, output_name, source_file)
    
    def _build_with_theos(self, project_path: Path, output_name: str) -> tuple[bool, str]:
        """Build using Theos."""
        self.log("[*] Using Theos to build...")
        
        makefile = project_path / "Makefile"
        if not makefile.exists():
            return False, "No Makefile found. Theos projects require a Makefile."
        
        make_cmd = self._find_make()
        if not make_cmd:
            return False, "make command not found. Please install build-essential or equivalent."
        
        try:
            subprocess.run([make_cmd, "clean"], cwd=project_path, capture_output=True)
            
            self.log("[*] Running: make")
            result = subprocess.run(
                [make_cmd],
                cwd=project_path,
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                error = result.stderr or result.stdout or "make failed"
                return False, error
            
            if result.stdout:
                self.log(result.stdout)
            
            obj_dir = project_path / ".theos" / "obj"
            dylib_files = list(obj_dir.rglob("*.dylib")) if obj_dir.exists() else []
            
            if dylib_files:
                self.log("[+] Build successful!", "success")
                for dylib in dylib_files:
                    self.log(f"    -> {dylib}", "success")
                return True, str(dylib_files[0])
            
            packages_dir = project_path / "packages"
            debs = list(packages_dir.glob("*.deb")) if packages_dir.exists() else []
            if debs:
                self.log("[+] Package created!", "success")
                return True, str(debs[0])
            
            return True, "Build completed. Check project for output."
            
        except FileNotFoundError:
            return False, "'make' command not found."
        except Exception as e:
            return False, str(e)
    
    def _find_make(self) -> Optional[str]:
        """Find make command."""
        if shutil.which("make"):
            return "make"
        if shutil.which("gmake"):
            return "gmake"
        
        paths = ["/usr/bin/make", "/usr/local/bin/make", "/opt/homebrew/bin/make"]
        for path in paths:
            if os.path.isfile(path):
                return path
        return None
    
    def _build_with_clang(
        self, 
        project_path: Path, 
        output_name: str, 
        source_file: Optional[str]
    ) -> tuple[bool, str]:
        """Build using clang."""
        self.log("[*] Theos not found, attempting clang build...")
        
        clang_path = shutil.which("clang")
        if not clang_path:
            return False, self._get_toolchain_requirements()
        
        if source_file:
            src = project_path / source_file
            if not src.exists():
                return False, f"Source file not found: {src}"
            source_files = [src]
        else:
            extensions = [".m", ".c", ".mm", ".cpp", ".cc"]
            source_files = []
            for ext in extensions:
                source_files.extend(project_path.glob(f"*{ext}"))
            
            if not source_files:
                return False, "No source files found (.m, .c, .mm, .cpp, .cc)"
        
        self.log(f"[*] Source files: {[f.name for f in source_files]}")
        
        output_path = project_path / output_name
        sdkroot = os.environ.get("SDKROOT")
        has_sdk = sdkroot and Path(sdkroot).exists()
        
        cmd = ["clang", "-dynamiclib", "-o", str(output_path)]
        
        if has_sdk:
            cmd.extend(["-isysroot", sdkroot])
            self.log(f"[*] Using SDK: {sdkroot}")
        else:
            self.log("[!] Warning: SDKROOT not set. Building for host platform.", "warning")
        
        cflags = os.environ.get("CFLAGS", "")
        ldflags = os.environ.get("LDFLAGS", "")
        
        if cflags:
            cmd.extend(cflags.split())
        
        cmd.extend([str(f) for f in source_files])
        
        has_objc = any(f.suffix in [".m", ".mm"] for f in source_files)
        if has_objc:
            cmd.extend(["-framework", "Foundation"])
            if "-fobjc-arc" not in cflags:
                cmd.append("-fobjc-arc")
        
        if ldflags:
            cmd.extend(ldflags.split())
        
        self.log(f"[*] Compiling: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                error = result.stderr or "Compilation failed"
                if not has_sdk:
                    error += "\n\n" + self._get_toolchain_requirements()
                return False, error
            
            if result.stderr:
                self.log(result.stderr, "warning")
            
            size_kb = output_path.stat().st_size / 1024
            self.log(f"[+] Success! Created: {output_path}", "success")
            self.log(f"[+] Size: {size_kb:.2f} KB", "success")
            
            return True, str(output_path)
            
        except FileNotFoundError:
            return False, self._get_toolchain_requirements()
        except Exception as e:
            return False, str(e)
    
    def _get_toolchain_requirements(self) -> str:
        import platform
        system = platform.system().lower()
        
        base = """iOS SDK Toolchain Required

To build iOS dylibs, you need one of:

1. Theos (Recommended for all platforms)
   Install: https://theos.dev/docs/installation
   Set: export THEOS=~/theos

2. iOS SDK Toolchain
   export SDKROOT=/path/to/iPhoneOS.sdk
   export CFLAGS="-target arm64-apple-ios14.0"
   export LDFLAGS="-target arm64-apple-ios14.0"
"""
        
        if system == "linux":
            base += """
Linux-specific:
   - Install clang: sudo apt install clang
   - Get iOS SDK from Xcode or third-party sources
   - Use Theos with Linux toolchain
"""
        elif system == "darwin":
            base += """
macOS-specific:
   - Install Xcode Command Line Tools: xcode-select --install
   - SDK is automatically available
"""
        elif system == "windows":
            base += """
Windows-specific:
   - Use WSL (Windows Subsystem for Linux)
   - Install Theos inside WSL
   - Or use a Linux VM
"""
        elif "bsd" in system:
            base += """
BSD-specific:
   - FreeBSD: pkg install llvm
   - OpenBSD: pkg_add llvm
   - NetBSD: pkgin install clang
   - Use Theos with BSD toolchain
"""
        
        return base

    def compile_binary(
        self,
        script_path: Optional[str] = None,
        output_name: Optional[str] = None,
        target_os: Optional[str] = None,
        target_arch: Optional[str] = None,
        onefile: bool = True
    ) -> tuple[bool, str]:
        """
        Compile ios_tool.py to standalone executable.
        
        Args:
            script_path: Path to script (defaults to this file)
            output_name: Output binary name
            target_os: Target OS (windows, linux, macos, bsd) - defaults to current
            target_arch: Target architecture (amd64, arm64) - defaults to current
            onefile: Create single file executable
        
        Returns:
            Tuple of (success, result_message)
        """
        import platform
        
        # Check for PyInstaller
        if not shutil.which("pyinstaller"):
            return False, self._get_pyinstaller_instructions()
        
        script = Path(script_path) if script_path else Path(__file__).resolve()
        if not script.exists():
            return False, f"Script not found: {script}"
        
        system = target_os or platform.system().lower()
        
        # Detect architecture
        machine = platform.machine().lower()
        if target_arch:
            arch = target_arch.lower()
        elif machine in ["x86_64", "amd64", "x64"]:
            arch = "amd64"
        elif machine in ["arm64", "aarch64"]:
            arch = "arm64"
        elif machine in ["armv7l", "armv7", "arm"]:
            arch = "arm"
        elif machine in ["i386", "i686", "x86"]:
            arch = "x86"
        else:
            arch = machine
        
        # Determine output name based on OS and architecture
        if not output_name:
            base_name = "ios_tool"
            arch_suffix = f"-{arch}"
            
            if system == "windows":
                output_name = f"{base_name}-win{arch_suffix}.exe"
            elif system == "darwin":
                output_name = f"{base_name}-macos{arch_suffix}"
            elif "bsd" in system:
                output_name = f"{base_name}-bsd{arch_suffix}"
            else:  # linux
                output_name = f"{base_name}-linux{arch_suffix}"
        
        self.log(f"[>] Source: {script}")
        self.log(f"[>] Target OS: {system}")
        self.log(f"[>] Target Arch: {arch}")
        self.log(f"[>] Output: {output_name}")
        
        # Build PyInstaller command
        cmd = [
            "pyinstaller",
            "--name", output_name.replace(".exe", ""),
            "--noconfirm",
            "--clean",
        ]
        
        if onefile:
            cmd.append("--onefile")
        
        # Platform-specific options
        cmd.append("--console")  # Show console for CLI
        
        # Architecture-specific target (for cross-compilation info)
        if system == "darwin" and arch == "arm64":
            cmd.extend(["--target-arch", "arm64"])
        elif system == "darwin" and arch == "amd64":
            cmd.extend(["--target-arch", "x86_64"])
        
        # Add hidden imports for PyQt6
        cmd.extend([
            "--hidden-import", "PyQt6",
            "--hidden-import", "PyQt6.QtWidgets",
            "--hidden-import", "PyQt6.QtCore",
            "--hidden-import", "PyQt6.QtGui",
            "--hidden-import", "typer",
        ])
        
        # Add logo icon for the executable
        logo_file = script.parent / "logo.jpg"
        logo_ico = script.parent / "logo.ico"
        
        # Try to use .ico file if it exists, otherwise convert jpg to ico
        if logo_ico.exists():
            cmd.extend(["--icon", str(logo_ico)])
            self.log(f"[>] Using icon: {logo_ico}")
        elif logo_file.exists():
            # Try to convert jpg to ico using PIL if available
            try:
                from PIL import Image
                img = Image.open(logo_file)
                # Create multiple sizes for better icon quality
                img.save(logo_ico, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
                cmd.extend(["--icon", str(logo_ico)])
                self.log(f"[>] Created icon: {logo_ico}")
            except ImportError:
                self.log("[!] PIL not installed - using jpg directly (may not work on all platforms)", "warning")
                cmd.extend(["--icon", str(logo_file)])
            except Exception as e:
                self.log(f"[!] Could not convert logo: {e}", "warning")
        
        # Bundle logo.jpg as data file for runtime use
        if logo_file.exists():
            if system == "windows":
                cmd.extend(["--add-data", f"{logo_file};."])
            else:
                cmd.extend(["--add-data", f"{logo_file}:."])
            self.log(f"[>] Bundling: {logo_file.name}")
        
        cmd.append(str(script))
        
        self.log(f"[*] Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=script.parent
            )
            
            if result.returncode != 0:
                error = result.stderr or result.stdout or "PyInstaller failed"
                return False, error
            
            # Find the output
            dist_dir = script.parent / "dist"
            binary_name = output_name.replace(".exe", "") if not system == "windows" else output_name.replace(".exe", "")
            output_file = dist_dir / binary_name
            
            if output_file.exists():
                size_mb = output_file.stat().st_size / (1024 * 1024)
                self.log(f"[+] Success! Created: {output_file}", "success")
                self.log(f"[+] Size: {size_mb:.2f} MB", "success")
                self.log(f"[+] Platform: {system} / {arch}", "success")
                return True, str(output_file)
            
            # Check for any file in dist
            dist_files = list(dist_dir.glob("*")) if dist_dir.exists() else []
            if dist_files:
                self.log(f"[+] Success! Output in: {dist_dir}", "success")
                for f in dist_files[:5]:
                    self.log(f"    -> {f.name}", "success")
                return True, str(dist_dir)
            
            return True, f"Build completed. Check {dist_dir} for output."
            
        except FileNotFoundError:
            return False, self._get_pyinstaller_instructions()
        except Exception as e:
            return False, str(e)
    
    def _get_pyinstaller_instructions(self) -> str:
        """Get PyInstaller installation instructions."""
        import platform
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        instructions = f"""PyInstaller Required

Current System: {platform.system()} / {machine}

To compile standalone executables, install PyInstaller:

    pip install pyinstaller

Output Naming Convention:
    Windows:  ios_tool-win-amd64.exe  / ios_tool-win-arm64.exe
    Linux:    ios_tool-linux-amd64    / ios_tool-linux-arm64
    macOS:    ios_tool-macos-amd64    / ios_tool-macos-arm64
    BSD:      ios_tool-bsd-amd64      / ios_tool-bsd-arm64

"""
        
        if system == "windows":
            instructions += """Windows Notes:
    - AMD64: Most Windows PCs (Intel/AMD processors)
    - ARM64: Windows on ARM devices (Surface Pro X, etc.)
    - May need to add to Windows Defender exclusions
"""
        elif system == "darwin":
            instructions += """macOS Notes:
    - AMD64: Intel Macs (pre-2020)
    - ARM64: Apple Silicon Macs (M1/M2/M3/M4)
    - Universal binaries: Build on both architectures
    - Sign for distribution: codesign -s - ios_tool-macos-arm64
"""
        elif system == "linux":
            instructions += """Linux Notes:
    - AMD64: Most desktop/server Linux (x86_64)
    - ARM64: Raspberry Pi 4+, AWS Graviton, etc.
    - ARM: Raspberry Pi 3 and older (32-bit)
    - Make executable: chmod +x ios_tool-linux-*
"""
        elif "bsd" in system:
            instructions += """BSD Notes:
    - AMD64: Most FreeBSD/OpenBSD servers
    - ARM64: ARM-based BSD systems
    - Make executable: chmod +x ios_tool-bsd-*
"""
        
        instructions += """
Cross-compilation Notes:
    - Native builds are recommended (build on target platform)
    - Use CI/CD (GitHub Actions) for multi-platform builds
    - ARM builds require ARM hardware or emulation (QEMU)
"""
        
        return instructions


# ============================================================================
# Signing Module Integration (Optional Extension)
# ============================================================================

def _check_signing_available() -> tuple[bool, str]:
    """Check if signing module is available."""
    try:
        from signing import is_available, get_signing_info
        if is_available():
            return True, "Signing module available"
        else:
            info = get_signing_info()
            missing = [k for k, v in info["dependencies"].items() if not v]
            return False, f"Missing dependencies: {', '.join(missing)}"
    except ImportError:
        return False, "Signing module not found"


def _get_signing_install_instructions() -> str:
    """Get signing module installation instructions."""
    return """
IPA Signing Module - Installation
==================================

To enable IPA signing features, install dependencies:

    pip install cryptography pyOpenSSL

For Apple ID (weekly) signing, also install:

    pip install requests

Signing Methods Available:
1. Annual Signing - Uses .p12 + mobileprovision (1 year validity)
2. Weekly Signing - Uses free Apple ID (7 days validity)

After installation, use:
    ios_tool sign-annual --help
    ios_tool sign-weekly --help
"""


# ============================================================================
# Device Module Integration (Optional Extension)
# ============================================================================

def _check_device_available() -> tuple[bool, str]:
    """Check if device module is available."""
    try:
        from device import is_available
        available, msg = is_available()
        if available:
            # Also check if detection is supported on this platform
            from device.detection import DeviceDetector
            detector = DeviceDetector()
            if detector.is_supported():
                return True, "Device detection available"
            else:
                return False, detector.get_status_message()
        return False, msg
    except ImportError:
        return False, "Device module not found"


def _get_device_install_instructions() -> str:
    """Get device module installation instructions."""
    import platform
    system = platform.system().lower()
    
    instructions = """
iOS Device Module - Installation
=================================

"""
    
    if system == "windows":
        instructions += """Windows Requirements:
--------------------
Option 1: iTunes (Recommended)
  • Download iTunes from apple.com (NOT Microsoft Store version)
  • URL: https://www.apple.com/itunes/download/win64
  • Includes Apple Mobile Device Support

Option 2: libimobiledevice
  • Install via Chocolatey: choco install libimobiledevice
  • Or download from: https://github.com/libimobiledevice-win32

IMPORTANT: Microsoft Store version of iTunes does NOT work!
"""
    
    elif system == "darwin":
        instructions += """macOS Requirements:
------------------
Install libimobiledevice via Homebrew:

    brew install libimobiledevice ideviceinstaller

Or use Xcode Command Line Tools:

    xcode-select --install
"""
    
    elif system == "linux":
        instructions += """Linux Requirements:
------------------
Install libimobiledevice:

  Ubuntu/Debian:
    sudo apt install libimobiledevice6 libimobiledevice-utils ideviceinstaller usbmuxd

  Fedora/RHEL:
    sudo dnf install libimobiledevice libimobiledevice-utils ideviceinstaller usbmuxd

  Arch Linux:
    sudo pacman -S libimobiledevice ideviceinstaller usbmuxd

Start usbmuxd service:
    sudo systemctl start usbmuxd
    sudo systemctl enable usbmuxd
"""
    
    else:
        instructions += """BSD Requirements:
----------------
Install libimobiledevice:

    pkg install libimobiledevice

Note: BSD support may be limited.
"""
    
    instructions += """
Available Commands:
  ios_tool device-detect   - Detect connected devices
  ios_tool device-install  - Install IPA to device
  ios_tool device-info     - Show platform support status
"""
    
    return instructions


# ============================================================================
# CLI Interface
# ============================================================================

def run_cli():
    """Run the CLI interface using typer."""
    try:
        import typer
        from typer import Argument, Option
    except ImportError:
        print("Error: typer is required for CLI mode.")
        print("Install with: pip install typer[all]")
        sys.exit(1)
    
    cli_app = typer.Typer(
        name="ios_tool",
        help="iOS Development CLI Tool - app2ipa, folder2deb, build-dylib",
        add_completion=False,
    )
    
    def typer_log(message: str, level: str = "info") -> None:
        colors = {
            "info": None,
            "success": typer.colors.GREEN,
            "warning": typer.colors.YELLOW,
            "error": typer.colors.RED,
        }
        typer.secho(message, fg=colors.get(level))
    
    core = IOSToolCore(log_callback=typer_log)
    
    @cli_app.command("app2ipa")
    def cmd_app2ipa(
        input_path: str = Argument(..., help="Path to the .app directory"),
        output: Optional[str] = Option(None, "-o", "--output", help="Output .ipa file path"),
    ) -> None:
        """Convert a .app directory to an unsigned .ipa file."""
        success, result = core.app2ipa(input_path, output)
        if not success:
            typer.secho(f"Error: {result}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    @cli_app.command("folder2deb")
    def cmd_folder2deb(
        input_path: str = Argument(..., help="Path to package root (must contain DEBIAN/control)"),
        output: Optional[str] = Option(None, "-o", "--output", help="Output .deb file path"),
    ) -> None:
        """Build a .deb package from a folder structure."""
        success, result = core.folder2deb(input_path, output)
        if not success:
            typer.secho(f"Error: {result}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    @cli_app.command("build-dylib")
    def cmd_build_dylib(
        input_path: str = Argument(..., help="Path to project directory"),
        output: Optional[str] = Option(None, "-o", "--output", help="Output .dylib name"),
        source_file: Optional[str] = Option(None, "-s", "--source", help="Specific source file"),
    ) -> None:
        """Build a dynamic library (.dylib) from source code."""
        success, result = core.build_dylib(input_path, output, source_file)
        if not success:
            typer.secho(f"Error: {result}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    @cli_app.command("compile")
    def cmd_compile(
        output: Optional[str] = Option(None, "-o", "--output", help="Output binary name"),
        target: Optional[str] = Option(None, "-t", "--target", help="Target OS: windows, linux, macos, bsd"),
        arch: Optional[str] = Option(None, "-a", "--arch", help="Target architecture: amd64, arm64, arm, x86"),
        no_onefile: bool = Option(False, "--no-onefile", help="Create folder instead of single file"),
    ) -> None:
        """Compile ios_tool to standalone executable (.exe, Linux binary, macOS binary)."""
        import platform
        current_arch = platform.machine()
        typer.secho(f"[*] Compiling standalone executable...", fg=typer.colors.CYAN)
        typer.secho(f"[*] Current platform: {platform.system()} / {current_arch}", fg=typer.colors.CYAN)
        success, result = core.compile_binary(
            script_path=None,  # Uses current file
            output_name=output,
            target_os=target,
            target_arch=arch,
            onefile=not no_onefile
        )
        if not success:
            typer.secho(f"Error: {result}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    @cli_app.command("gui")
    def cmd_gui() -> None:
        """Launch the graphical user interface."""
        run_gui()
    
    # =========================================================================
    # Signing Commands (Optional Extension)
    # =========================================================================
    
    @cli_app.command("sign-annual")
    def cmd_sign_annual(
        input_ipa: str = Argument(..., help="Path to IPA file to sign"),
        p12: str = Option(..., "--p12", "-p", help="Path to .p12 certificate file"),
        provision: str = Option(..., "--provision", "-m", help="Path to .mobileprovision file"),
        password: str = Option("", "--password", "-w", help="P12 password (empty if none)"),
        output: Optional[str] = Option(None, "-o", "--output", help="Output IPA path"),
        bundle_id: Optional[str] = Option(None, "-b", "--bundle-id", help="Override bundle ID"),
    ) -> None:
        """Sign IPA with Apple Developer Certificate (valid for 1 year)."""
        available, msg = _check_signing_available()
        if not available:
            typer.secho(f"Signing not available: {msg}", fg=typer.colors.RED, err=True)
            typer.echo(_get_signing_install_instructions())
            raise typer.Exit(code=1)
        
        try:
            from signing.annual import AnnualSigner
            
            typer.secho("[*] Annual Signing (Developer Certificate)", fg=typer.colors.CYAN)
            
            signer = AnnualSigner(
                p12_path=p12,
                provision_path=provision,
                p12_password=password,
                log_callback=typer_log
            )
            
            # Validate
            valid, validate_msg = signer.validate()
            if not valid:
                typer.secho(f"Validation failed: {validate_msg}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            
            # Sign
            result = signer.sign_ipa(input_ipa, output, bundle_id)
            
            if not result.success:
                typer.secho(f"Error: {result.message}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            
            typer.secho(f"[+] Signed IPA: {result.output_path}", fg=typer.colors.GREEN)
            
        except ImportError as e:
            typer.secho(f"Import error: {e}", fg=typer.colors.RED, err=True)
            typer.echo(_get_signing_install_instructions())
            raise typer.Exit(code=1)
    
    @cli_app.command("sign-weekly")
    def cmd_sign_weekly(
        input_ipa: str = Argument(..., help="Path to IPA file to sign"),
        apple_id: str = Option(..., "--apple-id", "-a", help="Apple ID email"),
        password: str = Option(..., "--password", "-w", help="Apple ID password"),
        udid: str = Option(..., "--udid", "-u", help="Target device UDID"),
        code: Optional[str] = Option(None, "--2fa", "-c", help="Two-factor auth code"),
        output: Optional[str] = Option(None, "-o", "--output", help="Output IPA path"),
        bundle_id: Optional[str] = Option(None, "-b", "--bundle-id", help="Override bundle ID"),
    ) -> None:
        """Sign IPA with Apple ID for sideloading (valid for 7 days)."""
        available, msg = _check_signing_available()
        if not available:
            typer.secho(f"Signing not available: {msg}", fg=typer.colors.RED, err=True)
            typer.echo(_get_signing_install_instructions())
            raise typer.Exit(code=1)
        
        try:
            from signing.weekly import WeeklySigner, TwoFactorRequired
            
            typer.secho("[*] Weekly Signing (Apple ID - 7 Days)", fg=typer.colors.CYAN)
            
            signer = WeeklySigner(log_callback=typer_log)
            
            # Authenticate
            try:
                success, auth_msg = signer.authenticate(apple_id, password, code)
            except TwoFactorRequired:
                typer.secho("[!] Two-factor authentication required", fg=typer.colors.YELLOW)
                typer.echo("Please run again with --2fa <code> option")
                raise typer.Exit(code=2)
            
            if not success:
                typer.secho(f"Authentication failed: {auth_msg}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            
            # Sign
            result = signer.sign_ipa(input_ipa, output, udid, bundle_id)
            
            if not result.success:
                typer.secho(f"Error: {result.message}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            
            typer.secho(f"[+] Signed IPA: {result.output_path}", fg=typer.colors.GREEN)
            typer.secho("[!] Remember: Signature valid for 7 days only!", fg=typer.colors.YELLOW)
            
        except ImportError as e:
            typer.secho(f"Import error: {e}", fg=typer.colors.RED, err=True)
            typer.echo(_get_signing_install_instructions())
            raise typer.Exit(code=1)
    
    @cli_app.command("sign-info")
    def cmd_sign_info() -> None:
        """Show signing module information and status."""
        available, msg = _check_signing_available()
        
        if available:
            typer.secho("[+] Signing Module: Available", fg=typer.colors.GREEN)
            
            try:
                from signing import get_signing_info
                info = get_signing_info()
                
                typer.echo(f"\nVersion: {info['version']}")
                typer.echo("\nDependencies:")
                for dep, status in info["dependencies"].items():
                    status_str = "✓" if status else "✗"
                    color = typer.colors.GREEN if status else typer.colors.RED
                    typer.secho(f"  {dep}: {status_str}", fg=color)
                
                typer.echo("\nSigning Methods:")
                for method, desc in info["methods"].items():
                    typer.echo(f"  {method}: {desc}")
                
            except Exception as e:
                typer.secho(f"Error getting info: {e}", fg=typer.colors.RED)
        else:
            typer.secho(f"[-] Signing Module: Not Available", fg=typer.colors.RED)
            typer.echo(f"    Reason: {msg}")
            typer.echo(_get_signing_install_instructions())
    
    # =========================================================================
    # Device Commands (Optional Extension)
    # =========================================================================
    
    @cli_app.command("device-detect")
    def cmd_device_detect() -> None:
        """Detect connected iOS devices."""
        available, msg = _check_device_available()
        if not available:
            typer.secho(f"Device detection not available: {msg}", fg=typer.colors.YELLOW)
            typer.echo(_get_device_install_instructions())
            return
        
        try:
            from device import get_device_manager
            
            manager = get_device_manager()
            manager._log = typer_log
            
            devices = manager.detect_devices()
            
            if not devices:
                typer.secho("No iOS devices detected", fg=typer.colors.YELLOW)
                typer.echo("Make sure your device is:")
                typer.echo("  • Connected via USB")
                typer.echo("  • Unlocked and trusted")
                return
            
            typer.secho(f"\n[+] Found {len(devices)} device(s):\n", fg=typer.colors.GREEN)
            
            for i, device in enumerate(devices, 1):
                typer.echo(f"  {i}. {device.display_name}")
                typer.echo(f"     UDID: {device.udid}")
                if device.ios_version:
                    typer.echo(f"     iOS: {device.ios_version}")
                if device.model:
                    typer.echo(f"     Model: {device.model}")
                typer.echo()
        
        except ImportError as e:
            typer.secho(f"Import error: {e}", fg=typer.colors.RED, err=True)
    
    @cli_app.command("device-install")
    def cmd_device_install(
        ipa_path: str = Argument(..., help="Path to IPA file to install"),
        udid: Optional[str] = Option(None, "--udid", "-u", help="Target device UDID (auto-detect if not provided)"),
    ) -> None:
        """Install IPA to connected iOS device."""
        available, msg = _check_device_available()
        if not available:
            typer.secho(f"Device operations not available: {msg}", fg=typer.colors.RED, err=True)
            typer.echo(_get_device_install_instructions())
            raise typer.Exit(code=1)
        
        try:
            from device import get_device_manager
            from device.models import InstallationStatus
            
            manager = get_device_manager()
            manager._log = typer_log
            
            # Validate IPA
            if not Path(ipa_path).exists():
                typer.secho(f"IPA not found: {ipa_path}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            
            # Get target device
            if udid:
                device = manager.get_device_by_udid(udid)
                if not device:
                    typer.secho(f"Device not found: {udid}", fg=typer.colors.RED, err=True)
                    raise typer.Exit(code=1)
            else:
                devices = manager.detect_devices()
                if not devices:
                    typer.secho("No devices detected", fg=typer.colors.RED, err=True)
                    raise typer.Exit(code=1)
                device = devices[0]
                typer.secho(f"[*] Using device: {device.display_name}", fg=typer.colors.CYAN)
            
            # Install
            def progress_callback(percent: int, message: str):
                typer.echo(f"  [{percent}%] {message}")
            
            from device.models import InstallationOptions
            options = InstallationOptions(progress_callback=progress_callback)
            
            result = manager.install_ipa(device, ipa_path, options)
            
            if result.success:
                typer.secho(f"\n[+] Installation successful!", fg=typer.colors.GREEN)
            else:
                typer.secho(f"\n[-] Installation failed: {result.message}", fg=typer.colors.RED, err=True)
                if result.error_details:
                    typer.echo(f"    Details: {result.error_details}")
                raise typer.Exit(code=1)
        
        except ImportError as e:
            typer.secho(f"Import error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    @cli_app.command("device-info")
    def cmd_device_info() -> None:
        """Show device module information and platform status."""
        available, msg = _check_device_available()
        
        typer.secho("\n=== Device Module Status ===\n", fg=typer.colors.CYAN)
        
        if available:
            typer.secho("[+] Device Module: Available", fg=typer.colors.GREEN)
            
            try:
                from device import get_platform_info
                info = get_platform_info()
                
                typer.echo(f"\nPlatform: {info['platform']}")
                typer.echo(f"Detection: {'✓' if info['detection_supported'] else '✗'}")
                typer.echo(f"Installation: {'✓' if info['installation_supported'] else '✗'}")
                
                deps = info['dependencies']
                typer.echo(f"\nDependencies ({deps.platform}):")
                for dep in deps.dependencies:
                    status = "✓" if dep.installed else "✗"
                    req = "(required)" if dep.required else "(optional)"
                    color = typer.colors.GREEN if dep.installed else (typer.colors.RED if dep.required else typer.colors.YELLOW)
                    typer.secho(f"  {status} {dep.name} {req}", fg=color)
                
                if deps.missing_required:
                    typer.echo(f"\nMissing required: {', '.join(deps.missing_required)}")
                    typer.echo(f"\n{info['installation_instructions']}")
                
            except Exception as e:
                typer.secho(f"Error getting info: {e}", fg=typer.colors.RED)
        else:
            typer.secho(f"[-] Device Module: Not Available", fg=typer.colors.RED)
            typer.echo(f"    Reason: {msg}")
            typer.echo(_get_device_install_instructions())
    
    @cli_app.callback(invoke_without_command=True)
    def main(
        ctx: typer.Context,
        version: bool = Option(False, "--version", "-v", help="Show version"),
    ) -> None:
        """IOS TOOLS - CLI & GUI utility for iOS development."""
        if version:
            typer.echo("ios_tool version 1.0.0")
            raise typer.Exit()
        
        if ctx.invoked_subcommand is None:
            run_gui()
    
    cli_app()


# ============================================================================
# GUI Interface (PyQt6 - Clean Default Style)
# ============================================================================

def run_gui():
    """Run the GUI interface using PyQt6."""
    try:
        from PyQt6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QTabWidget, QLabel, QLineEdit, QPushButton, QTextEdit,
            QFileDialog, QMessageBox, QFrame, QGroupBox, QProgressBar,
            QStackedWidget, QScrollArea
        )
        from PyQt6.QtCore import (
            Qt, QTimer, QThread, pyqtSignal, QRectF, QPointF, QSize
        )
        from PyQt6.QtGui import (
            QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
            QRadialGradient, QPainterPath, QPalette, QFontDatabase,
            QIcon, QPixmap
        )
    except ImportError:
        print("Error: PyQt6 is required for GUI mode.")
        print("Install with: pip install PyQt6")
        sys.exit(1)
    
    # Get logo path
    def get_resource_path(filename: str) -> Path:
        """Get path to resource file, works for dev and PyInstaller bundle."""
        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent
        return base_path / filename
    
    logo_path = get_resource_path("logo.jpg")
    
    # ============ Worker Thread ============
    class WorkerThread(QThread):
        """Worker thread for long-running operations."""
        finished = pyqtSignal(bool, str)
        log_signal = pyqtSignal(str, str)
        
        def __init__(self, func, *args, **kwargs):
            super().__init__()
            self.func = func
            self.args = args
            self.kwargs = kwargs
        
        def run(self):
            try:
                success, result = self.func(*self.args, **self.kwargs)
                self.finished.emit(success, result)
            except Exception as e:
                self.finished.emit(False, str(e))
    
    # ============ Main Window (Clean Default Style) ============
    class IOSToolGUI(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("iOS Tools Maker")
            self.setMinimumSize(800, 600)
            self.resize(900, 700)
            
            if logo_path.exists():
                self.setWindowIcon(QIcon(str(logo_path)))
            
            self.core = IOSToolCore(log_callback=self._log_from_core)
            self.worker = None
            self._last_signed_ipa = None
            self._detected_devices = []
            
            self._setup_ui()
        
        def _log_from_core(self, message: str, level: str = "info"):
            """Thread-safe logging from core."""
            self.log_text.append(message)
        
        def _format_log(self, message: str, level: str) -> str:
            return message
        
        def _setup_ui(self):
            # Central widget
            central = QWidget()
            self.setCentralWidget(central)
            
            # Main layout
            main_layout = QVBoxLayout(central)
            main_layout.setContentsMargins(20, 20, 20, 20)
            main_layout.setSpacing(15)
            
            # Title
            title = QLabel("iOS Tools Maker")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
            main_layout.addWidget(title)
            
            subtitle = QLabel("Build • Sign • Deploy")
            subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle.setFont(QFont("Segoe UI", 10))
            main_layout.addWidget(subtitle)
            
            # Tab widget
            self.tabs = QTabWidget()
            main_layout.addWidget(self.tabs, stretch=2)
            
            # Create tabs
            self._create_app2ipa_tab()
            self._create_folder2deb_tab()
            self._create_build_dylib_tab()
            self._create_compile_tab()
            self._create_sign_annual_tab()
            self._create_sign_weekly_tab()
            self._create_device_tab()
            
            # Log area
            log_group = QGroupBox("Console")
            log_layout = QVBoxLayout(log_group)
            
            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)
            self.log_text.setFont(QFont("Consolas", 9))
            self.log_text.setMaximumHeight(120)
            log_layout.addWidget(self.log_text)
            
            clear_btn = QPushButton("Clear")
            clear_btn.setFixedWidth(80)
            clear_btn.clicked.connect(lambda: self.log_text.clear())
            log_layout.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignRight)
            
            main_layout.addWidget(log_group)
            
            # Progress bar
            self.progress = QProgressBar()
            self.progress.setVisible(False)
            self.progress.setTextVisible(False)
            self.progress.setMaximum(0)
            main_layout.addWidget(self.progress)
        
        def _create_section_label(self, text: str) -> QLabel:
            """Create a section label."""
            label = QLabel(text)
            label.setFont(QFont("Segoe UI", 9))
            return label
        
        def _create_app2ipa_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            
            # Input section
            layout.addWidget(self._create_section_label("Input .app Directory:"))
            input_layout = QHBoxLayout()
            self.app2ipa_input = QLineEdit()
            self.app2ipa_input.setPlaceholderText("Select .app folder...")
            input_layout.addWidget(self.app2ipa_input)
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda: self._browse_dir(self.app2ipa_input))
            input_layout.addWidget(browse_btn)
            layout.addLayout(input_layout)
            
            # Output section
            layout.addWidget(self._create_section_label("Output .ipa File (Optional):"))
            output_layout = QHBoxLayout()
            self.app2ipa_output = QLineEdit()
            self.app2ipa_output.setPlaceholderText("Leave empty for default...")
            output_layout.addWidget(self.app2ipa_output)
            browse_btn2 = QPushButton("Browse")
            browse_btn2.clicked.connect(lambda: self._browse_save(self.app2ipa_output, "IPA Files (*.ipa)"))
            output_layout.addWidget(browse_btn2)
            layout.addLayout(output_layout)
            
            layout.addStretch()
            
            # Convert button
            self.app2ipa_btn = QPushButton("Convert to IPA")
            self.app2ipa_btn.clicked.connect(self._run_app2ipa)
            layout.addWidget(self.app2ipa_btn)
            
            self.tabs.addTab(tab, "App to IPA")
        
        def _create_folder2deb_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            
            # Input section
            layout.addWidget(self._create_section_label("Package Root Directory:"))
            input_layout = QHBoxLayout()
            self.folder2deb_input = QLineEdit()
            self.folder2deb_input.setPlaceholderText("Must contain DEBIAN/control...")
            input_layout.addWidget(self.folder2deb_input)
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda: self._browse_dir(self.folder2deb_input))
            input_layout.addWidget(browse_btn)
            layout.addLayout(input_layout)
            
            # Output section
            layout.addWidget(self._create_section_label("Output .deb File (Optional):"))
            output_layout = QHBoxLayout()
            self.folder2deb_output = QLineEdit()
            self.folder2deb_output.setPlaceholderText("Leave empty for default...")
            output_layout.addWidget(self.folder2deb_output)
            browse_btn2 = QPushButton("Browse")
            browse_btn2.clicked.connect(lambda: self._browse_save(self.folder2deb_output, "DEB Files (*.deb)"))
            output_layout.addWidget(browse_btn2)
            layout.addLayout(output_layout)
            
            layout.addStretch()
            
            # Build button
            self.folder2deb_btn = QPushButton("Build DEB Package")
            self.folder2deb_btn.clicked.connect(self._run_folder2deb)
            layout.addWidget(self.folder2deb_btn)
            
            self.tabs.addTab(tab, "Folder to DEB")
        
        def _create_build_dylib_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            
            # Input section
            layout.addWidget(self._create_section_label("Source Files (.c/.m/.swift):"))
            input_layout = QHBoxLayout()
            self.dylib_input = QLineEdit()
            self.dylib_input.setPlaceholderText("Select source file(s)...")
            input_layout.addWidget(self.dylib_input)
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda: self._browse_files(self.dylib_input, "Source Files (*.c *.m *.swift)"))
            input_layout.addWidget(browse_btn)
            layout.addLayout(input_layout)
            
            # Output section
            layout.addWidget(self._create_section_label("Output .dylib File (Optional):"))
            output_layout = QHBoxLayout()
            self.dylib_output = QLineEdit()
            self.dylib_output.setPlaceholderText("Leave empty for default...")
            output_layout.addWidget(self.dylib_output)
            browse_btn2 = QPushButton("Browse")
            browse_btn2.clicked.connect(lambda: self._browse_save(self.dylib_output, "Dylib Files (*.dylib)"))
            output_layout.addWidget(browse_btn2)
            layout.addLayout(output_layout)
            
            layout.addStretch()
            
            # Build button
            self.dylib_btn = QPushButton("Build Dynamic Library")
            self.dylib_btn.clicked.connect(self._run_build_dylib)
            layout.addWidget(self.dylib_btn)
            
            self.tabs.addTab(tab, "Build Dylib")
        
        def _create_compile_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            
            # Input section
            layout.addWidget(self._create_section_label("Source File:"))
            input_layout = QHBoxLayout()
            self.compile_input = QLineEdit()
            self.compile_input.setPlaceholderText("Select source file...")
            input_layout.addWidget(self.compile_input)
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda: self._browse_file(self.compile_input, "Source Files (*.c *.m *.swift)"))
            input_layout.addWidget(browse_btn)
            layout.addLayout(input_layout)
            
            # Output section
            layout.addWidget(self._create_section_label("Output Executable (Optional):"))
            output_layout = QHBoxLayout()
            self.compile_output = QLineEdit()
            self.compile_output.setPlaceholderText("Leave empty for default...")
            output_layout.addWidget(self.compile_output)
            browse_btn2 = QPushButton("Browse")
            browse_btn2.clicked.connect(lambda: self._browse_save(self.compile_output, "All Files (*)"))
            output_layout.addWidget(browse_btn2)
            layout.addLayout(output_layout)
            
            layout.addStretch()
            
            # Compile button
            self.compile_btn = QPushButton("Compile")
            self.compile_btn.clicked.connect(self._run_compile)
            layout.addWidget(self.compile_btn)
            
            self.tabs.addTab(tab, "Compile")
        
        def _create_sign_annual_tab(self):
            """Create Annual Signing tab (P12 + Provisioning)."""
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            
            # Check if signing is available
            signing_available, signing_msg = _check_signing_available()
            
            if not signing_available:
                info_label = QLabel(
                    f"Annual Signing (Developer Certificate)\n\n"
                    f"Status: Not Available\nReason: {signing_msg}\n\n"
                    "Install: pip install cryptography pyOpenSSL"
                )
                info_label.setWordWrap(True)
                layout.addWidget(info_label)
                layout.addStretch()
                self.tabs.addTab(tab, "Sign (Annual)")
                return
            
            # IPA Input
            layout.addWidget(self._create_section_label("Input IPA File:"))
            ipa_layout = QHBoxLayout()
            self.annual_ipa_input = QLineEdit()
            self.annual_ipa_input.setPlaceholderText("Select IPA file to sign...")
            ipa_layout.addWidget(self.annual_ipa_input)
            browse_ipa = QPushButton("Browse")
            browse_ipa.clicked.connect(lambda: self._browse_file(self.annual_ipa_input, "IPA Files (*.ipa)"))
            ipa_layout.addWidget(browse_ipa)
            layout.addLayout(ipa_layout)
            
            # P12 Input
            layout.addWidget(self._create_section_label("P12 Certificate:"))
            p12_layout = QHBoxLayout()
            self.annual_p12_input = QLineEdit()
            self.annual_p12_input.setPlaceholderText("Select .p12 certificate file...")
            p12_layout.addWidget(self.annual_p12_input)
            browse_p12 = QPushButton("Browse")
            browse_p12.clicked.connect(lambda: self._browse_file(self.annual_p12_input, "P12 Files (*.p12)"))
            p12_layout.addWidget(browse_p12)
            layout.addLayout(p12_layout)
            
            # P12 Password
            layout.addWidget(self._create_section_label("P12 Password:"))
            self.annual_password = QLineEdit()
            self.annual_password.setPlaceholderText("Certificate password...")
            self.annual_password.setEchoMode(QLineEdit.EchoMode.Password)
            layout.addWidget(self.annual_password)
            
            # Provisioning Profile
            layout.addWidget(self._create_section_label("Provisioning Profile:"))
            prov_layout = QHBoxLayout()
            self.annual_provision_input = QLineEdit()
            self.annual_provision_input.setPlaceholderText("Select .mobileprovision file...")
            prov_layout.addWidget(self.annual_provision_input)
            browse_prov = QPushButton("Browse")
            browse_prov.clicked.connect(lambda: self._browse_file(self.annual_provision_input, "Provisioning (*.mobileprovision)"))
            prov_layout.addWidget(browse_prov)
            layout.addLayout(prov_layout)
            
            # Output
            layout.addWidget(self._create_section_label("Output IPA (Optional):"))
            out_layout = QHBoxLayout()
            self.annual_output = QLineEdit()
            self.annual_output.setPlaceholderText("Leave empty for default...")
            out_layout.addWidget(self.annual_output)
            browse_out = QPushButton("Browse")
            browse_out.clicked.connect(lambda: self._browse_save(self.annual_output, "IPA Files (*.ipa)"))
            out_layout.addWidget(browse_out)
            layout.addLayout(out_layout)
            
            layout.addStretch()
            
            # Sign button
            self.annual_sign_btn = QPushButton("Sign IPA (Annual)")
            self.annual_sign_btn.clicked.connect(self._run_sign_annual)
            layout.addWidget(self.annual_sign_btn)
            
            self.tabs.addTab(tab, "Sign (Annual)")
        
        def _create_sign_weekly_tab(self):
            """Create Weekly Signing tab (Apple ID)."""
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            
            # Check if signing is available
            signing_available, signing_msg = _check_signing_available()
            
            if not signing_available:
                info_label = QLabel(
                    f"Weekly Signing (Apple ID)\n\n"
                    f"Status: Not Available\nReason: {signing_msg}\n\n"
                    "Install: pip install cryptography pyOpenSSL requests"
                )
                info_label.setWordWrap(True)
                layout.addWidget(info_label)
                layout.addStretch()
                self.tabs.addTab(tab, "Sign (Weekly)")
                return
            
            # IPA Input
            layout.addWidget(self._create_section_label("Input IPA File:"))
            ipa_layout = QHBoxLayout()
            self.weekly_ipa_input = QLineEdit()
            self.weekly_ipa_input.setPlaceholderText("Select IPA file to sign...")
            ipa_layout.addWidget(self.weekly_ipa_input)
            browse_ipa = QPushButton("Browse")
            browse_ipa.clicked.connect(lambda: self._browse_file(self.weekly_ipa_input, "IPA Files (*.ipa)"))
            ipa_layout.addWidget(browse_ipa)
            layout.addLayout(ipa_layout)
            
            # Apple ID
            layout.addWidget(self._create_section_label("Apple ID:"))
            self.weekly_apple_id = QLineEdit()
            self.weekly_apple_id.setPlaceholderText("your@apple.id")
            layout.addWidget(self.weekly_apple_id)
            
            # Password
            layout.addWidget(self._create_section_label("Apple ID Password:"))
            self.weekly_password = QLineEdit()
            self.weekly_password.setPlaceholderText("App-specific password recommended")
            self.weekly_password.setEchoMode(QLineEdit.EchoMode.Password)
            layout.addWidget(self.weekly_password)
            
            # Device UDID
            layout.addWidget(self._create_section_label("Device UDID:"))
            self.weekly_udid = QLineEdit()
            self.weekly_udid.setPlaceholderText("40-character device UDID...")
            layout.addWidget(self.weekly_udid)
            
            # 2FA Code
            layout.addWidget(self._create_section_label("2FA Code (if required):"))
            self.weekly_2fa = QLineEdit()
            self.weekly_2fa.setPlaceholderText("6-digit verification code...")
            layout.addWidget(self.weekly_2fa)
            
            layout.addStretch()
            
            # Sign button
            self.weekly_sign_btn = QPushButton("Sign IPA (Weekly)")
            self.weekly_sign_btn.clicked.connect(self._run_sign_weekly)
            layout.addWidget(self.weekly_sign_btn)
            
            # Warning
            warning = QLabel("Note: Signature valid for 7 days only. Must re-sign weekly.")
            warning.setFont(QFont("Segoe UI", 9))
            layout.addWidget(warning)
            
            layout.addStretch()
            self.tabs.addTab(tab, "Sign (Weekly)")
        
        def _create_device_tab(self):
            """Create Device Management tab."""
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            
            # Check if device module is available
            device_available, device_msg = _check_device_available()
            
            import platform
            platform_name = platform.system()
            
            # Status
            status_group = QGroupBox("Platform Status")
            status_layout = QVBoxLayout(status_group)
            
            self.device_status_label = QLabel(f"Platform: {platform_name}")
            status_layout.addWidget(self.device_status_label)
            
            detection_status = "Available" if device_available else f"Not Available: {device_msg}"
            self.device_detection_label = QLabel(f"Detection: {detection_status}")
            status_layout.addWidget(self.device_detection_label)
            
            layout.addWidget(status_group)
            
            if not device_available:
                instructions = _get_device_install_instructions()
                info_label = QLabel(instructions[:500] + "..." if len(instructions) > 500 else instructions)
                info_label.setWordWrap(True)
                layout.addWidget(info_label)
                layout.addStretch()
                self.tabs.addTab(tab, "Device")
                return
            
            # Device list
            layout.addWidget(self._create_section_label("Connected Devices:"))
            
            self.device_list_frame = QFrame()
            self.device_list_frame.setFrameShape(QFrame.Shape.StyledPanel)
            self.device_list_frame.setMinimumHeight(80)
            self.device_list_layout = QVBoxLayout(self.device_list_frame)
            
            self.no_device_label = QLabel("No devices detected. Click 'Detect Devices' to scan.")
            self.no_device_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.device_list_layout.addWidget(self.no_device_label)
            
            layout.addWidget(self.device_list_frame)
            
            # Detect button
            detect_btn = QPushButton("Detect Devices")
            detect_btn.clicked.connect(self._detect_devices)
            layout.addWidget(detect_btn)
            
            # IPA Installation
            layout.addWidget(self._create_section_label("Install IPA to Device:"))
            
            ipa_layout = QHBoxLayout()
            self.device_ipa_input = QLineEdit()
            self.device_ipa_input.setPlaceholderText("Select signed IPA file...")
            ipa_layout.addWidget(self.device_ipa_input)
            browse_ipa = QPushButton("Browse")
            browse_ipa.clicked.connect(lambda: self._browse_file(self.device_ipa_input, "IPA Files (*.ipa)"))
            ipa_layout.addWidget(browse_ipa)
            layout.addLayout(ipa_layout)
            
            layout.addStretch()
            
            # Install button
            self.device_install_btn = QPushButton("Install to Device")
            self.device_install_btn.clicked.connect(self._install_to_device)
            layout.addWidget(self.device_install_btn)
            
            note = QLabel("Device must be connected via USB and trusted")
            note.setFont(QFont("Segoe UI", 9))
            layout.addWidget(note)
            
            layout.addStretch()
            self.tabs.addTab(tab, "Device")
            
            # Store detected devices
            self._detected_devices = []
        
        def _detect_devices(self):
            """Detect connected iOS devices."""
            self.log_text.append("[>] Detecting iOS devices...")
            
            try:
                from device import get_device_manager
                
                manager = get_device_manager()
                devices = manager.detect_devices()
                self._detected_devices = devices
                
                # Clear old device labels
                while self.device_list_layout.count() > 0:
                    item = self.device_list_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                
                if devices:
                    for i, device in enumerate(devices):
                        device_widget = QFrame()
                        device_widget.setFrameShape(QFrame.Shape.StyledPanel)
                        device_layout = QVBoxLayout(device_widget)
                        device_layout.setSpacing(2)
                        
                        name_label = QLabel(f"{device.display_name}")
                        name_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                        device_layout.addWidget(name_label)
                        
                        udid_label = QLabel(f"UDID: {device.short_udid}")
                        udid_label.setFont(QFont("Segoe UI", 9))
                        device_layout.addWidget(udid_label)
                        
                        if device.ios_version:
                            ios_label = QLabel(f"iOS: {device.ios_version}")
                            ios_label.setFont(QFont("Segoe UI", 9))
                            device_layout.addWidget(ios_label)
                        
                        self.device_list_layout.addWidget(device_widget)
                        device_widget.setProperty("device_index", i)
                    
                    self.log_text.append(f"[+] Found {len(devices)} device(s)")
                else:
                    self.no_device_label = QLabel("No devices detected")
                    self.no_device_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.device_list_layout.addWidget(self.no_device_label)
                    self.log_text.append("[!] No devices detected")
            
            except ImportError as e:
                self.log_text.append(f"[!] Device module error: {e}")
            except Exception as e:
                self.log_text.append(f"[!] Detection error: {e}")
        
        def _install_to_device(self):
            """Install IPA to connected device."""
            ipa_path = self.device_ipa_input.text().strip()
            
            if not ipa_path:
                QMessageBox.warning(self, "Warning", "Please select an IPA file to install")
                return
            
            if not self._detected_devices:
                QMessageBox.warning(self, "Warning", "No devices detected. Please click 'Detect Devices' first.")
                return
            
            # Use first detected device
            device = self._detected_devices[0]
            
            self.log_text.append(self._format_log("=" * 50, "info"))
            self.log_text.append(self._format_log(f"[>] Installing to {device.display_name}...", "info"))
            
            self._set_busy(True, self.device_install_btn)
            
            def do_install():
                try:
                    from device import get_device_manager
                    from device.models import InstallationOptions
                    
                    manager = get_device_manager()
                    
                    def progress_callback(percent, message):
                        self.log_text.append(self._format_log(f"  [{percent}%] {message}", "info"))
                    
                    options = InstallationOptions(progress_callback=progress_callback)
                    result = manager.install_ipa(device, ipa_path, options)
                    
                    return result.success, result.message
                except Exception as e:
                    return False, str(e)
            
            self.worker = WorkerThread(do_install)
            self.worker.finished.connect(lambda s, r: self._on_device_install_finished(s, r))
            self.worker.start()
        
        def _on_device_install_finished(self, success: bool, message: str):
            """Handle device installation completion."""
            self._set_busy(False, self.device_install_btn)
            if success:
                self.log_text.append(self._format_log("[+] Installation successful!", "success"))
                QMessageBox.information(self, "Success", "IPA installed successfully!")
            else:
                self.log_text.append(self._format_log(f"[-] Installation failed: {message}", "error"))
                QMessageBox.critical(self, "Error", f"Installation failed:\n{message}")
        
        def _browse_file(self, line_edit: QLineEdit, filter_str: str):
            path, _ = QFileDialog.getOpenFileName(self, "Select File", "", filter_str)
            if path:
                line_edit.setText(path)
        
        def _browse_dir(self, line_edit: QLineEdit):
            path = QFileDialog.getExistingDirectory(self, "Select Directory")
            if path:
                line_edit.setText(path)
        
        def _browse_save(self, line_edit: QLineEdit, filter_str: str):
            path, _ = QFileDialog.getSaveFileName(self, "Save File", "", filter_str)
            if path:
                line_edit.setText(path)
        
        def _set_busy(self, busy: bool, button: QPushButton):
            button.setEnabled(not busy)
            self.progress.setVisible(busy)
        
        def _on_finished(self, success: bool, result: str, button: QPushButton):
            self._set_busy(False, button)
            if success:
                QMessageBox.information(self, "Success", f"Created:\n{result}")
            else:
                QMessageBox.critical(self, "Error", result)
        
        def _run_app2ipa(self):
            input_path = self.app2ipa_input.text().strip()
            output_path = self.app2ipa_output.text().strip() or None
            
            if not input_path:
                QMessageBox.warning(self, "Warning", "Please select an input .app directory")
                return
            
            self.log_text.append(self._format_log("=" * 50, "info"))
            self.log_text.append(self._format_log("[>] Starting app2ipa conversion...", "info"))
            
            self._set_busy(True, self.app2ipa_btn)
            
            self.worker = WorkerThread(self.core.app2ipa, input_path, output_path)
            self.worker.finished.connect(lambda s, r: self._on_finished(s, r, self.app2ipa_btn))
            self.worker.start()
        
        def _run_folder2deb(self):
            input_path = self.folder2deb_input.text().strip()
            output_path = self.folder2deb_output.text().strip() or None
            
            if not input_path:
                QMessageBox.warning(self, "Warning", "Please select a package root directory")
                return
            
            self.log_text.append(self._format_log("=" * 50, "info"))
            self.log_text.append(self._format_log("[>] Starting folder2deb build...", "info"))
            
            self._set_busy(True, self.folder2deb_btn)
            
            self.worker = WorkerThread(self.core.folder2deb, input_path, output_path)
            self.worker.finished.connect(lambda s, r: self._on_finished(s, r, self.folder2deb_btn))
            self.worker.start()
        
        def _run_build_dylib(self):
            input_path = self.dylib_input.text().strip()
            output_name = self.dylib_output.text().strip() or None
            source_file = self.dylib_source.text().strip() or None
            
            if not input_path:
                QMessageBox.warning(self, "Warning", "Please select a project directory")
                return
            
            self.log_text.append(self._format_log("=" * 50, "info"))
            self.log_text.append(self._format_log("[>] Starting dylib build...", "info"))
            
            self._set_busy(True, self.dylib_btn)
            
            self.worker = WorkerThread(self.core.build_dylib, input_path, output_name, source_file)
            self.worker.finished.connect(lambda s, r: self._on_finished(s, r, self.dylib_btn))
            self.worker.start()
        
        def _run_compile(self):
            output_name = self.compile_output.text().strip() or None
            
            self.log_text.append(self._format_log("=" * 50, "info"))
            self.log_text.append(self._format_log("[>] Compiling standalone executable...", "info"))
            self.log_text.append(self._format_log("[*] This may take a few minutes...", "info"))
            
            self._set_busy(True, self.compile_btn)
            
            self.worker = WorkerThread(self.core.compile_binary, None, output_name, None, None, True)
            self.worker.finished.connect(lambda s, r: self._on_finished(s, r, self.compile_btn))
            self.worker.start()
        
        def _run_sign_annual(self):
            """Run annual signing (P12 + Provisioning)."""
            ipa_path = self.annual_ipa_input.text().strip()
            p12_path = self.annual_p12_input.text().strip()
            password = self.annual_password.text()
            provision_path = self.annual_provision_input.text().strip()
            output_path = self.annual_output.text().strip() or None
            
            # Validation
            if not ipa_path:
                QMessageBox.warning(self, "Warning", "Please select an input IPA file")
                return
            if not p12_path:
                QMessageBox.warning(self, "Warning", "Please select a P12 certificate")
                return
            if not provision_path:
                QMessageBox.warning(self, "Warning", "Please select a provisioning profile")
                return
            
            self.log_text.append(self._format_log("=" * 50, "info"))
            self.log_text.append(self._format_log("[>] Starting Annual Signing...", "info"))
            self.log_text.append(self._format_log("[*] Validating certificate and profile...", "info"))
            
            self._set_busy(True, self.annual_sign_btn)
            
            def sign_task():
                try:
                    from signing.annual import AnnualSigner
                    
                    signer = AnnualSigner(
                        p12_path=p12_path,
                        provision_path=provision_path,
                        p12_password=password,
                        log_callback=self._log_from_core
                    )
                    
                    valid, msg = signer.validate()
                    if not valid:
                        return False, f"Validation failed: {msg}"
                    
                    result = signer.sign_ipa(ipa_path, output_path)
                    
                    if result.success:
                        return True, str(result.output_path)
                    else:
                        return False, result.message
                        
                except Exception as e:
                    return False, str(e)
            
            self.worker = WorkerThread(sign_task)
            self.worker.finished.connect(lambda s, r: self._on_sign_annual_finished(s, r))
            self.worker.start()
        
        def _on_sign_annual_finished(self, success: bool, result: str):
            """Handle annual signing completion with smart install suggestion."""
            self._set_busy(False, self.annual_sign_btn)
            if success:
                self._last_signed_ipa = result
                self._suggest_device_install(result)
            else:
                QMessageBox.critical(self, "Error", result)
        
        def _run_sign_weekly(self):
            """Run weekly signing (Apple ID)."""
            ipa_path = self.weekly_ipa_input.text().strip()
            apple_id = self.weekly_apple_id.text().strip()
            password = self.weekly_password.text()
            udid = self.weekly_udid.text().strip()
            code_2fa = self.weekly_2fa.text().strip() or None
            
            # Validation
            if not ipa_path:
                QMessageBox.warning(self, "Warning", "Please select an input IPA file")
                return
            if not apple_id:
                QMessageBox.warning(self, "Warning", "Please enter your Apple ID")
                return
            if not password:
                QMessageBox.warning(self, "Warning", "Please enter your password")
                return
            if not udid:
                QMessageBox.warning(self, "Warning", "Please enter the device UDID")
                return
            
            # Check if we should reuse existing signer (for 2FA flow)
            reuse_signer = code_2fa and hasattr(self, '_weekly_signer') and self._weekly_signer is not None
            
            self.log_text.append(self._format_log("=" * 50, "info"))
            self.log_text.append(self._format_log("[>] Starting Weekly Signing...", "info"))
            self.log_text.append(self._format_log("[*] Authenticating with Apple ID...", "info"))
            
            self._set_busy(True, self.weekly_sign_btn)
            
            # Capture reuse_signer in closure
            _reuse_signer = reuse_signer
            _self = self
            
            def sign_task():
                try:
                    from signing.weekly import WeeklySigner
                    from signing.apple_auth import TwoFactorRequired
                    
                    # Reuse existing signer if we have 2FA code, otherwise create new
                    if _reuse_signer:
                        signer = getattr(_self, '_weekly_signer', None)
                        if signer is None:
                            signer = WeeklySigner(log_callback=_self._log_from_core)
                    else:
                        signer = WeeklySigner(log_callback=_self._log_from_core)
                    
                    # Store for 2FA flow (always)
                    _self._weekly_signer = signer
                    
                    try:
                        success, msg = signer.authenticate(apple_id, password, code_2fa)
                    except TwoFactorRequired as e:
                        # 2FA code was sent to device - keep signer for later
                        return False, "2FA_REQUIRED:"
                    
                    if not success:
                        return False, f"Authentication failed: {msg}"
                    
                    result = signer.sign_ipa(ipa_path, None, udid)
                    
                    if result.success:
                        return True, str(result.output_path)
                    else:
                        return False, result.message
                        
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    return False, str(e)
            
            self.worker = WorkerThread(sign_task)
            self.worker.finished.connect(lambda s, r: self._on_sign_weekly_finished(s, r))
            self.worker.start()
        
        def _on_sign_weekly_finished(self, success: bool, result: str):
            """Handle weekly signing completion with smart install suggestion."""
            self._set_busy(False, self.weekly_sign_btn)
            if success:
                self._weekly_signer = None  # Clear signer on success
                self._last_signed_ipa = result
                self._suggest_device_install(result, is_weekly=True)
            elif result.startswith("2FA_REQUIRED"):
                # Show 2FA input dialog - signer is preserved for next call
                self.log_text.append(self._format_log("[*] 2FA code sent to your devices", "info"))
                self._show_2fa_dialog()
            else:
                self._weekly_signer = None  # Clear signer on error
                QMessageBox.critical(self, "Error", result)
        
        def _show_2fa_dialog(self):
            """Show popup dialog to enter 2FA code."""
            from PyQt6.QtWidgets import QInputDialog
            
            code, ok = QInputDialog.getText(
                self,
                "Two-Factor Authentication",
                "A verification code was sent to your Apple devices.\n\nEnter the 6-digit code:",
                QLineEdit.EchoMode.Normal,
                ""
            )
            
            if ok and code:
                code = code.strip().replace(" ", "").replace("-", "")
                if len(code) == 6 and code.isdigit():
                    # Set the code and re-run signing
                    self.weekly_2fa.setText(code)
                    self._run_sign_weekly()
                else:
                    QMessageBox.warning(self, "Invalid Code", "Please enter a valid 6-digit code.")
                    self._show_2fa_dialog()  # Show dialog again
            else:
                self.log_text.append(self._format_log("[!] 2FA verification cancelled", "warning"))
        
        def _suggest_device_install(self, signed_ipa_path: str, is_weekly: bool = False):
            """Smart suggestion to install signed IPA to connected device."""
            try:
                from device import get_device_manager
                
                # Check if device module is available
                available, _ = _check_device_available()
                if not available:
                    # Just show success without device suggestion
                    validity_msg = "\n\n⚠️ Valid for 7 days only!" if is_weekly else ""
                    QMessageBox.information(
                        self, 
                        "Success", 
                        f"Signed IPA created:\n{signed_ipa_path}{validity_msg}"
                    )
                    return
                
                manager = get_device_manager()
                devices = manager.detect_devices()
                
                if not devices:
                    # No device connected, just show success
                    validity_msg = "\n\n⚠️ Valid for 7 days only!" if is_weekly else ""
                    QMessageBox.information(
                        self, 
                        "Success", 
                        f"Signed IPA created:\n{signed_ipa_path}{validity_msg}"
                    )
                    return
                
                # Device found! Ask user if they want to install
                device = devices[0]
                validity_msg = "\n⚠️ Signature valid for 7 days only!" if is_weekly else ""
                
                reply = QMessageBox.question(
                    self,
                    "Install to Device?",
                    f"Signed IPA created successfully!\n\n"
                    f"📄 {Path(signed_ipa_path).name}\n"
                    f"📱 Device detected: {device.display_name}\n"
                    f"{validity_msg}\n\n"
                    f"Would you like to install it to the device now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    # Fill in the device tab and trigger install
                    self.device_ipa_input.setText(signed_ipa_path)
                    self._detected_devices = devices
                    self.tabs.setCurrentWidget(self.tabs.widget(self.tabs.count() - 1))  # Switch to Device tab
                    self._install_to_device()
                else:
                    self.log_text.append(self._format_log(f"[+] Signed IPA saved: {signed_ipa_path}", "success"))
                    
            except ImportError:
                # Device module not available, just show success
                validity_msg = "\n\n⚠️ Valid for 7 days only!" if is_weekly else ""
                QMessageBox.information(
                    self, 
                    "Success", 
                    f"Signed IPA created:\n{signed_ipa_path}{validity_msg}"
                )
            except Exception as e:
                # Error checking devices, still show success for signing
                validity_msg = "\n\n⚠️ Valid for 7 days only!" if is_weekly else ""
                QMessageBox.information(
                    self, 
                    "Success", 
                    f"Signed IPA created:\n{signed_ipa_path}{validity_msg}"
                )
    
    # Run the application
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Set application icon (for taskbar)
    if logo_path.exists():
        app.setWindowIcon(QIcon(str(logo_path)))
    
    window = IOSToolGUI()
    window.show()
    
    sys.exit(app.exec())


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli()
    else:
        run_gui()
