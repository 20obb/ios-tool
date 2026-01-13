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
    
    # Get logo path - support both development and PyInstaller bundled modes
    def get_resource_path(filename: str) -> Path:
        """Get path to resource file, works for dev and PyInstaller bundle."""
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            base_path = Path(sys._MEIPASS)
        else:
            # Running as script
            base_path = Path(__file__).parent
        return base_path / filename
    
    script_dir = Path(__file__).parent if not getattr(sys, 'frozen', False) else Path(sys._MEIPASS)
    logo_path = get_resource_path("logo.jpg")
    
    # ============ Grok-style Milky Way Background ============
    @dataclass
    class Star:
        x: float
        y: float
        size: float
        brightness: float
        twinkle_speed: float
        twinkle_phase: float
    
    @dataclass
    class CosmicDust:
        x: float
        y: float
        size: float
        alpha: float
        drift_x: float
        drift_y: float
    
    class GrokSpaceWidget(QWidget):
        """Grok AI style animated space background with milky way."""
        
        def __init__(self, parent=None):
            super().__init__(parent)
            self.stars: List[Star] = []
            self.cosmic_dust: List[CosmicDust] = []
            self.time = 0.0
            self.milky_way_phase = 0.0
            
            self._init_cosmos()
            
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._animate)
            self.timer.start(33)  # ~30 FPS
        
        def _init_cosmos(self):
            """Initialize stars and cosmic dust."""
            self.stars.clear()
            self.cosmic_dust.clear()
            
            w = max(1920, self.width() if self.width() > 0 else 1920)
            h = max(1080, self.height() if self.height() > 0 else 1080)
            
            # Create stars - more concentrated in center (milky way band)
            for _ in range(400):
                # Bias toward center vertically for milky way effect
                if random.random() < 0.6:
                    # Milky way band stars
                    y = h * 0.3 + random.gauss(0, h * 0.15)
                else:
                    # Background stars
                    y = random.uniform(0, h)
                
                self.stars.append(Star(
                    x=random.uniform(0, w),
                    y=y,
                    size=random.uniform(0.5, 2.5),
                    brightness=random.uniform(0.3, 1.0),
                    twinkle_speed=random.uniform(0.02, 0.08),
                    twinkle_phase=random.uniform(0, math.pi * 2)
                ))
            
            # Cosmic dust particles for the milky way glow
            for _ in range(150):
                self.cosmic_dust.append(CosmicDust(
                    x=random.uniform(0, w),
                    y=h * 0.25 + random.gauss(0, h * 0.12),
                    size=random.uniform(30, 120),
                    alpha=random.uniform(0.02, 0.08),
                    drift_x=random.uniform(-0.3, 0.3),
                    drift_y=random.uniform(-0.1, 0.1)
                ))
        
        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._init_cosmos()
        
        def _animate(self):
            """Update animation state."""
            self.time += 0.016
            self.milky_way_phase += 0.003
            
            # Update star twinkle
            for star in self.stars:
                star.twinkle_phase += star.twinkle_speed
            
            # Slowly drift cosmic dust
            w = self.width()
            for dust in self.cosmic_dust:
                dust.x += dust.drift_x
                dust.y += dust.drift_y
                
                # Wrap around
                if dust.x < -dust.size:
                    dust.x = w + dust.size
                elif dust.x > w + dust.size:
                    dust.x = -dust.size
            
            self.update()
        
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            w = self.width()
            h = self.height()
            
            # Pure black background
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            
            # Draw the milky way band
            self._draw_milky_way(painter, w, h)
            
            # Draw cosmic dust
            self._draw_cosmic_dust(painter)
            
            # Draw stars
            self._draw_stars(painter)
        
        def _draw_milky_way(self, painter: QPainter, w: int, h: int):
            """Draw the milky way band like in Grok app."""
            center_y = h * 0.35
            
            # Multiple layers for depth
            for layer in range(5):
                spread = 80 + layer * 40
                alpha_base = 25 - layer * 4
                
                # Wavy path across screen
                path = QPainterPath()
                
                points = []
                for i in range(20):
                    x = (i / 19) * w
                    wave = math.sin(x * 0.003 + self.milky_way_phase + layer * 0.5) * 30
                    wave += math.sin(x * 0.007 + self.milky_way_phase * 0.7) * 20
                    y = center_y + wave
                    points.append((x, y))
                
                if points:
                    path.moveTo(points[0][0], points[0][1] - spread)
                    
                    # Top edge
                    for x, y in points:
                        path.lineTo(x, y - spread + math.sin(x * 0.01 + self.time) * 10)
                    
                    # Bottom edge (reverse)
                    for x, y in reversed(points):
                        path.lineTo(x, y + spread + math.sin(x * 0.01 + self.time + 1) * 10)
                    
                    path.closeSubpath()
                
                # Gradient fill
                gradient = QLinearGradient(0, center_y - spread, 0, center_y + spread)
                gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
                gradient.setColorAt(0.3, QColor(200, 200, 220, alpha_base))
                gradient.setColorAt(0.5, QColor(220, 220, 235, alpha_base + 10))
                gradient.setColorAt(0.7, QColor(200, 200, 220, alpha_base))
                gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
                
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(gradient))
                painter.drawPath(path)
            
            # Central bright core
            core_gradient = QRadialGradient(w * 0.5, center_y, 200)
            core_gradient.setColorAt(0.0, QColor(255, 255, 255, 40))
            core_gradient.setColorAt(0.3, QColor(230, 230, 240, 25))
            core_gradient.setColorAt(0.6, QColor(200, 200, 220, 10))
            core_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(core_gradient))
            painter.drawEllipse(QRectF(w * 0.3, center_y - 150, w * 0.4, 300))
        
        def _draw_cosmic_dust(self, painter: QPainter):
            """Draw floating cosmic dust particles."""
            for dust in self.cosmic_dust:
                alpha = int(dust.alpha * 255 * (0.7 + 0.3 * math.sin(self.time + dust.x * 0.01)))
                
                gradient = QRadialGradient(dust.x, dust.y, dust.size)
                gradient.setColorAt(0.0, QColor(230, 230, 240, alpha))
                gradient.setColorAt(0.4, QColor(200, 200, 220, alpha // 2))
                gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
                
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(gradient))
                painter.drawEllipse(QRectF(
                    dust.x - dust.size,
                    dust.y - dust.size,
                    dust.size * 2,
                    dust.size * 2
                ))
        
        def _draw_stars(self, painter: QPainter):
            """Draw twinkling stars."""
            for star in self.stars:
                # Twinkle effect
                twinkle = 0.5 + 0.5 * math.sin(star.twinkle_phase)
                alpha = int(star.brightness * twinkle * 255)
                
                if alpha < 20:
                    continue
                
                color = QColor(255, 255, 255, alpha)
                
                # Glow for brighter stars
                if star.size > 1.5 and alpha > 100:
                    glow_size = star.size * 4
                    glow = QRadialGradient(star.x, star.y, glow_size)
                    glow.setColorAt(0.0, QColor(255, 255, 255, alpha // 3))
                    glow.setColorAt(0.5, QColor(200, 210, 255, alpha // 6))
                    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
                    
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(glow))
                    painter.drawEllipse(QRectF(
                        star.x - glow_size,
                        star.y - glow_size,
                        glow_size * 2,
                        glow_size * 2
                    ))
                
                # Star core
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QRectF(
                    star.x - star.size / 2,
                    star.y - star.size / 2,
                    star.size,
                    star.size
                ))
    
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
            
            # Set window icon from logo.jpg
            if logo_path.exists():
                self.setWindowIcon(QIcon(str(logo_path)))
            
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
            self.space_bg = GrokSpaceWidget(central)
            self.space_bg.setGeometry(central.rect())
            
            # Content overlay
            content = QWidget(central)
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(50, 25, 50, 35)
            content_layout.setSpacing(15)
            
            # Title section
            title_container = QWidget()
            title_layout = QVBoxLayout(title_container)
            title_layout.setSpacing(6)
            title_layout.setContentsMargins(0, 15, 0, 25)
            
            title = QLabel("IOS TOOLS")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setFont(QFont("Cairo", 42, QFont.Weight.ExtraLight))
            title.setStyleSheet("""
                color: white;
                background: transparent;
                letter-spacing: 12px;
            """)
            title_layout.addWidget(title)
            
            # Animated subtitle
            self.subtitle = QLabel("Build from the Universe_")
            self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.subtitle.setFont(QFont("Cairo", 12))
            self.subtitle.setStyleSheet("""
                color: rgba(160, 170, 200, 0.6);
                background: transparent;
                letter-spacing: 4px;
                margin-top: 5px;
            """)
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
            log_label = QLabel("   Console")
            log_label.setFont(QFont("Cairo", 10, QFont.Weight.Medium))
            log_label.setStyleSheet("""
                color: rgba(140, 150, 180, 0.7);
                background: transparent;
                letter-spacing: 1px;
            """)
            log_header.addWidget(log_label)
            
            log_header.addStretch()
            
            clear_btn = QPushButton("Clear")
            clear_btn.setFixedWidth(75)
            clear_btn.setFixedHeight(28)
            clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            clear_btn.clicked.connect(lambda: self.log_text.clear())
            clear_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.05);
                    border: 1px solid rgba(255,255,255,0.1);
                    border-radius: 8px;
                    color: rgba(255,255,255,0.5);
                    padding: 4px 12px;
                    font-size: 10px;
                    font-weight: 500;
                    letter-spacing: 0.5px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.1);
                    color: rgba(255,255,255,0.8);
                    border: 1px solid rgba(255,255,255,0.15);
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
            base_text = "Build from the Universe"
            if self.cursor_visible:
                self.subtitle.setText(base_text + "_")
            else:
                self.subtitle.setText(base_text + " ")
        
        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.space_bg.setGeometry(self.centralWidget().rect())
        
        def _create_grok_button(self, text: str, primary: bool = False, icon: str = "") -> QPushButton:
            """Create a glassy frosted button with Cairo font."""
            display_text = f"{icon}  {text}" if icon else text
            btn = QPushButton(display_text)
            btn.setMinimumHeight(54)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont("Cairo", 12, QFont.Weight.DemiBold))
            
            if primary:
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(255, 255, 255, 0.18),
                            stop:0.4 rgba(255, 255, 255, 0.08),
                            stop:0.6 rgba(200, 210, 255, 0.06),
                            stop:1 rgba(180, 190, 255, 0.12));
                        border: 1px solid rgba(255, 255, 255, 0.35);
                        border-top: 1px solid rgba(255, 255, 255, 0.5);
                        border-left: 1px solid rgba(255, 255, 255, 0.4);
                        border-radius: 16px;
                        color: white;
                        padding: 15px 40px;
                        font-weight: 600;
                        font-size: 14px;
                        letter-spacing: 0.5px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(255, 255, 255, 0.28),
                            stop:0.4 rgba(255, 255, 255, 0.15),
                            stop:0.6 rgba(220, 225, 255, 0.12),
                            stop:1 rgba(200, 210, 255, 0.18));
                        border: 1px solid rgba(255, 255, 255, 0.5);
                        border-top: 1px solid rgba(255, 255, 255, 0.65);
                        border-left: 1px solid rgba(255, 255, 255, 0.55);
                    }
                    QPushButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(255, 255, 255, 0.1),
                            stop:1 rgba(180, 190, 255, 0.15));
                        border: 1px solid rgba(255, 255, 255, 0.25);
                        padding-top: 16px;
                        padding-bottom: 14px;
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
                            stop:0 rgba(255, 255, 255, 0.12),
                            stop:0.5 rgba(255, 255, 255, 0.05),
                            stop:1 rgba(255, 255, 255, 0.08));
                        border: 1px solid rgba(255, 255, 255, 0.2);
                        border-top: 1px solid rgba(255, 255, 255, 0.3);
                        border-left: 1px solid rgba(255, 255, 255, 0.25);
                        border-radius: 14px;
                        color: rgba(255, 255, 255, 0.9);
                        padding: 12px 26px;
                        font-weight: 500;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(255, 255, 255, 0.2),
                            stop:0.5 rgba(255, 255, 255, 0.1),
                            stop:1 rgba(255, 255, 255, 0.14));
                        border: 1px solid rgba(255, 255, 255, 0.35);
                        border-top: 1px solid rgba(255, 255, 255, 0.45);
                        color: white;
                    }
                    QPushButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgba(255, 255, 255, 0.06),
                            stop:1 rgba(255, 255, 255, 0.1));
                        padding-top: 13px;
                        padding-bottom: 11px;
                    }
                """)
            
            return btn
        
        def _create_grok_input(self, placeholder: str) -> QLineEdit:
            """Create a glassy input field with Cairo font."""
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            inp.setMinimumHeight(48)
            inp.setFont(QFont("Cairo", 11))
            return inp
        
        def _create_section_label(self, text: str) -> QLabel:
            """Create a section label with subtle styling."""
            label = QLabel(text)
            label.setFont(QFont("Cairo", 9, QFont.Weight.Medium))
            label.setStyleSheet("""
                color: rgba(180, 190, 255, 0.6);
                background: transparent;
                margin-top: 12px;
                margin-bottom: 4px;
                padding-left: 4px;
                letter-spacing: 1.5px;
            """)
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
            info.setFont(QFont("Cairo", 9))
            info.setStyleSheet("color: rgba(255,255,255,0.4); background: transparent;")
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
            header = QLabel("Compile Standalone Executable")
            header.setFont(QFont("Cairo", 14, QFont.Weight.DemiBold))
            header.setStyleSheet("color: rgba(255,255,255,0.9); background: transparent;")
            layout.addWidget(header)
            
            desc = QLabel("Create standalone binaries for Windows (.exe), Linux, macOS, and BSD")
            desc.setFont(QFont("Cairo", 10))
            desc.setStyleSheet("color: rgba(255,255,255,0.5); background: transparent;")
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
            
            os_info = QLabel(f"Current Platform: {current_os} / {arch_display}")
            os_info.setFont(QFont("Cairo", 10))
            os_info.setStyleSheet("color: rgba(120,180,255,0.8); background: transparent; margin-top: 10px;")
            layout.addWidget(os_info)
            
            layout.addSpacing(25)
            
            # Compile button
            self.compile_btn = self._create_grok_button("Compile Binary", primary=True)
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
            notes.setFont(QFont("Cairo", 9))
            notes.setStyleSheet("color: rgba(255,255,255,0.4); background: transparent; margin-top: 15px;")
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
            
            self.worker = WorkerThread(self.core.compile_binary, None, output_name, None, None, True)
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
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(20, 20, 35, 0.85),
                        stop:1 rgba(10, 10, 20, 0.9));
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-top: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 20px;
                    padding: 5px;
                }
                QTabBar {
                    background: transparent;
                }
                QTabBar::tab {
                    background: rgba(255, 255, 255, 0.03);
                    color: rgba(255, 255, 255, 0.45);
                    padding: 10px 28px;
                    margin: 4px 3px 8px 3px;
                    border: 1px solid transparent;
                    border-radius: 12px;
                    font-size: 12px;
                    font-weight: 500;
                    letter-spacing: 0.3px;
                }
                QTabBar::tab:selected {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(100, 120, 255, 0.25),
                        stop:1 rgba(150, 100, 255, 0.2));
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                }
                QTabBar::tab:hover:!selected {
                    background: rgba(255, 255, 255, 0.08);
                    color: rgba(255, 255, 255, 0.75);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                }
                QLineEdit {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(30, 30, 45, 0.9),
                        stop:1 rgba(20, 20, 35, 0.95));
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-top: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 14px;
                    padding: 14px 20px;
                    color: rgba(255, 255, 255, 0.95);
                    font-size: 13px;
                    selection-background-color: rgba(100, 150, 255, 0.4);
                }
                QLineEdit:focus {
                    border: 1px solid rgba(130, 150, 255, 0.5);
                    border-top: 1px solid rgba(130, 150, 255, 0.6);
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(35, 35, 55, 0.95),
                        stop:1 rgba(25, 25, 40, 0.98));
                }
                QLineEdit::placeholder {
                    color: rgba(255, 255, 255, 0.3);
                }
                QTextEdit {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(10, 10, 18, 0.95),
                        stop:1 rgba(5, 5, 12, 0.98));
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-top: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 14px;
                    padding: 14px;
                    color: rgba(200, 200, 210, 0.9);
                    font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
                    font-size: 11px;
                    line-height: 1.4;
                }
                QScrollBar:vertical {
                    background: rgba(255, 255, 255, 0.02);
                    width: 6px;
                    border-radius: 3px;
                    margin: 4px 2px;
                }
                QScrollBar::handle:vertical {
                    background: rgba(255, 255, 255, 0.15);
                    border-radius: 3px;
                    min-height: 40px;
                }
                QScrollBar::handle:vertical:hover {
                    background: rgba(255, 255, 255, 0.25);
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: transparent;
                }
                QProgressBar {
                    background: rgba(255, 255, 255, 0.08);
                    border: none;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(100, 150, 255, 0.8),
                        stop:1 rgba(180, 100, 255, 0.8));
                    border-radius: 2px;
                }
                QMessageBox {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #1e1e2e, stop:1 #121218);
                }
                QMessageBox QLabel {
                    color: rgba(255, 255, 255, 0.9);
                }
                QMessageBox QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(60, 60, 80, 0.9),
                        stop:1 rgba(40, 40, 60, 0.95));
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 10px;
                    color: white;
                    padding: 10px 24px;
                    min-width: 90px;
                    font-weight: 500;
                }
                QMessageBox QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(80, 80, 100, 0.95),
                        stop:1 rgba(60, 60, 80, 0.98));
                    border: 1px solid rgba(255, 255, 255, 0.25);
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
