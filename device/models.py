"""
Data models for device detection and installation module.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class DeviceType(Enum):
    """Type of iOS device."""
    IPHONE = "iPhone"
    IPAD = "iPad"
    IPOD = "iPod"
    UNKNOWN = "Unknown"


class ConnectionType(Enum):
    """Type of device connection."""
    USB = "USB"
    WIFI = "WiFi"
    UNKNOWN = "Unknown"


class InstallationStatus(Enum):
    """Status of IPA installation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Device:
    """Represents a connected iOS device."""
    udid: str
    name: str
    device_type: DeviceType = DeviceType.UNKNOWN
    model: str = ""
    ios_version: str = ""
    connection_type: ConnectionType = ConnectionType.USB
    is_paired: bool = False
    is_trusted: bool = False
    
    @property
    def display_name(self) -> str:
        """Get a display-friendly name for the device."""
        if self.name:
            return f"{self.name} ({self.device_type.value})"
        return f"{self.device_type.value} - {self.udid[:8]}..."
    
    @property
    def short_udid(self) -> str:
        """Get shortened UDID for display."""
        if len(self.udid) > 16:
            return f"{self.udid[:8]}...{self.udid[-8:]}"
        return self.udid
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "udid": self.udid,
            "name": self.name,
            "device_type": self.device_type.value,
            "model": self.model,
            "ios_version": self.ios_version,
            "connection_type": self.connection_type.value,
            "is_paired": self.is_paired,
            "is_trusted": self.is_trusted,
        }


@dataclass
class Dependency:
    """Represents a platform dependency."""
    name: str
    description: str
    required: bool = True
    installed: bool = False
    version: Optional[str] = None
    install_url: Optional[str] = None
    install_command: Optional[str] = None
    notes: str = ""
    
    @property
    def status_icon(self) -> str:
        """Get status icon for display."""
        if self.installed:
            return "✓"
        elif self.required:
            return "✗"
        else:
            return "○"
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "installed": self.installed,
            "version": self.version,
            "install_url": self.install_url,
            "install_command": self.install_command,
            "notes": self.notes,
        }


@dataclass
class DependencyCheckResult:
    """Result of dependency check."""
    platform: str
    all_satisfied: bool
    dependencies: List[Dependency] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)
    
    @property
    def can_detect(self) -> bool:
        """Check if device detection is possible."""
        # Detection requires at least basic dependencies
        return self.all_satisfied or len(self.missing_required) == 0
    
    @property
    def can_install(self) -> bool:
        """Check if IPA installation is possible."""
        return self.all_satisfied
    
    def get_summary(self) -> str:
        """Get a summary message."""
        if self.all_satisfied:
            return f"All dependencies satisfied on {self.platform}"
        
        missing = ", ".join(self.missing_required)
        return f"Missing required dependencies: {missing}"


@dataclass
class InstallationResult:
    """Result of IPA installation."""
    success: bool
    device: Device
    ipa_path: str
    status: InstallationStatus = InstallationStatus.PENDING
    message: str = ""
    error_code: Optional[int] = None
    error_details: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: int = 0  # 0-100
    
    @property
    def duration(self) -> Optional[float]:
        """Get installation duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "device_udid": self.device.udid,
            "ipa_path": self.ipa_path,
            "status": self.status.value,
            "message": self.message,
            "error_code": self.error_code,
            "error_details": self.error_details,
            "progress": self.progress,
            "duration": self.duration,
        }


@dataclass
class InstallationOptions:
    """Options for IPA installation."""
    force_reinstall: bool = False
    skip_verification: bool = False
    timeout_seconds: int = 300  # 5 minutes default
    progress_callback: Optional[callable] = None
    
    # Platform-specific options
    use_wifi: bool = False  # Try WiFi installation if USB fails
    preserve_data: bool = True  # Preserve app data on reinstall
