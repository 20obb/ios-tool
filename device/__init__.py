"""
iOS Device Detection and IPA Installation Module.

This module provides:
- Device detection (iPhone/iPad via USB)
- Platform-specific dependency checking
- IPA installation to connected devices

Supported Platforms:
- Windows: Requires iTunes (desktop version) + Apple Mobile Device Support
- macOS: Native support via libimobiledevice or Xcode
- Linux/BSD: Requires libimobiledevice

Usage:
    from device import is_available, get_device_manager
    
    if is_available():
        manager = get_device_manager()
        devices = manager.detect_devices()
        if devices:
            manager.install_ipa(devices[0], "path/to/app.ipa")
"""

import sys
import os

# Module availability flag
_module_available = True
_availability_message = "Device module ready"

def is_available() -> tuple[bool, str]:
    """
    Check if device module is available.
    
    Returns:
        Tuple of (available: bool, message: str)
    """
    return _module_available, _availability_message


def get_platform_info() -> dict:
    """
    Get information about current platform and device support.
    
    Returns:
        Dictionary with platform info, requirements, and status
    """
    from .detection import DeviceDetector
    from .installer import IPAInstaller
    from .platform_deps import PlatformDependencies
    
    detector = DeviceDetector()
    installer = IPAInstaller()
    deps = PlatformDependencies()
    
    return {
        "platform": deps.get_platform_name(),
        "detection_supported": detector.is_supported(),
        "installation_supported": installer.is_supported(),
        "dependencies": deps.check_all(),
        "missing_dependencies": deps.get_missing(),
        "installation_instructions": deps.get_installation_instructions(),
    }


def get_device_manager():
    """
    Get the device manager instance for detecting and installing.
    
    Returns:
        DeviceManager instance
    """
    from .manager import DeviceManager
    return DeviceManager()


def detect_devices() -> list:
    """
    Quick function to detect connected iOS devices.
    
    Returns:
        List of detected Device objects
    """
    from .detection import DeviceDetector
    detector = DeviceDetector()
    return detector.detect()


def can_install() -> tuple[bool, str]:
    """
    Check if IPA installation is possible on current platform.
    
    Returns:
        Tuple of (can_install: bool, reason: str)
    """
    from .installer import IPAInstaller
    installer = IPAInstaller()
    return installer.is_supported(), installer.get_status_message()


__all__ = [
    'is_available',
    'get_platform_info',
    'get_device_manager',
    'detect_devices',
    'can_install',
]
