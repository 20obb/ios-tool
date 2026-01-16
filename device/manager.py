"""
Device Manager - High-level API for device operations.

Provides a unified interface for:
- Device detection
- IPA installation
- Platform dependency checking
- Smart installation suggestions
"""

import os
import sys
from typing import List, Optional, Callable, Tuple
from pathlib import Path

from .models import (
    Device, DeviceType, InstallationResult, InstallationStatus,
    InstallationOptions, DependencyCheckResult
)
from .detection import DeviceDetector
from .installer import IPAInstaller
from .platform_deps import PlatformDependencies


class DeviceManager:
    """
    High-level manager for iOS device operations.
    
    Combines detection, installation, and dependency checking
    into a unified, easy-to-use interface.
    """
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self._detector = DeviceDetector()
        self._installer = IPAInstaller()
        self._deps = PlatformDependencies()
        self._log = log_callback or self._default_log
        self._cached_devices: List[Device] = []
        self._last_signed_ipa: Optional[str] = None
    
    def _default_log(self, message: str, level: str = "info") -> None:
        """Default logging function."""
        print(f"[{level.upper()}] {message}")
    
    # =========================================================================
    # Status and Capability Checks
    # =========================================================================
    
    def get_platform_status(self) -> dict:
        """
        Get comprehensive status of device support on current platform.
        
        Returns:
            Dictionary with platform info, capabilities, and requirements
        """
        deps = self._deps.check_all()
        
        return {
            "platform": self._deps.get_platform_name(),
            "can_detect": self._detector.is_supported(),
            "can_install": self._installer.is_supported(),
            "detection_message": self._detector.get_status_message(),
            "installation_message": self._installer.get_status_message(),
            "dependencies": deps,
            "all_dependencies_met": deps.all_satisfied,
            "missing_required": deps.missing_required,
            "installation_instructions": self._deps.get_installation_instructions(),
        }
    
    def is_ready(self) -> Tuple[bool, str]:
        """
        Check if device operations are ready.
        
        Returns:
            Tuple of (ready: bool, message: str)
        """
        if self._detector.is_supported() and self._installer.is_supported():
            return True, "Ready for device operations"
        
        if not self._detector.is_supported():
            return False, self._detector.get_status_message()
        
        if not self._installer.is_supported():
            return False, self._installer.get_status_message()
        
        return False, "Device operations not available"
    
    def get_requirements_message(self) -> str:
        """Get detailed message about requirements for current platform."""
        return self._deps.get_installation_instructions()
    
    # =========================================================================
    # Device Detection
    # =========================================================================
    
    def detect_devices(self, refresh: bool = True) -> List[Device]:
        """
        Detect connected iOS devices.
        
        Args:
            refresh: If True, force refresh detection. If False, may use cache.
            
        Returns:
            List of detected Device objects
        """
        if not self._detector.is_supported():
            self._log("Device detection not supported on this platform", "warning")
            return []
        
        self._log("Detecting iOS devices...", "info")
        devices = self._detector.detect()
        self._cached_devices = devices
        
        if devices:
            self._log(f"Found {len(devices)} device(s)", "success")
            for device in devices:
                self._log(f"  • {device.display_name}", "info")
        else:
            self._log("No devices detected", "info")
        
        return devices
    
    def get_cached_devices(self) -> List[Device]:
        """Get last detected devices without refreshing."""
        return self._cached_devices
    
    def get_device_by_udid(self, udid: str) -> Optional[Device]:
        """Get a specific device by UDID."""
        return self._detector.get_device_by_udid(udid)
    
    def wait_for_device(self, timeout_seconds: int = 30) -> Optional[Device]:
        """Wait for a device to be connected."""
        self._log(f"Waiting for device connection ({timeout_seconds}s timeout)...", "info")
        device = self._detector.wait_for_device(timeout_seconds)
        
        if device:
            self._log(f"Device connected: {device.display_name}", "success")
        else:
            self._log("No device connected within timeout", "warning")
        
        return device
    
    # =========================================================================
    # IPA Installation
    # =========================================================================
    
    def install_ipa(
        self,
        device: Device,
        ipa_path: str,
        options: Optional[InstallationOptions] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> InstallationResult:
        """
        Install an IPA to a connected device.
        
        Args:
            device: Target device
            ipa_path: Path to the IPA file
            options: Installation options
            progress_callback: Callback for progress updates (percent, message)
            
        Returns:
            InstallationResult with status and details
        """
        if not self._installer.is_supported():
            return InstallationResult(
                success=False,
                device=device,
                ipa_path=ipa_path,
                status=InstallationStatus.FAILED,
                message=self._installer.get_status_message(),
            )
        
        # Validate IPA first
        valid, msg = self._installer.validate_ipa(ipa_path)
        if not valid:
            self._log(f"IPA validation failed: {msg}", "error")
            return InstallationResult(
                success=False,
                device=device,
                ipa_path=ipa_path,
                status=InstallationStatus.FAILED,
                message=msg,
            )
        
        # Set up options with progress callback
        if options is None:
            options = InstallationOptions()
        
        if progress_callback:
            options.progress_callback = progress_callback
        
        self._log(f"Installing {Path(ipa_path).name} to {device.display_name}...", "info")
        
        result = self._installer.install(device, ipa_path, options)
        
        if result.success:
            self._log("Installation completed successfully!", "success")
        else:
            self._log(f"Installation failed: {result.message}", "error")
            if result.error_details:
                self._log(f"Details: {result.error_details}", "debug")
        
        return result
    
    def uninstall_app(
        self,
        device: Device,
        bundle_id: str,
    ) -> Tuple[bool, str]:
        """
        Uninstall an app from a device.
        
        Args:
            device: Target device
            bundle_id: App bundle identifier
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        self._log(f"Uninstalling {bundle_id}...", "info")
        success, msg = self._installer.uninstall(device, bundle_id)
        
        if success:
            self._log(msg, "success")
        else:
            self._log(msg, "error")
        
        return success, msg
    
    def list_installed_apps(self, device: Device) -> Tuple[bool, list]:
        """List installed apps on a device."""
        return self._installer.list_installed_apps(device)
    
    # =========================================================================
    # Smart Installation Suggestion
    # =========================================================================
    
    def set_last_signed_ipa(self, ipa_path: str) -> None:
        """
        Set the path to the last signed IPA.
        Used for smart installation suggestions.
        """
        if Path(ipa_path).exists():
            self._last_signed_ipa = ipa_path
    
    def get_last_signed_ipa(self) -> Optional[str]:
        """Get the path to the last signed IPA."""
        return self._last_signed_ipa
    
    def should_suggest_install(self) -> Tuple[bool, Optional[Device], Optional[str]]:
        """
        Check if we should suggest installing to a connected device.
        
        Returns:
            Tuple of (should_suggest: bool, device: Optional[Device], ipa_path: Optional[str])
        """
        # Need a signed IPA
        if not self._last_signed_ipa or not Path(self._last_signed_ipa).exists():
            return False, None, None
        
        # Need installation support
        if not self._installer.is_supported():
            return False, None, None
        
        # Need a connected device
        devices = self.detect_devices()
        if not devices:
            return False, None, None
        
        return True, devices[0], self._last_signed_ipa
    
    def get_install_suggestion(self) -> Optional[dict]:
        """
        Get installation suggestion if conditions are met.
        
        Returns:
            Dictionary with suggestion details, or None
        """
        should_suggest, device, ipa_path = self.should_suggest_install()
        
        if not should_suggest:
            return None
        
        return {
            "message": f"Device detected: {device.display_name}",
            "prompt": f"Would you like to install the signed IPA to this device?",
            "device": device,
            "ipa_path": ipa_path,
            "ipa_name": Path(ipa_path).name if ipa_path else None,
        }
    
    # =========================================================================
    # Convenience Methods
    # =========================================================================
    
    def quick_install(self, ipa_path: str) -> InstallationResult:
        """
        Quick install: detect first device and install IPA.
        
        Args:
            ipa_path: Path to the IPA file
            
        Returns:
            InstallationResult
        """
        devices = self.detect_devices()
        
        if not devices:
            return InstallationResult(
                success=False,
                device=Device(udid="", name="No Device"),
                ipa_path=ipa_path,
                status=InstallationStatus.FAILED,
                message="No devices detected",
            )
        
        return self.install_ipa(devices[0], ipa_path)
    
    def refresh_all(self) -> dict:
        """
        Refresh all information.
        
        Returns:
            Dictionary with updated platform status and devices
        """
        self._deps.refresh()
        devices = self.detect_devices()
        status = self.get_platform_status()
        
        return {
            "status": status,
            "devices": devices,
        }
