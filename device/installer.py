"""
IPA Installation Module.

Provides cross-platform IPA installation to connected iOS devices.
Uses platform-specific methods:
- Windows: Apple Mobile Device Service / libimobiledevice
- macOS: libimobiledevice / ios-deploy / Xcode
- Linux/BSD: libimobiledevice
"""

import os
import sys
import shutil
import subprocess
import tempfile
from typing import Optional, Callable, Tuple
from pathlib import Path
from datetime import datetime

from .models import (
    Device, InstallationResult, InstallationStatus, InstallationOptions
)


class IPAInstaller:
    """Cross-platform IPA installer for iOS devices."""
    
    def __init__(self):
        self._platform = self._detect_platform()
    
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
    
    def is_supported(self) -> bool:
        """Check if IPA installation is supported on this platform."""
        if self._platform == "unknown":
            return False
        
        # Check for required tools
        if shutil.which("ideviceinstaller"):
            return True
        
        if self._platform == "macos" and shutil.which("ios-deploy"):
            return True
        
        if self._platform == "windows":
            return self._has_apple_installer_support()
        
        return False
    
    def _has_apple_installer_support(self) -> bool:
        """Check for Apple installer support on Windows."""
        # Check for Apple's DeviceSupport
        try:
            result = subprocess.run(
                ["sc", "query", "Apple Mobile Device Service"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "RUNNING" in result.stdout
        except Exception:
            return False
    
    def get_status_message(self) -> str:
        """Get status message about installation capability."""
        if self.is_supported():
            return "IPA installation available"
        
        if self._platform == "windows":
            return (
                "IPA installation requires:\n"
                "• iTunes (desktop version from apple.com, NOT Microsoft Store)\n"
                "• Apple Mobile Device Support\n"
                "Or install libimobiledevice (ideviceinstaller)"
            )
        elif self._platform == "macos":
            return (
                "Install one of the following for IPA installation:\n"
                "• brew install ideviceinstaller\n"
                "• brew install ios-deploy"
            )
        elif self._platform in ("linux", "bsd"):
            return "Install ideviceinstaller for IPA installation"
        else:
            return "Platform not supported for IPA installation"
    
    def validate_ipa(self, ipa_path: str) -> Tuple[bool, str]:
        """
        Validate an IPA file before installation.
        
        Args:
            ipa_path: Path to the IPA file
            
        Returns:
            Tuple of (valid: bool, message: str)
        """
        path = Path(ipa_path)
        
        if not path.exists():
            return False, f"IPA file not found: {ipa_path}"
        
        if not path.suffix.lower() == ".ipa":
            return False, f"File is not an IPA: {path.name}"
        
        # Check if it's a valid zip/IPA
        try:
            import zipfile
            with zipfile.ZipFile(path, 'r') as zf:
                # Check for Payload directory
                names = zf.namelist()
                has_payload = any(n.startswith("Payload/") for n in names)
                if not has_payload:
                    return False, "Invalid IPA: No Payload directory found"
                
                # Check for .app
                has_app = any(".app/" in n for n in names)
                if not has_app:
                    return False, "Invalid IPA: No .app bundle found"
        except zipfile.BadZipFile:
            return False, "Invalid IPA: Not a valid zip file"
        except Exception as e:
            return False, f"Error validating IPA: {e}"
        
        return True, "IPA is valid"
    
    def install(
        self,
        device: Device,
        ipa_path: str,
        options: Optional[InstallationOptions] = None,
    ) -> InstallationResult:
        """
        Install an IPA to a connected device.
        
        Args:
            device: Target device
            ipa_path: Path to the IPA file
            options: Installation options
            
        Returns:
            InstallationResult with status and details
        """
        if options is None:
            options = InstallationOptions()
        
        result = InstallationResult(
            success=False,
            device=device,
            ipa_path=ipa_path,
            status=InstallationStatus.IN_PROGRESS,
            started_at=datetime.now(),
        )
        
        # Validate IPA
        valid, msg = self.validate_ipa(ipa_path)
        if not valid:
            result.status = InstallationStatus.FAILED
            result.message = msg
            result.completed_at = datetime.now()
            return result
        
        # Check if installation is supported
        if not self.is_supported():
            result.status = InstallationStatus.FAILED
            result.message = self.get_status_message()
            result.completed_at = datetime.now()
            return result
        
        # Report progress
        if options.progress_callback:
            options.progress_callback(10, "Starting installation...")
        
        # Try different installation methods
        if shutil.which("ideviceinstaller"):
            result = self._install_with_ideviceinstaller(device, ipa_path, options, result)
        elif self._platform == "macos" and shutil.which("ios-deploy"):
            result = self._install_with_ios_deploy(device, ipa_path, options, result)
        else:
            result.status = InstallationStatus.FAILED
            result.message = "No installation tool available"
        
        result.completed_at = datetime.now()
        return result
    
    def _install_with_ideviceinstaller(
        self,
        device: Device,
        ipa_path: str,
        options: InstallationOptions,
        result: InstallationResult,
    ) -> InstallationResult:
        """Install using ideviceinstaller."""
        try:
            cmd = ["ideviceinstaller", "-u", device.udid, "-i", ipa_path]
            
            if options.progress_callback:
                options.progress_callback(20, "Installing with ideviceinstaller...")
            
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=options.timeout_seconds,
            )
            
            if process.returncode == 0:
                result.success = True
                result.status = InstallationStatus.SUCCESS
                result.message = "IPA installed successfully"
                result.progress = 100
            else:
                result.status = InstallationStatus.FAILED
                result.message = "Installation failed"
                result.error_details = process.stderr or process.stdout
                result.error_code = process.returncode
                
                # Parse common errors
                if "Could not connect" in (process.stderr or ""):
                    result.message = "Could not connect to device. Is it trusted?"
                elif "ApplicationVerificationFailed" in (process.stderr or ""):
                    result.message = "App verification failed. Check signing."
        
        except subprocess.TimeoutExpired:
            result.status = InstallationStatus.FAILED
            result.message = f"Installation timed out after {options.timeout_seconds}s"
        
        except FileNotFoundError:
            result.status = InstallationStatus.FAILED
            result.message = "ideviceinstaller not found"
        
        except Exception as e:
            result.status = InstallationStatus.FAILED
            result.message = f"Installation error: {e}"
        
        return result
    
    def _install_with_ios_deploy(
        self,
        device: Device,
        ipa_path: str,
        options: InstallationOptions,
        result: InstallationResult,
    ) -> InstallationResult:
        """Install using ios-deploy (macOS only)."""
        try:
            # ios-deploy requires extracting the .app from IPA
            import zipfile
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract IPA
                if options.progress_callback:
                    options.progress_callback(20, "Extracting IPA...")
                
                with zipfile.ZipFile(ipa_path, 'r') as zf:
                    zf.extractall(temp_dir)
                
                # Find .app directory
                payload_dir = Path(temp_dir) / "Payload"
                app_dirs = list(payload_dir.glob("*.app"))
                
                if not app_dirs:
                    result.status = InstallationStatus.FAILED
                    result.message = "No .app found in IPA"
                    return result
                
                app_path = app_dirs[0]
                
                if options.progress_callback:
                    options.progress_callback(40, "Installing with ios-deploy...")
                
                cmd = [
                    "ios-deploy",
                    "--id", device.udid,
                    "--bundle", str(app_path),
                ]
                
                if not options.skip_verification:
                    cmd.append("--no-wifi")
                
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=options.timeout_seconds,
                )
                
                if process.returncode == 0:
                    result.success = True
                    result.status = InstallationStatus.SUCCESS
                    result.message = "IPA installed successfully"
                    result.progress = 100
                else:
                    result.status = InstallationStatus.FAILED
                    result.message = "Installation failed"
                    result.error_details = process.stderr or process.stdout
                    result.error_code = process.returncode
        
        except subprocess.TimeoutExpired:
            result.status = InstallationStatus.FAILED
            result.message = f"Installation timed out after {options.timeout_seconds}s"
        
        except Exception as e:
            result.status = InstallationStatus.FAILED
            result.message = f"Installation error: {e}"
        
        return result
    
    def uninstall(
        self,
        device: Device,
        bundle_id: str,
        timeout_seconds: int = 60,
    ) -> Tuple[bool, str]:
        """
        Uninstall an app from a device.
        
        Args:
            device: Target device
            bundle_id: App bundle identifier
            timeout_seconds: Timeout for operation
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not shutil.which("ideviceinstaller"):
            return False, "ideviceinstaller not available"
        
        try:
            cmd = ["ideviceinstaller", "-u", device.udid, "-U", bundle_id]
            
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            
            if process.returncode == 0:
                return True, f"Uninstalled {bundle_id} successfully"
            else:
                return False, process.stderr or "Uninstall failed"
        
        except subprocess.TimeoutExpired:
            return False, "Uninstall timed out"
        except Exception as e:
            return False, f"Error: {e}"
    
    def list_installed_apps(
        self,
        device: Device,
        timeout_seconds: int = 30,
    ) -> Tuple[bool, list]:
        """
        List installed apps on a device.
        
        Args:
            device: Target device
            timeout_seconds: Timeout for operation
            
        Returns:
            Tuple of (success: bool, list of app bundle IDs or error message)
        """
        if not shutil.which("ideviceinstaller"):
            return False, ["ideviceinstaller not available"]
        
        try:
            cmd = ["ideviceinstaller", "-u", device.udid, "-l"]
            
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            
            if process.returncode == 0:
                apps = []
                for line in process.stdout.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("Total:"):
                        # Format: "bundle.id - App Name"
                        if " - " in line:
                            bundle_id = line.split(" - ")[0].strip()
                            apps.append(bundle_id)
                        else:
                            apps.append(line)
                return True, apps
            else:
                return False, [process.stderr or "Failed to list apps"]
        
        except subprocess.TimeoutExpired:
            return False, ["Operation timed out"]
        except Exception as e:
            return False, [f"Error: {e}"]
