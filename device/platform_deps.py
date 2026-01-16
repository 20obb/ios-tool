"""
Platform-specific dependency checker for iOS device operations.

Handles dependency detection and installation guidance for:
- Windows: iTunes (desktop), Apple Mobile Device Support
- macOS: libimobiledevice or Xcode
- Linux/BSD: libimobiledevice
"""

import os
import sys
import shutil
import subprocess
from typing import List, Optional, Tuple
from pathlib import Path

from .models import Dependency, DependencyCheckResult


class PlatformDependencies:
    """Check and manage platform-specific dependencies for device operations."""
    
    def __init__(self):
        self._platform = self._detect_platform()
        self._cached_result: Optional[DependencyCheckResult] = None
    
    def _detect_platform(self) -> str:
        """Detect the current platform."""
        if sys.platform == "win32":
            return "windows"
        elif sys.platform == "darwin":
            return "macos"
        elif sys.platform.startswith("linux"):
            return "linux"
        elif "bsd" in sys.platform.lower():
            return "bsd"
        else:
            return "unknown"
    
    def get_platform_name(self) -> str:
        """Get human-readable platform name."""
        names = {
            "windows": "Windows",
            "macos": "macOS",
            "linux": "Linux",
            "bsd": "BSD",
            "unknown": "Unknown Platform",
        }
        return names.get(self._platform, "Unknown")
    
    def check_all(self) -> DependencyCheckResult:
        """Check all dependencies for current platform."""
        if self._cached_result:
            return self._cached_result
        
        if self._platform == "windows":
            result = self._check_windows_deps()
        elif self._platform == "macos":
            result = self._check_macos_deps()
        elif self._platform == "linux":
            result = self._check_linux_deps()
        elif self._platform == "bsd":
            result = self._check_bsd_deps()
        else:
            result = self._check_unknown_deps()
        
        self._cached_result = result
        return result
    
    def get_missing(self) -> List[str]:
        """Get list of missing required dependencies."""
        result = self.check_all()
        return result.missing_required
    
    def get_installation_instructions(self) -> str:
        """Get installation instructions for missing dependencies."""
        result = self.check_all()
        
        if result.all_satisfied:
            return "All dependencies are installed."
        
        instructions = []
        instructions.append(f"Platform: {self.get_platform_name()}\n")
        instructions.append("Missing Dependencies:\n")
        
        for dep in result.dependencies:
            if not dep.installed and dep.required:
                instructions.append(f"\n{dep.name}:")
                instructions.append(f"  Description: {dep.description}")
                if dep.install_url:
                    instructions.append(f"  Download: {dep.install_url}")
                if dep.install_command:
                    instructions.append(f"  Install: {dep.install_command}")
                if dep.notes:
                    instructions.append(f"  Note: {dep.notes}")
        
        return "\n".join(instructions)
    
    # =========================================================================
    # Windows Dependencies
    # =========================================================================
    
    def _check_windows_deps(self) -> DependencyCheckResult:
        """Check Windows-specific dependencies."""
        dependencies = []
        missing_required = []
        missing_optional = []
        
        # Check for iTunes (Desktop version)
        itunes_dep = self._check_itunes_windows()
        dependencies.append(itunes_dep)
        if not itunes_dep.installed:
            missing_required.append(itunes_dep.name)
        
        # Check for Apple Mobile Device Support
        amds_dep = self._check_apple_mobile_device_support()
        dependencies.append(amds_dep)
        if not amds_dep.installed:
            missing_required.append(amds_dep.name)
        
        # Check for iCloud (optional but recommended)
        icloud_dep = self._check_icloud_windows()
        dependencies.append(icloud_dep)
        if not icloud_dep.installed:
            missing_optional.append(icloud_dep.name)
        
        # Check for libimobiledevice (optional alternative)
        libimobile_dep = self._check_libimobiledevice_windows()
        dependencies.append(libimobile_dep)
        
        return DependencyCheckResult(
            platform="Windows",
            all_satisfied=len(missing_required) == 0,
            dependencies=dependencies,
            missing_required=missing_required,
            missing_optional=missing_optional,
        )
    
    def _check_itunes_windows(self) -> Dependency:
        """Check for iTunes installation on Windows."""
        dep = Dependency(
            name="iTunes (Desktop)",
            description="Apple iTunes desktop application (NOT Microsoft Store version)",
            required=True,
            installed=False,
            install_url="https://www.apple.com/itunes/download/win64",
            notes="Download from Apple website, NOT from Microsoft Store",
        )
        
        # Check common installation paths
        itunes_paths = [
            Path(os.environ.get("PROGRAMFILES", "")) / "iTunes" / "iTunes.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "iTunes" / "iTunes.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "iTunes" / "iTunes.exe",
        ]
        
        for path in itunes_paths:
            if path.exists():
                dep.installed = True
                dep.version = self._get_file_version(path)
                break
        
        # Also check in PATH
        if not dep.installed and shutil.which("iTunes.exe"):
            dep.installed = True
        
        return dep
    
    def _check_apple_mobile_device_support(self) -> Dependency:
        """Check for Apple Mobile Device Support on Windows."""
        dep = Dependency(
            name="Apple Mobile Device Support",
            description="Driver for communicating with iOS devices",
            required=True,
            installed=False,
            notes="Installed automatically with iTunes (desktop version)",
        )
        
        # Check for the service
        try:
            result = subprocess.run(
                ["sc", "query", "Apple Mobile Device Service"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "RUNNING" in result.stdout or "STOPPED" in result.stdout:
                dep.installed = True
        except Exception:
            pass
        
        # Check for usbmuxd.exe or idevice tools
        amds_paths = [
            Path(os.environ.get("COMMONPROGRAMFILES", "")) / "Apple" / "Mobile Device Support",
            Path(os.environ.get("COMMONPROGRAMFILES(X86)", "")) / "Apple" / "Mobile Device Support",
        ]
        
        for path in amds_paths:
            if path.exists():
                dep.installed = True
                break
        
        return dep
    
    def _check_icloud_windows(self) -> Dependency:
        """Check for iCloud installation on Windows."""
        dep = Dependency(
            name="iCloud (Desktop)",
            description="Apple iCloud desktop application",
            required=False,  # Optional
            installed=False,
            install_url="https://support.apple.com/en-us/HT204283",
            notes="Recommended for better device pairing",
        )
        
        icloud_paths = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Common Files" / "Apple" / "Internet Services",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Common Files" / "Apple" / "Internet Services",
        ]
        
        for path in icloud_paths:
            if path.exists():
                dep.installed = True
                break
        
        return dep
    
    def _check_libimobiledevice_windows(self) -> Dependency:
        """Check for libimobiledevice on Windows."""
        dep = Dependency(
            name="libimobiledevice",
            description="Open-source library for iOS device communication",
            required=False,  # Optional alternative
            installed=False,
            install_url="https://github.com/libimobiledevice-win32/imobiledevice-net",
            install_command="choco install libimobiledevice",
            notes="Alternative to iTunes for device communication",
        )
        
        # Check for idevice tools in PATH
        tools = ["idevice_id", "ideviceinfo", "ideviceinstaller"]
        for tool in tools:
            if shutil.which(tool) or shutil.which(f"{tool}.exe"):
                dep.installed = True
                break
        
        return dep
    
    def _get_file_version(self, path: Path) -> Optional[str]:
        """Get file version on Windows."""
        try:
            import ctypes
            
            size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
            if size == 0:
                return None
            
            buffer = ctypes.create_string_buffer(size)
            ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer)
            
            # This is simplified - full implementation would parse the version info
            return "Installed"
        except Exception:
            return "Installed"
    
    # =========================================================================
    # macOS Dependencies
    # =========================================================================
    
    def _check_macos_deps(self) -> DependencyCheckResult:
        """Check macOS-specific dependencies."""
        dependencies = []
        missing_required = []
        missing_optional = []
        
        # Check for Xcode Command Line Tools
        xcode_dep = self._check_xcode_tools()
        dependencies.append(xcode_dep)
        
        # Check for libimobiledevice
        libimobile_dep = self._check_libimobiledevice_macos()
        dependencies.append(libimobile_dep)
        
        # At least one must be installed
        if not xcode_dep.installed and not libimobile_dep.installed:
            missing_required.append("libimobiledevice or Xcode tools")
        
        return DependencyCheckResult(
            platform="macOS",
            all_satisfied=len(missing_required) == 0,
            dependencies=dependencies,
            missing_required=missing_required,
            missing_optional=missing_optional,
        )
    
    def _check_xcode_tools(self) -> Dependency:
        """Check for Xcode Command Line Tools on macOS."""
        dep = Dependency(
            name="Xcode Command Line Tools",
            description="Apple development tools",
            required=False,  # libimobiledevice is alternative
            installed=False,
            install_command="xcode-select --install",
        )
        
        try:
            result = subprocess.run(
                ["xcode-select", "-p"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                dep.installed = True
        except Exception:
            pass
        
        return dep
    
    def _check_libimobiledevice_macos(self) -> Dependency:
        """Check for libimobiledevice on macOS."""
        dep = Dependency(
            name="libimobiledevice",
            description="Open-source library for iOS device communication",
            required=True,
            installed=False,
            install_command="brew install libimobiledevice ideviceinstaller",
            notes="Install via Homebrew",
        )
        
        tools = ["idevice_id", "ideviceinfo", "ideviceinstaller"]
        for tool in tools:
            if shutil.which(tool):
                dep.installed = True
                break
        
        return dep
    
    # =========================================================================
    # Linux Dependencies
    # =========================================================================
    
    def _check_linux_deps(self) -> DependencyCheckResult:
        """Check Linux-specific dependencies."""
        dependencies = []
        missing_required = []
        missing_optional = []
        
        # Check for libimobiledevice
        libimobile_dep = self._check_libimobiledevice_linux()
        dependencies.append(libimobile_dep)
        if not libimobile_dep.installed:
            missing_required.append(libimobile_dep.name)
        
        # Check for usbmuxd
        usbmuxd_dep = self._check_usbmuxd()
        dependencies.append(usbmuxd_dep)
        if not usbmuxd_dep.installed:
            missing_required.append(usbmuxd_dep.name)
        
        # Check for ideviceinstaller
        installer_dep = self._check_ideviceinstaller()
        dependencies.append(installer_dep)
        if not installer_dep.installed:
            missing_required.append(installer_dep.name)
        
        return DependencyCheckResult(
            platform="Linux",
            all_satisfied=len(missing_required) == 0,
            dependencies=dependencies,
            missing_required=missing_required,
            missing_optional=missing_optional,
        )
    
    def _check_libimobiledevice_linux(self) -> Dependency:
        """Check for libimobiledevice on Linux."""
        dep = Dependency(
            name="libimobiledevice",
            description="Library for iOS device communication",
            required=True,
            installed=False,
            notes="Required for device detection and installation",
        )
        
        # Detect package manager and set install command
        if shutil.which("apt"):
            dep.install_command = "sudo apt install libimobiledevice6 libimobiledevice-utils"
        elif shutil.which("dnf"):
            dep.install_command = "sudo dnf install libimobiledevice libimobiledevice-utils"
        elif shutil.which("pacman"):
            dep.install_command = "sudo pacman -S libimobiledevice"
        elif shutil.which("zypper"):
            dep.install_command = "sudo zypper install libimobiledevice-tools"
        else:
            dep.install_command = "Install libimobiledevice from your package manager"
        
        # Check for the tools
        if shutil.which("idevice_id") or shutil.which("ideviceinfo"):
            dep.installed = True
        
        return dep
    
    def _check_usbmuxd(self) -> Dependency:
        """Check for usbmuxd service."""
        dep = Dependency(
            name="usbmuxd",
            description="USB multiplexing daemon for iOS devices",
            required=True,
            installed=False,
        )
        
        if shutil.which("apt"):
            dep.install_command = "sudo apt install usbmuxd"
        elif shutil.which("dnf"):
            dep.install_command = "sudo dnf install usbmuxd"
        elif shutil.which("pacman"):
            dep.install_command = "sudo pacman -S usbmuxd"
        else:
            dep.install_command = "Install usbmuxd from your package manager"
        
        # Check if usbmuxd is available
        if shutil.which("usbmuxd"):
            dep.installed = True
        
        # Check if service is running
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "usbmuxd"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout.strip() == "active":
                dep.installed = True
        except Exception:
            pass
        
        return dep
    
    def _check_ideviceinstaller(self) -> Dependency:
        """Check for ideviceinstaller."""
        dep = Dependency(
            name="ideviceinstaller",
            description="Tool for installing apps on iOS devices",
            required=True,
            installed=False,
        )
        
        if shutil.which("apt"):
            dep.install_command = "sudo apt install ideviceinstaller"
        elif shutil.which("dnf"):
            dep.install_command = "sudo dnf install ideviceinstaller"
        elif shutil.which("pacman"):
            dep.install_command = "sudo pacman -S ideviceinstaller"
        else:
            dep.install_command = "Install ideviceinstaller from your package manager"
        
        if shutil.which("ideviceinstaller"):
            dep.installed = True
        
        return dep
    
    # =========================================================================
    # BSD Dependencies
    # =========================================================================
    
    def _check_bsd_deps(self) -> DependencyCheckResult:
        """Check BSD-specific dependencies."""
        dependencies = []
        missing_required = []
        missing_optional = []
        
        # Check for libimobiledevice
        libimobile_dep = Dependency(
            name="libimobiledevice",
            description="Library for iOS device communication",
            required=True,
            installed=False,
            install_command="pkg install libimobiledevice",
            notes="BSD support may be limited",
        )
        
        if shutil.which("idevice_id") or shutil.which("ideviceinfo"):
            libimobile_dep.installed = True
        else:
            missing_required.append(libimobile_dep.name)
        
        dependencies.append(libimobile_dep)
        
        return DependencyCheckResult(
            platform="BSD",
            all_satisfied=len(missing_required) == 0,
            dependencies=dependencies,
            missing_required=missing_required,
            missing_optional=missing_optional,
        )
    
    def _check_unknown_deps(self) -> DependencyCheckResult:
        """Handle unknown platform."""
        return DependencyCheckResult(
            platform="Unknown",
            all_satisfied=False,
            dependencies=[],
            missing_required=["Platform not supported"],
            missing_optional=[],
        )
    
    def refresh(self) -> DependencyCheckResult:
        """Refresh dependency check (clear cache)."""
        self._cached_result = None
        return self.check_all()
