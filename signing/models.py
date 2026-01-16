"""
Data models for iOS signing operations.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pathlib import Path


class SigningMethod(Enum):
    """Available signing methods."""
    ANNUAL = "annual"      # Developer certificate (1 year)
    WEEKLY = "weekly"      # Apple ID sideloading (7 days)


class CertificateType(Enum):
    """Certificate types for signing."""
    DEVELOPMENT = "development"
    DISTRIBUTION = "distribution"
    FREE = "free"  # Apple ID free signing


class ProvisioningType(Enum):
    """Provisioning profile types."""
    DEVELOPMENT = "Development"
    AD_HOC = "AdHoc"
    APP_STORE = "AppStore"
    ENTERPRISE = "Enterprise"


@dataclass
class Certificate:
    """Represents a signing certificate."""
    serial_number: str
    common_name: str
    organization: Optional[str]
    team_id: Optional[str]
    cert_type: CertificateType
    not_before: datetime
    not_after: datetime
    fingerprint_sha1: str
    fingerprint_sha256: str
    raw_data: bytes = field(repr=False)
    private_key: Optional[bytes] = field(default=None, repr=False)
    
    @property
    def is_valid(self) -> bool:
        """Check if certificate is currently valid."""
        now = datetime.utcnow()
        return self.not_before <= now <= self.not_after
    
    @property
    def days_remaining(self) -> int:
        """Days until certificate expires."""
        delta = self.not_after - datetime.utcnow()
        return max(0, delta.days)
    
    @property
    def is_development(self) -> bool:
        """Check if this is a development certificate."""
        return self.cert_type == CertificateType.DEVELOPMENT
    
    @property
    def display_name(self) -> str:
        """Human-readable certificate name."""
        return f"{self.common_name} ({self.days_remaining} days remaining)"


@dataclass
class ProvisioningProfile:
    """Represents a provisioning profile."""
    uuid: str
    name: str
    app_id: str
    team_id: str
    team_name: str
    profile_type: ProvisioningType
    creation_date: datetime
    expiration_date: datetime
    devices: List[str] = field(default_factory=list)
    entitlements: Dict[str, Any] = field(default_factory=dict)
    certificates: List[bytes] = field(default_factory=list, repr=False)
    raw_data: bytes = field(default=b"", repr=False)
    
    @property
    def is_valid(self) -> bool:
        """Check if profile is currently valid."""
        now = datetime.utcnow()
        return self.creation_date <= now <= self.expiration_date
    
    @property
    def days_remaining(self) -> int:
        """Days until profile expires."""
        delta = self.expiration_date - datetime.utcnow()
        return max(0, delta.days)
    
    @property
    def is_wildcard(self) -> bool:
        """Check if this is a wildcard app ID."""
        return self.app_id.endswith("*")
    
    @property
    def bundle_id_pattern(self) -> str:
        """Get the bundle ID pattern from app ID."""
        # App ID format: TEAM_ID.bundle.id or TEAM_ID.*
        parts = self.app_id.split(".", 1)
        return parts[1] if len(parts) > 1 else "*"
    
    def matches_bundle_id(self, bundle_id: str) -> bool:
        """Check if this profile matches a bundle ID."""
        pattern = self.bundle_id_pattern
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return bundle_id.startswith(prefix)
        return bundle_id == pattern


@dataclass
class AppInfo:
    """Information extracted from an iOS app."""
    bundle_id: str
    bundle_name: str
    version: str
    build_number: str
    min_ios_version: str
    executable_name: str
    icon_files: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    plugins: List[str] = field(default_factory=list)
    entitlements: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_info_plist(cls, plist_data: Dict[str, Any]) -> "AppInfo":
        """Create AppInfo from Info.plist data."""
        return cls(
            bundle_id=plist_data.get("CFBundleIdentifier", ""),
            bundle_name=plist_data.get("CFBundleName", ""),
            version=plist_data.get("CFBundleShortVersionString", "1.0"),
            build_number=plist_data.get("CFBundleVersion", "1"),
            min_ios_version=plist_data.get("MinimumOSVersion", "9.0"),
            executable_name=plist_data.get("CFBundleExecutable", ""),
            icon_files=plist_data.get("CFBundleIconFiles", []),
        )


@dataclass
class SigningIdentity:
    """Combined certificate and provisioning profile."""
    certificate: Certificate
    profile: ProvisioningProfile
    method: SigningMethod
    
    @property
    def is_valid(self) -> bool:
        """Check if both cert and profile are valid."""
        return self.certificate.is_valid and self.profile.is_valid
    
    @property
    def days_remaining(self) -> int:
        """Minimum days remaining between cert and profile."""
        return min(self.certificate.days_remaining, self.profile.days_remaining)
    
    @property
    def display_name(self) -> str:
        """Human-readable identity name."""
        return f"{self.certificate.common_name} / {self.profile.name}"


@dataclass
class SigningResult:
    """Result of a signing operation."""
    success: bool
    message: str
    input_path: Optional[Path] = None
    output_path: Optional[Path] = None
    signing_time: float = 0.0
    certificate_used: Optional[str] = None
    profile_used: Optional[str] = None
    bundle_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "message": self.message,
            "input_path": str(self.input_path) if self.input_path else None,
            "output_path": str(self.output_path) if self.output_path else None,
            "signing_time": self.signing_time,
            "certificate_used": self.certificate_used,
            "profile_used": self.profile_used,
            "bundle_id": self.bundle_id,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class AppleAccount:
    """Apple ID account information for weekly signing."""
    apple_id: str
    # Password is stored temporarily in memory only
    _password: str = field(repr=False)
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    session_token: Optional[str] = field(default=None, repr=False)
    session_expiry: Optional[datetime] = None
    is_authenticated: bool = False
    
    @property
    def is_session_valid(self) -> bool:
        """Check if session is still valid."""
        if not self.session_token or not self.session_expiry:
            return False
        return datetime.utcnow() < self.session_expiry


@dataclass 
class Device:
    """iOS device information."""
    udid: str
    name: str
    model: Optional[str] = None
    ios_version: Optional[str] = None
    is_registered: bool = False
    
    @property
    def display_name(self) -> str:
        """Human-readable device name."""
        if self.model:
            return f"{self.name} ({self.model})"
        return self.name
