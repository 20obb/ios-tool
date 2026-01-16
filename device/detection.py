"""
iOS Device Detection Module.

Provides cross-platform detection of connected iOS devices (iPhone, iPad, iPod).
Uses platform-specific methods:
- Windows: Apple Mobile Device Service / libimobiledevice
- macOS: libimobiledevice / Xcode tools
- Linux/BSD: libimobiledevice
"""

import os
import sys
import re
import shutil
import subprocess
from typing import List, Optional, Tuple
from pathlib import Path

from .models import Device, DeviceType, ConnectionType


class DeviceDetector:
    """Cross-platform iOS device detector."""
    
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
        """Check if device detection is supported on this platform."""
        if self._platform == "unknown":
            return False
        
        # Check for required tools
        if self._platform == "windows":
            return self._has_windows_support()
        else:
            return self._has_libimobiledevice()
    
    def _has_windows_support(self) -> bool:
        """Check for Windows iOS device support."""
        # Check for libimobiledevice first
        if self._has_libimobiledevice():
            return True
        
        # Check for Apple Mobile Device Support service
        try:
            result = subprocess.run(
                ["sc", "query", "Apple Mobile Device Service"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "RUNNING" in result.stdout:
                return True
        except Exception:
            pass
        
        # On Windows, we can always try PnP device detection as fallback
        # This works with just USB drivers installed (from iTunes or standalone)
        return True
    
    def _has_libimobiledevice(self) -> bool:
        """Check for libimobiledevice tools."""
        return shutil.which("idevice_id") is not None
    
    def get_status_message(self) -> str:
        """Get status message about detection capability."""
        if self.is_supported():
            return "Device detection available"
        
        if self._platform == "windows":
            return "Install iTunes (desktop version) or libimobiledevice for device detection"
        elif self._platform in ("macos", "linux", "bsd"):
            return "Install libimobiledevice for device detection"
        else:
            return "Platform not supported for device detection"
    
    def detect(self) -> List[Device]:
        """
        Detect all connected iOS devices.
        
        Returns:
            List of Device objects for connected devices
        """
        if not self.is_supported():
            return []
        
        devices = []
        
        # Try libimobiledevice first (works on all platforms)
        if self._has_libimobiledevice():
            devices = self._detect_with_libimobiledevice()
        
        # On Windows, also try Apple's method
        if not devices and self._platform == "windows":
            devices = self._detect_with_apple_service()
        
        return devices
    
    def _detect_with_libimobiledevice(self) -> List[Device]:
        """Detect devices using libimobiledevice tools."""
        devices = []
        
        try:
            # Get list of device UDIDs
            result = subprocess.run(
                ["idevice_id", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode != 0:
                return []
            
            udids = result.stdout.strip().split("\n")
            udids = [u.strip() for u in udids if u.strip()]
            
            # Get info for each device
            for udid in udids:
                device = self._get_device_info_libimobiledevice(udid)
                if device:
                    devices.append(device)
        
        except subprocess.TimeoutExpired:
            pass
        except FileNotFoundError:
            pass
        except Exception:
            pass
        
        return devices
    
    def _get_device_info_libimobiledevice(self, udid: str) -> Optional[Device]:
        """Get device info using ideviceinfo."""
        try:
            result = subprocess.run(
                ["ideviceinfo", "-u", udid],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode != 0:
                # Return basic device with just UDID
                return Device(
                    udid=udid,
                    name=f"iOS Device",
                    device_type=DeviceType.UNKNOWN,
                )
            
            # Parse device info
            info = self._parse_device_info(result.stdout)
            
            return Device(
                udid=udid,
                name=info.get("DeviceName", "iOS Device"),
                device_type=self._detect_device_type(info.get("ProductType", "")),
                model=info.get("ProductType", ""),
                ios_version=info.get("ProductVersion", ""),
                connection_type=ConnectionType.USB,
                is_paired=True,
                is_trusted=True,
            )
        
        except Exception:
            return Device(
                udid=udid,
                name="iOS Device",
                device_type=DeviceType.UNKNOWN,
            )
    
    def _parse_device_info(self, output: str) -> dict:
        """Parse ideviceinfo output."""
        info = {}
        for line in output.split("\n"):
            if ": " in line:
                key, value = line.split(": ", 1)
                info[key.strip()] = value.strip()
        return info
    
    def _detect_device_type(self, product_type: str) -> DeviceType:
        """Detect device type from product type string."""
        product_type = product_type.lower()
        
        if "iphone" in product_type:
            return DeviceType.IPHONE
        elif "ipad" in product_type:
            return DeviceType.IPAD
        elif "ipod" in product_type:
            return DeviceType.IPOD
        else:
            return DeviceType.UNKNOWN
    
    def _detect_with_apple_service(self) -> List[Device]:
        """
        Detect devices using Windows methods when libimobiledevice is not available.
        Uses PowerShell to query PnP devices for connected iOS devices.
        """
        devices = []
        
        try:
            # Get WPD (Windows Portable Device) entries for Apple devices
            # The UDID is in the parent USB device's instance ID
            ps_script = """
$devices = @()
Get-PnpDevice -Class WPD | Where-Object { 
    $_.Status -eq 'OK' -and ($_.FriendlyName -like '*iPhone*' -or $_.FriendlyName -like '*iPad*' -or $_.FriendlyName -like '*iPod*')
} | ForEach-Object {
    $name = $_.FriendlyName
    $parent = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue).Data
    if ($parent) {
        # UDID is the last part of parent instance ID: USB\\VID_05AC&PID_XXXX\\UDID
        $parts = $parent -split '\\\\'
        if ($parts.Count -ge 3) {
            $udid = $parts[-1]
            Write-Output "$name|$udid"
        }
    }
}
"""
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                
                for line in lines:
                    line = line.strip()
                    if not line or "|" not in line:
                        continue
                    
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        device_name, udid = parts
                        
                        # Determine device type from name
                        device_type = DeviceType.UNKNOWN
                        if "iPhone" in device_name:
                            device_type = DeviceType.IPHONE
                        elif "iPad" in device_name:
                            device_type = DeviceType.IPAD
                        elif "iPod" in device_name:
                            device_type = DeviceType.IPOD
                        
                        device = Device(
                            udid=udid,
                            name=device_name,
                            device_type=device_type,
                            connection_type=ConnectionType.USB,
                            is_paired=True,
                            is_trusted=True,
                        )
                        devices.append(device)
                
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            pass
        
        return devices
    
    def get_device_by_udid(self, udid: str) -> Optional[Device]:
        """
        Get a specific device by UDID.
        
        Args:
            udid: The device UDID to look for
            
        Returns:
            Device if found, None otherwise
        """
        devices = self.detect()
        for device in devices:
            if device.udid == udid:
                return device
        return None
    
    def wait_for_device(self, timeout_seconds: int = 30) -> Optional[Device]:
        """
        Wait for a device to be connected.
        
        Args:
            timeout_seconds: Maximum time to wait
            
        Returns:
            First detected Device or None if timeout
        """
        import time
        
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            devices = self.detect()
            if devices:
                return devices[0]
            time.sleep(1)
        
        return None
    
    def refresh(self) -> List[Device]:
        """Refresh device detection (alias for detect)."""
        return self.detect()
