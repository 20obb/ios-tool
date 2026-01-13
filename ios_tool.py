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
# GUI Interface (PyQt6 with Grok-style Milky Way Background)
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
            Qt, QTimer, QThread, pyqtSignal, QRectF, QPointF
        )
        from PyQt6.QtGui import (
            QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
            QRadialGradient, QPainterPath, QPalette, QFontDatabase
        )
    except ImportError:
        print("Error: PyQt6 is required for GUI mode.")
        print("Install with: pip install PyQt6")
        sys.exit(1)
    
    # ============ Simple Universe Background ============
    @dataclass
    class Star:
        x: float
        y: float
        z: float  # Depth for parallax
        size: float
        brightness: float
    
    class UniverseWidget(QWidget):
        """Simple animated universe with flowing stars - Grok style."""
        
        def __init__(self, parent=None):
            super().__init__(parent)
            self.stars: List[Star] = []
            self.time = 0.0
            self.center_x = 0.0
            self.center_y = 0.0
            
            self._init_stars()
            
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._animate)
            self.timer.start(16)  # ~60 FPS for smooth animation
        
        def _init_stars(self):
            """Initialize star field."""
            self.stars.clear()
            
            # Create 300 stars at random positions with depth
            for _ in range(300):
                self.stars.append(Star(
                    x=random.uniform(-1, 1),
                    y=random.uniform(-1, 1),
                    z=random.uniform(0.1, 1.0),
                    size=random.uniform(1, 3),
                    brightness=random.uniform(0.4, 1.0)
                ))
        
        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.center_x = self.width() / 2
            self.center_y = self.height() / 2
        
        def _animate(self):
            """Update star positions - move toward viewer."""
            self.time += 0.008
            
            for star in self.stars:
                # Move stars toward viewer (decrease z)
                star.z -= 0.002
                
                # Reset star when it passes the viewer
                if star.z <= 0.01:
                    star.x = random.uniform(-1, 1)
                    star.y = random.uniform(-1, 1)
                    star.z = 1.0
                    star.brightness = random.uniform(0.4, 1.0)
            
            self.update()
        
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            w = self.width()
            h = self.height()
            cx = w / 2
            cy = h / 2
            
            # Pure black background
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            
            # Draw subtle gradient glow in center (like distant galaxy)
            glow = QRadialGradient(cx, cy * 0.7, max(w, h) * 0.4)
            glow.setColorAt(0.0, QColor(40, 40, 60, 30))
            glow.setColorAt(0.5, QColor(20, 20, 40, 15))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QRectF(0, 0, w, h))
            
            # Sort stars by depth (far to near)
            sorted_stars = sorted(self.stars, key=lambda s: s.z, reverse=True)
            
            # Draw stars with perspective projection
            for star in sorted_stars:
                # Project 3D to 2D with perspective
                scale = 1.0 / star.z
                screen_x = cx + star.x * scale * w * 0.5
                screen_y = cy + star.y * scale * h * 0.5
                
                # Skip if outside screen
                if screen_x < -50 or screen_x > w + 50 or screen_y < -50 or screen_y > h + 50:
                    continue
                
                # Size and brightness based on depth
                size = star.size * scale * 0.8
                size = min(size, 8)  # Cap max size
                
                alpha = int(star.brightness * (1.0 - star.z * 0.5) * 255)
                alpha = max(0, min(255, alpha))
                
                if alpha < 15:
                    continue
                
                # Draw star glow for closer stars
                if size > 2:
                    glow_size = size * 3
                    glow_gradient = QRadialGradient(screen_x, screen_y, glow_size)
                    glow_gradient.setColorAt(0.0, QColor(255, 255, 255, alpha // 4))
                    glow_gradient.setColorAt(0.5, QColor(200, 210, 255, alpha // 8))
                    glow_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
                    painter.setBrush(QBrush(glow_gradient))
                    painter.drawEllipse(QRectF(
                        screen_x - glow_size,
                        screen_y - glow_size,
                        glow_size * 2,
                        glow_size * 2
                    ))
                
                # Draw star core
                color = QColor(255, 255, 255, alpha)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QRectF(
                    screen_x - size / 2,
                    screen_y - size / 2,
                    size,
                    size
                ))
                
                # Draw motion trail for fast-moving close stars
                if star.z < 0.3 and size > 1.5:
                    trail_length = (0.3 - star.z) * 30
                    trail_alpha = alpha // 3
                    
                    # Trail going toward center
                    dx = screen_x - cx
                    dy = screen_y - cy
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist > 0:
                        trail_x = screen_x - (dx / dist) * trail_length
                        trail_y = screen_y - (dy / dist) * trail_length
                        
                        gradient = QLinearGradient(screen_x, screen_y, trail_x, trail_y)
                        gradient.setColorAt(0, QColor(255, 255, 255, trail_alpha))
                        gradient.setColorAt(1, QColor(255, 255, 255, 0))
                        
                        pen = QPen(QBrush(gradient), size * 0.5)
                        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                        painter.setPen(pen)
                        painter.drawLine(
                            int(screen_x), int(screen_y),
                            int(trail_x), int(trail_y)
                        )
                        painter.setPen(Qt.PenStyle.NoPen)
    
    # ============ Icon Helper (Text-based icons) ============
    class Icons:
        """Text-based icons instead of emojis."""
        APP = "[App]"
        IPA = "[IPA]"
        FOLDER = "[Dir]"
        PACKAGE = "[Pkg]"
        BUILD = "[Build]"
        CONVERT = "[>>]"
        BROWSE = "[...]"
        CLEAR = "[x]"
        CONSOLE = "[>_]"
        SETTINGS = "[*]"
        SUCCESS = "[+]"
        ERROR = "[-]"
        WARNING = "[!]"
        INFO = "[i]"
        ARROW = "->"
    
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
    
    # ============ Main Window ============
    class IOSToolGUI(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("IOS TOOLS MAKER")
            self.setMinimumSize(900, 700)
            self.resize(1000, 750)
            
            self.core = IOSToolCore(log_callback=self._log_from_core)
            self.worker = None
            
            self._setup_ui()
            self._apply_styles()
        
        def _log_from_core(self, message: str, level: str = "info"):
            """Thread-safe logging from core."""
            self.log_text.append(self._format_log(message, level))
        
        def _format_log(self, message: str, level: str) -> str:
            colors = {
                "info": "#CCCCCC",
                "success": "#4ADE80",
                "warning": "#FBBF24",
                "error": "#F87171",
            }
            color = colors.get(level, "#CCCCCC")
            return f'<span style="color: {color}; font-family: Consolas, monospace;">{message}</span>'
        
        def _setup_ui(self):
            # Central widget
            central = QWidget()
            self.setCentralWidget(central)
            
            # Main layout
            main_layout = QVBoxLayout(central)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)
            
            # Space background
            self.space_bg = UniverseWidget(central)
            self.space_bg.setGeometry(central.rect())
            
            # Content overlay
            content = QWidget(central)
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(40, 30, 40, 30)
            content_layout.setSpacing(20)
            
            # Title section
            title_container = QWidget()
            title_layout = QVBoxLayout(title_container)
            title_layout.setSpacing(8)
            title_layout.setContentsMargins(0, 20, 0, 20)
            
            title = QLabel("IOS TOOLS")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setFont(QFont("SF Pro Display", 42, QFont.Weight.Light))
            title.setStyleSheet("color: white; background: transparent; letter-spacing: 2px;")
            title_layout.addWidget(title)
            
            # Animated subtitle
            self.subtitle = QLabel("Build from the Universe_")
            self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.subtitle.setFont(QFont("SF Mono", 14))
            self.subtitle.setStyleSheet("color: rgba(255,255,255,0.5); background: transparent; letter-spacing: 3px;")
            title_layout.addWidget(self.subtitle)
            
            # Cursor blink animation
            self.cursor_visible = True
            self.cursor_timer = QTimer()
            self.cursor_timer.timeout.connect(self._blink_cursor)
            self.cursor_timer.start(530)
            
            content_layout.addWidget(title_container)
            
            # Tab widget
            self.tabs = QTabWidget()
            self.tabs.setDocumentMode(True)
            content_layout.addWidget(self.tabs, stretch=2)
            
            # Create tabs
            self._create_app2ipa_tab()
            self._create_folder2deb_tab()
            self._create_build_dylib_tab()
            self._create_compile_tab()
            
            # Log area
            log_container = QWidget()
            log_layout = QVBoxLayout(log_container)
            log_layout.setContentsMargins(0, 10, 0, 0)
            
            log_header = QHBoxLayout()
            log_label = QLabel("Console")
            log_label.setFont(QFont("SF Pro Display", 12, QFont.Weight.Medium))
            log_label.setStyleSheet("color: rgba(255,255,255,0.6); background: transparent;")
            log_header.addWidget(log_label)
            
            log_header.addStretch()
            
            clear_btn = QPushButton("Clear")
            clear_btn.setFixedWidth(80)
            clear_btn.clicked.connect(lambda: self.log_text.clear())
            clear_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.1);
                    border: 1px solid rgba(255,255,255,0.2);
                    border-radius: 6px;
                    color: rgba(255,255,255,0.7);
                    padding: 5px 15px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.15);
                }
            """)
            log_header.addWidget(clear_btn)
            
            log_layout.addLayout(log_header)
            
            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)
            self.log_text.setFont(QFont("Consolas", 10))
            self.log_text.setMinimumHeight(100)
            self.log_text.setMaximumHeight(150)
            log_layout.addWidget(self.log_text)
            
            # Progress bar
            self.progress = QProgressBar()
            self.progress.setVisible(False)
            self.progress.setTextVisible(False)
            self.progress.setMaximum(0)
            self.progress.setFixedHeight(3)
            log_layout.addWidget(self.progress)
            
            content_layout.addWidget(log_container, stretch=1)
            
            main_layout.addWidget(content)
        
        def _blink_cursor(self):
            """Blink the cursor in subtitle."""
            self.cursor_visible = not self.cursor_visible
            base_text = "Build the Universe"
            if self.cursor_visible:
                self.subtitle.setText(base_text + "_")
            else:
                self.subtitle.setText(base_text + " ")
        
        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.space_bg.setGeometry(self.centralWidget().rect())
        
        def _create_grok_button(self, text: str, primary: bool = False, icon: str = "") -> QPushButton:
            """Create a premium Grok-style button with glow effects."""
            display_text = f"{icon}  {text}" if icon else text
            btn = QPushButton(display_text)
            btn.setMinimumHeight(52)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont("SF Pro Display", 13, QFont.Weight.DemiBold))
            
            if primary:
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                            stop:0 rgba(120, 120, 255, 0.25),
                            stop:0.5 rgba(180, 120, 255, 0.20),
                            stop:1 rgba(120, 180, 255, 0.25));
                        border: 1px solid rgba(255, 255, 255, 0.3);
                        border-radius: 14px;
                        color: white;
                        padding: 14px 35px;
                        font-weight: 600;
                        letter-spacing: 0.5px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                            stop:0 rgba(140, 140, 255, 0.35),
                            stop:0.5 rgba(200, 140, 255, 0.30),
                            stop:1 rgba(140, 200, 255, 0.35));
                        border: 1px solid rgba(255, 255, 255, 0.5);
                    }
                    QPushButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                            stop:0 rgba(100, 100, 200, 0.4),
                            stop:1 rgba(100, 150, 200, 0.4));
                        border: 1px solid rgba(255, 255, 255, 0.2);
                    }
                    QPushButton:disabled {
                        background: rgba(255, 255, 255, 0.05);
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        color: rgba(255, 255, 255, 0.25);
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(255, 255, 255, 0.1),
                            stop:1 rgba(255, 255, 255, 0.05));
                        border: 1px solid rgba(255, 255, 255, 0.18);
                        border-radius: 12px;
                        color: rgba(255, 255, 255, 0.9);
                        padding: 12px 24px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(255, 255, 255, 0.18),
                            stop:1 rgba(255, 255, 255, 0.10));
                        border: 1px solid rgba(255, 255, 255, 0.28);
                        color: white;
                    }
                    QPushButton:pressed {
                        background: rgba(255, 255, 255, 0.08);
                    }
                """)
            
            return btn
        
        def _create_grok_input(self, placeholder: str) -> QLineEdit:
            """Create a Grok-style input field."""
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            inp.setMinimumHeight(45)
            inp.setFont(QFont("SF Pro Display", 12))
            return inp
        
        def _create_section_label(self, text: str) -> QLabel:
            """Create a section label."""
            label = QLabel(text)
            label.setFont(QFont("SF Pro Display", 11, QFont.Weight.Medium))
            label.setStyleSheet("color: rgba(255,255,255,0.5); background: transparent; margin-top: 10px;")
            return label
        
        def _create_app2ipa_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(12)
            layout.setContentsMargins(20, 20, 20, 20)
            
            # Input section
            layout.addWidget(self._create_section_label("INPUT .APP DIRECTORY"))
            
            input_layout = QHBoxLayout()
            self.app2ipa_input = self._create_grok_input("Select .app folder...")
            input_layout.addWidget(self.app2ipa_input)
            
            browse_btn = self._create_grok_button("Browse")
            browse_btn.setFixedWidth(100)
            browse_btn.clicked.connect(lambda: self._browse_dir(self.app2ipa_input))
            input_layout.addWidget(browse_btn)
            layout.addLayout(input_layout)
            
            # Output section
            layout.addWidget(self._create_section_label("OUTPUT .IPA FILE (OPTIONAL)"))
            
            output_layout = QHBoxLayout()
            self.app2ipa_output = self._create_grok_input("Leave empty for default...")
            output_layout.addWidget(self.app2ipa_output)
            
            browse_btn2 = self._create_grok_button("Browse")
            browse_btn2.setFixedWidth(100)
            browse_btn2.clicked.connect(lambda: self._browse_save(self.app2ipa_output, "IPA Files (*.ipa)"))
            output_layout.addWidget(browse_btn2)
            layout.addLayout(output_layout)
            
            layout.addSpacing(20)
            
            # Convert button
            self.app2ipa_btn = self._create_grok_button("Convert to IPA", primary=True)
            self.app2ipa_btn.clicked.connect(self._run_app2ipa)
            layout.addWidget(self.app2ipa_btn)
            
            layout.addStretch()
            self.tabs.addTab(tab, "App to IPA")
        
        def _create_folder2deb_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(12)
            layout.setContentsMargins(20, 20, 20, 20)
            
            # Input section
            layout.addWidget(self._create_section_label("PACKAGE ROOT DIRECTORY"))
            
            input_layout = QHBoxLayout()
            self.folder2deb_input = self._create_grok_input("Must contain DEBIAN/control...")
            input_layout.addWidget(self.folder2deb_input)
            
            browse_btn = self._create_grok_button("Browse")
            browse_btn.setFixedWidth(100)
            browse_btn.clicked.connect(lambda: self._browse_dir(self.folder2deb_input))
            input_layout.addWidget(browse_btn)
            layout.addLayout(input_layout)
            
            # Output section
            layout.addWidget(self._create_section_label("OUTPUT .DEB FILE (OPTIONAL)"))
            
            output_layout = QHBoxLayout()
            self.folder2deb_output = self._create_grok_input("Leave empty for default...")
            output_layout.addWidget(self.folder2deb_output)
            
            browse_btn2 = self._create_grok_button("Browse")
            browse_btn2.setFixedWidth(100)
            browse_btn2.clicked.connect(lambda: self._browse_save(self.folder2deb_output, "DEB Files (*.deb)"))
            output_layout.addWidget(browse_btn2)
            layout.addLayout(output_layout)
            
            layout.addSpacing(20)
            
            # Build button
            self.folder2deb_btn = self._create_grok_button("Build DEB Package", primary=True)
            self.folder2deb_btn.clicked.connect(self._run_folder2deb)
            layout.addWidget(self.folder2deb_btn)
            
            layout.addStretch()
            self.tabs.addTab(tab, "Folder to DEB")
        
        def _create_build_dylib_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(12)
            layout.setContentsMargins(20, 20, 20, 20)
            
            # Input section
            layout.addWidget(self._create_section_label("PROJECT DIRECTORY"))
            
            input_layout = QHBoxLayout()
            self.dylib_input = self._create_grok_input("Select project folder...")
            input_layout.addWidget(self.dylib_input)
            
            browse_btn = self._create_grok_button("Browse")
            browse_btn.setFixedWidth(100)
            browse_btn.clicked.connect(lambda: self._browse_dir(self.dylib_input))
            input_layout.addWidget(browse_btn)
            layout.addLayout(input_layout)
            
            # Source file section
            layout.addWidget(self._create_section_label("SOURCE FILE (OPTIONAL)"))
            self.dylib_source = self._create_grok_input("e.g., tweak.m, dylib.c (auto-detect if empty)")
            layout.addWidget(self.dylib_source)
            
            # Output section
            layout.addWidget(self._create_section_label("OUTPUT NAME"))
            self.dylib_output = self._create_grok_input("tweak.dylib")
            self.dylib_output.setText("tweak.dylib")
            layout.addWidget(self.dylib_output)
            
            layout.addSpacing(20)
            
            # Build button
            self.dylib_btn = self._create_grok_button("Build Dylib", primary=True)
            self.dylib_btn.clicked.connect(self._run_build_dylib)
            layout.addWidget(self.dylib_btn)
            
            # Info
            info = QLabel("Requires Theos or clang with iOS SDK")
            info.setStyleSheet("color: rgba(255,255,255,0.4); background: transparent; font-size: 11px;")
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(info)
            
            layout.addStretch()
            self.tabs.addTab(tab, "Build Dylib")
        
        def _create_compile_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(12)
            layout.setContentsMargins(20, 20, 20, 20)
            
            # Header
            header = QLabel("[>] Compile Standalone Executable")
            header.setFont(QFont("SF Pro Display", 14, QFont.Weight.DemiBold))
            header.setStyleSheet("color: rgba(255,255,255,0.9); background: transparent;")
            layout.addWidget(header)
            
            desc = QLabel("Create standalone binaries for Windows (.exe), Linux, macOS, and BSD")
            desc.setStyleSheet("color: rgba(255,255,255,0.5); background: transparent; font-size: 12px;")
            layout.addWidget(desc)
            
            layout.addSpacing(15)
            
            # Output name section
            layout.addWidget(self._create_section_label("OUTPUT NAME (OPTIONAL)"))
            self.compile_output = self._create_grok_input("Auto: ios_tool-[os]-[arch] e.g. ios_tool-win-amd64.exe")
            layout.addWidget(self.compile_output)
            
            # Platform info
            import platform
            current_os = platform.system()
            current_arch = platform.machine()
            
            # Normalize arch display
            arch_display = current_arch
            if current_arch.lower() in ["x86_64", "amd64", "x64"]:
                arch_display = "AMD64 (x86_64)"
            elif current_arch.lower() in ["arm64", "aarch64"]:
                arch_display = "ARM64 (Apple Silicon / ARM)"
            elif current_arch.lower() in ["armv7l", "armv7"]:
                arch_display = "ARM (32-bit)"
            
            os_info = QLabel(f"[*] Current Platform: {current_os} / {arch_display}")
            os_info.setStyleSheet("color: rgba(120,180,255,0.8); background: transparent; font-size: 12px; margin-top: 10px;")
            layout.addWidget(os_info)
            
            layout.addSpacing(25)
            
            # Compile button
            self.compile_btn = self._create_grok_button("[>] Compile Binary", primary=True)
            self.compile_btn.clicked.connect(self._run_compile)
            layout.addWidget(self.compile_btn)
            
            # Platform notes with architecture info
            notes = QLabel(
                "Output Binaries:\n"
                "  Windows:  ios_tool-win-amd64.exe  |  ios_tool-win-arm64.exe\n"
                "  Linux:    ios_tool-linux-amd64   |  ios_tool-linux-arm64\n"
                "  macOS:    ios_tool-macos-amd64   |  ios_tool-macos-arm64\n"
                "  BSD:      ios_tool-bsd-amd64     |  ios_tool-bsd-arm64\n\n"
                "Requires: pip install pyinstaller"
            )
            notes.setStyleSheet("color: rgba(255,255,255,0.4); background: transparent; font-size: 11px; margin-top: 15px;")
            layout.addWidget(notes)
            
            layout.addStretch()
            self.tabs.addTab(tab, "Compile")
        
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
            
            self.worker = WorkerThread(self.core.compile_binary, None, output_name, None, True)
            self.worker.finished.connect(lambda s, r: self._on_finished(s, r, self.compile_btn))
            self.worker.start()
        
        def _apply_styles(self):
            self.setStyleSheet("""
                QMainWindow {
                    background: transparent;
                }
                QWidget {
                    background: transparent;
                    color: #FFFFFF;
                }
                QTabWidget::pane {
                    background: rgba(0, 0, 0, 0.4);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 15px;
                }
                QTabBar::tab {
                    background: transparent;
                    color: rgba(255, 255, 255, 0.5);
                    padding: 12px 30px;
                    margin-right: 5px;
                    border: none;
                    font-size: 13px;
                    font-weight: 500;
                }
                QTabBar::tab:selected {
                    color: white;
                    border-bottom: 2px solid white;
                }
                QTabBar::tab:hover:!selected {
                    color: rgba(255, 255, 255, 0.7);
                }
                QLineEdit {
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 10px;
                    padding: 12px 18px;
                    color: white;
                    font-size: 13px;
                    selection-background-color: rgba(255, 255, 255, 0.3);
                }
                QLineEdit:focus {
                    border: 1px solid rgba(255, 255, 255, 0.35);
                    background: rgba(255, 255, 255, 0.1);
                }
                QLineEdit::placeholder {
                    color: rgba(255, 255, 255, 0.35);
                }
                QTextEdit {
                    background: rgba(0, 0, 0, 0.5);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                    padding: 12px;
                    color: #CCC;
                    font-family: 'Consolas', 'Monaco', 'SF Mono', monospace;
                    font-size: 11px;
                }
                QScrollBar:vertical {
                    background: transparent;
                    width: 8px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical {
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 4px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background: rgba(255, 255, 255, 0.3);
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0;
                }
                QProgressBar {
                    background: rgba(255, 255, 255, 0.1);
                    border: none;
                    border-radius: 1px;
                }
                QProgressBar::chunk {
                    background: rgba(255, 255, 255, 0.6);
                    border-radius: 1px;
                }
                QMessageBox {
                    background: #1a1a1a;
                }
                QMessageBox QLabel {
                    color: white;
                }
                QMessageBox QPushButton {
                    background: rgba(255, 255, 255, 0.1);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 8px;
                    color: white;
                    padding: 8px 20px;
                    min-width: 80px;
                }
                QMessageBox QPushButton:hover {
                    background: rgba(255, 255, 255, 0.15);
                }
            """)
    
    # Run the application
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Base, QColor(10, 10, 10))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(20, 20, 20))
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Button, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(80, 80, 80))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
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
