"""
Weekly Signing Module (Apple ID Sideloading)
=============================================

Signs IPA files using free Apple ID for 7-day sideloading.
Similar to AltStore/Sideloadly but cross-platform.

This module:
- Authenticates with Apple ID
- Generates temporary certificate
- Creates temporary provisioning profile
- Registers App ID
- Signs the IPA

Valid for 7 days, requires Apple server communication.

Usage:
    from signing.weekly import WeeklySigner
    
    signer = WeeklySigner()
    success = signer.authenticate("appleid@example.com", "password")
    
    if success:
        result = signer.sign_ipa("input.ipa", "output.ipa", device_udid="...")

IMPORTANT: Respects Apple's Terms of Service.
"""

import os
import time
import json
import tempfile
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from .models import (
    SigningResult, Certificate, ProvisioningProfile, Device,
    SigningIdentity, SigningMethod, CertificateType, ProvisioningType,
    AppleAccount
)
from .core import SigningCore, SigningError
from .apple_auth import (
    AppleAuthenticator, AppleSession, 
    AuthenticationError, TwoFactorRequired,
    is_requests_available
)
from .crypto_utils import is_crypto_available, CryptoError

# Check for requests
_requests_available = False
try:
    import requests
    _requests_available = True
except ImportError:
    pass


class WeeklySigningError(Exception):
    """Weekly signing specific error."""
    pass


@dataclass
class FreeSigningLimits:
    """Apple's free account limits."""
    max_app_ids_per_week: int = 10
    max_certificates_per_week: int = 3
    max_devices: int = 100
    signature_validity_days: int = 7


class WeeklySigner:
    """
    Signs IPA files using free Apple ID.
    
    This signer uses Apple's free provisioning to sign apps
    for 7 days. Similar to how AltStore and Sideloadly work.
    
    Features:
    - Uses free Apple ID (no paid developer account needed)
    - Automatic certificate generation
    - Automatic provisioning profile generation
    - Automatic App ID registration
    - Device UDID registration
    - Cross-platform (Windows, Linux, macOS, BSD)
    
    Limitations (Apple-imposed):
    - Signatures valid for 7 days only
    - Maximum 3 apps can be signed at once
    - Maximum 10 App IDs per week
    - Requires re-signing every 7 days
    
    Requirements:
    - Apple ID (free)
    - Device UDID
    - Internet connection
    """
    
    # Apple Developer Services endpoints
    DEV_SERVICES_URL = "https://developerservices2.apple.com/services/v1"
    QH65B2_URL = "https://developerservices2.apple.com/services/QH65B2"
    
    LIMITS = FreeSigningLimits()
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        """
        Initialize the weekly signer.
        
        Args:
            log_callback: Optional logging callback function
        """
        self.log_callback = log_callback or self._default_log
        self._auth = AppleAuthenticator(log_callback=self.log_callback)
        self._core = SigningCore(log_callback=self.log_callback)
        
        self._team_id: Optional[str] = None
        self._certificates: List[Certificate] = []
        self._app_ids: Dict[str, str] = {}  # bundle_id -> app_id
        self._devices: List[Device] = []
    
    def _default_log(self, message: str, level: str = "info") -> None:
        print(message)
    
    def log(self, message: str, level: str = "info") -> None:
        self.log_callback(message, level)
    
    # =========================================================================
    # Authentication
    # =========================================================================
    
    def authenticate(
        self,
        apple_id: str,
        password: str,
        two_factor_code: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Authenticate with Apple ID.
        
        Args:
            apple_id: Apple ID email
            password: Account password
            two_factor_code: 2FA code if required
        
        Returns:
            Tuple of (success, message)
        
        Raises:
            TwoFactorRequired: If 2FA needed
        """
        if not _requests_available:
            return False, "requests module not installed. Run: pip install requests"
        
        self.log("[*] Authenticating with Apple ID...")
        
        try:
            success, message = self._auth.authenticate(
                apple_id, 
                password,
                two_factor_code
            )
            
            if success:
                # Get team info
                teams = self._auth.get_teams()
                if teams:
                    self._team_id = teams[0].get("teamId")
                    team_name = teams[0].get("name", "Unknown")
                    self.log(f"[+] Team: {team_name} ({self._team_id})", "success")
            
            return success, message
            
        except TwoFactorRequired:
            raise
        except Exception as e:
            return False, str(e)
    
    @property
    def is_authenticated(self) -> bool:
        """Check if authenticated."""
        return self._auth.is_authenticated
    
    @property
    def session(self) -> Optional[AppleSession]:
        """Get current session."""
        return self._auth.session
    
    # =========================================================================
    # Certificate Management
    # =========================================================================
    
    def get_certificates(self) -> List[Dict[str, Any]]:
        """Get existing development certificates."""
        if not self.is_authenticated:
            raise WeeklySigningError("Not authenticated")
        
        self.log("[*] Fetching certificates...")
        
        try:
            response = self._dev_request(
                "POST",
                f"{self.QH65B2_URL}/listAllDevelopmentCerts",
                json={"teamId": self._team_id}
            )
            
            certs = response.get("certRequests", [])
            self.log(f"[*] Found {len(certs)} certificate(s)")
            
            return certs
            
        except Exception as e:
            self.log(f"[-] Failed to get certificates: {e}", "error")
            return []
    
    def create_certificate(self) -> Optional[Certificate]:
        """
        Create a new development certificate.
        
        Generates a CSR, submits to Apple, and returns
        the signed certificate.
        """
        if not self.is_authenticated:
            raise WeeklySigningError("Not authenticated")
        
        if not is_crypto_available():
            raise WeeklySigningError(
                "cryptography module required. Run: pip install cryptography"
            )
        
        self.log("[*] Creating development certificate...")
        
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.backends import default_backend
            from cryptography.x509.oid import NameOID
            
            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            # Create CSR
            csr = x509.CertificateSigningRequestBuilder().subject_name(
                x509.Name([
                    x509.NameAttribute(NameOID.COMMON_NAME, "iOS Development"),
                    x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                ])
            ).sign(private_key, hashes.SHA256(), default_backend())
            
            csr_pem = csr.public_bytes(serialization.Encoding.PEM)
            
            # Submit CSR to Apple
            response = self._dev_request(
                "POST",
                f"{self.QH65B2_URL}/submitDevelopmentCSR",
                json={
                    "teamId": self._team_id,
                    "csrContent": csr_pem.decode(),
                    "machineId": self._auth._device_id,
                    "machineName": "ios-tool",
                }
            )
            
            cert_data = response.get("certRequest", {})
            cert_content = cert_data.get("certContent")
            
            if not cert_content:
                raise WeeklySigningError("No certificate returned from Apple")
            
            # Parse certificate
            import base64
            cert_der = base64.b64decode(cert_content)
            cert = x509.load_der_x509_certificate(cert_der, default_backend())
            
            # Create Certificate object
            import hashlib
            
            certificate = Certificate(
                serial_number=format(cert.serial_number, 'x').upper(),
                common_name="iOS Development",
                organization=None,
                team_id=self._team_id,
                cert_type=CertificateType.FREE,
                not_before=cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before,
                not_after=cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after,
                fingerprint_sha1=hashlib.sha1(cert_der).hexdigest().upper(),
                fingerprint_sha256=hashlib.sha256(cert_der).hexdigest().upper(),
                raw_data=cert_der,
                private_key=private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                )
            )
            
            self._certificates.append(certificate)
            self.log(f"[+] Certificate created successfully", "success")
            self.log(f"[*] Valid until: {certificate.not_after}")
            
            return certificate
            
        except WeeklySigningError:
            raise
        except Exception as e:
            raise WeeklySigningError(f"Failed to create certificate: {e}")
    
    def revoke_certificate(self, serial_number: str) -> bool:
        """Revoke an existing certificate."""
        if not self.is_authenticated:
            raise WeeklySigningError("Not authenticated")
        
        self.log(f"[*] Revoking certificate: {serial_number}")
        
        try:
            self._dev_request(
                "POST",
                f"{self.QH65B2_URL}/revokeDevelopmentCert",
                json={
                    "teamId": self._team_id,
                    "serialNumber": serial_number,
                }
            )
            
            self.log("[+] Certificate revoked", "success")
            return True
            
        except Exception as e:
            self.log(f"[-] Failed to revoke: {e}", "error")
            return False
    
    # =========================================================================
    # App ID Management
    # =========================================================================
    
    def register_app_id(self, bundle_id: str, name: str = None) -> str:
        """
        Register an App ID for the bundle identifier.
        
        Args:
            bundle_id: Bundle identifier (e.g., com.example.app)
            name: Optional app name
        
        Returns:
            App ID identifier from Apple
        """
        if not self.is_authenticated:
            raise WeeklySigningError("Not authenticated")
        
        # Check cache
        if bundle_id in self._app_ids:
            return self._app_ids[bundle_id]
        
        name = name or bundle_id.split(".")[-1]
        
        self.log(f"[*] Registering App ID: {bundle_id}")
        
        try:
            # First check if it exists
            existing = self._get_app_id(bundle_id)
            if existing:
                self._app_ids[bundle_id] = existing
                return existing
            
            # Create new App ID
            response = self._dev_request(
                "POST",
                f"{self.QH65B2_URL}/addAppId",
                json={
                    "teamId": self._team_id,
                    "identifier": bundle_id,
                    "name": name,
                    "enabledFeatures": {},
                }
            )
            
            app_id = response.get("appId", {}).get("appIdId", "")
            self._app_ids[bundle_id] = app_id
            
            self.log(f"[+] App ID registered: {app_id}", "success")
            return app_id
            
        except Exception as e:
            raise WeeklySigningError(f"Failed to register App ID: {e}")
    
    def _get_app_id(self, bundle_id: str) -> Optional[str]:
        """Check if App ID already exists."""
        try:
            response = self._dev_request(
                "POST",
                f"{self.QH65B2_URL}/listAppIds",
                json={"teamId": self._team_id}
            )
            
            for app_id in response.get("appIds", []):
                if app_id.get("identifier") == bundle_id:
                    return app_id.get("appIdId")
            
            return None
            
        except Exception:
            return None
    
    # =========================================================================
    # Device Registration
    # =========================================================================
    
    def register_device(self, udid: str, name: str = "iOS Device") -> bool:
        """
        Register a device UDID.
        
        Args:
            udid: Device UDID (40 character hex string)
            name: Device name
        
        Returns:
            True if successful
        """
        if not self.is_authenticated:
            raise WeeklySigningError("Not authenticated")
        
        # Validate UDID format
        udid = udid.strip().upper()
        if len(udid) != 40 or not all(c in '0123456789ABCDEF-' for c in udid):
            raise WeeklySigningError(f"Invalid UDID format: {udid}")
        
        self.log(f"[*] Registering device: {udid[:8]}...{udid[-4:]}")
        
        try:
            # Check if already registered
            if self._is_device_registered(udid):
                self.log("[*] Device already registered")
                return True
            
            response = self._dev_request(
                "POST",
                f"{self.QH65B2_URL}/addDevice",
                json={
                    "teamId": self._team_id,
                    "deviceNumber": udid,
                    "name": name,
                }
            )
            
            device_id = response.get("device", {}).get("deviceId", "")
            self.log(f"[+] Device registered: {device_id}", "success")
            
            return True
            
        except Exception as e:
            raise WeeklySigningError(f"Failed to register device: {e}")
    
    def _is_device_registered(self, udid: str) -> bool:
        """Check if device is already registered."""
        try:
            response = self._dev_request(
                "POST",
                f"{self.QH65B2_URL}/listDevices",
                json={"teamId": self._team_id}
            )
            
            for device in response.get("devices", []):
                if device.get("deviceNumber", "").upper() == udid.upper():
                    return True
            
            return False
            
        except Exception:
            return False
    
    # =========================================================================
    # Provisioning Profile
    # =========================================================================
    
    def create_provisioning_profile(
        self,
        bundle_id: str,
        device_udid: str,
        certificate: Certificate
    ) -> ProvisioningProfile:
        """
        Create a provisioning profile.
        
        Args:
            bundle_id: Bundle identifier
            device_udid: Device UDID
            certificate: Certificate to include
        
        Returns:
            ProvisioningProfile object
        """
        if not self.is_authenticated:
            raise WeeklySigningError("Not authenticated")
        
        self.log(f"[*] Creating provisioning profile for: {bundle_id}")
        
        try:
            # Ensure device is registered
            self.register_device(device_udid)
            
            # Ensure App ID exists
            app_id = self.register_app_id(bundle_id)
            
            # Create profile
            profile_name = f"iOS Team Provisioning Profile: {bundle_id}"
            
            response = self._dev_request(
                "POST",
                f"{self.QH65B2_URL}/downloadTeamProvisioningProfile",
                json={
                    "teamId": self._team_id,
                    "appIdId": app_id,
                }
            )
            
            profile_data = response.get("provisioningProfile", {})
            profile_content = profile_data.get("encodedProfile")
            
            if not profile_content:
                raise WeeklySigningError("No profile returned from Apple")
            
            import base64
            profile_bytes = base64.b64decode(profile_content)
            
            # Parse profile
            from .crypto_utils import ProvisioningProfileParser
            
            # Write to temp file for parsing
            temp_path = Path(tempfile.gettempdir()) / "temp.mobileprovision"
            temp_path.write_bytes(profile_bytes)
            
            parser = ProvisioningProfileParser(str(temp_path))
            info = parser.get_profile_info()
            
            profile = ProvisioningProfile(
                uuid=info.get("uuid", ""),
                name=info.get("name", profile_name),
                app_id=f"{self._team_id}.{bundle_id}",
                team_id=self._team_id,
                team_name=info.get("team_name", ""),
                profile_type=ProvisioningType.DEVELOPMENT,
                creation_date=info.get("creation_date", datetime.utcnow()),
                expiration_date=info.get("expiration_date", datetime.utcnow() + timedelta(days=7)),
                devices=[device_udid],
                entitlements=info.get("entitlements", {}),
                raw_data=profile_bytes
            )
            
            # Cleanup
            temp_path.unlink(missing_ok=True)
            
            self.log(f"[+] Provisioning profile created", "success")
            self.log(f"[*] Valid until: {profile.expiration_date}")
            
            return profile
            
        except WeeklySigningError:
            raise
        except Exception as e:
            raise WeeklySigningError(f"Failed to create profile: {e}")
    
    # =========================================================================
    # Signing
    # =========================================================================
    
    def sign_ipa(
        self,
        input_ipa: str,
        output_ipa: Optional[str] = None,
        device_udid: str = None,
        new_bundle_id: Optional[str] = None
    ) -> SigningResult:
        """
        Sign an IPA file with free Apple ID signing.
        
        Args:
            input_ipa: Path to input IPA
            output_ipa: Path for signed output
            device_udid: Target device UDID (required)
            new_bundle_id: Optional new bundle ID
        
        Returns:
            SigningResult with operation details
        """
        input_path = Path(input_ipa)
        
        if not self.is_authenticated:
            return SigningResult(
                success=False,
                message="Not authenticated. Call authenticate() first.",
                input_path=input_path,
                errors=["Not authenticated"]
            )
        
        if not device_udid:
            return SigningResult(
                success=False,
                message="Device UDID is required for weekly signing",
                input_path=input_path,
                errors=["No device UDID provided"]
            )
        
        if not input_path.exists():
            return SigningResult(
                success=False,
                message=f"Input IPA not found: {input_path}",
                input_path=input_path,
                errors=["Input file does not exist"]
            )
        
        # Determine output path
        if output_ipa:
            output_path = Path(output_ipa)
        else:
            output_path = input_path.parent / f"{input_path.stem}-signed.ipa"
        
        self.log("=" * 50)
        self.log(f"[>] Weekly Signing (Apple ID - 7 Days)")
        self.log(f"[>] Input: {input_path}")
        self.log(f"[>] Output: {output_path}")
        self.log(f"[>] Device: {device_udid[:8]}...{device_udid[-4:]}")
        
        try:
            # Extract IPA to get bundle ID
            success, extract_dir = self._core.extract_ipa(str(input_path))
            app_path = self._core.find_app_in_payload(extract_dir)
            app_info = self._core.get_app_info(str(app_path))
            
            bundle_id = new_bundle_id or app_info.bundle_id
            self.log(f"[*] Bundle ID: {bundle_id}")
            
            # Get or create certificate
            certificate = None
            if self._certificates:
                certificate = self._certificates[0]
            else:
                certificate = self.create_certificate()
            
            if not certificate:
                raise WeeklySigningError("Failed to get certificate")
            
            # Create provisioning profile
            profile = self.create_provisioning_profile(
                bundle_id,
                device_udid,
                certificate
            )
            
            # Sign the IPA
            result = self._core.sign_ipa(
                str(input_path),
                str(output_path),
                certificate,
                profile,
                new_bundle_id
            )
            
            if result.success:
                self.log(f"[+] IPA signed successfully!", "success")
                self.log(f"[+] Output: {result.output_path}", "success")
                self.log(f"[+] Valid for: 7 days", "success")
            else:
                self.log(f"[-] Signing failed: {result.message}", "error")
            
            return result
            
        except Exception as e:
            return SigningResult(
                success=False,
                message=str(e),
                input_path=input_path,
                errors=[str(e)]
            )
    
    # =========================================================================
    # API Helper
    # =========================================================================
    
    def _dev_request(
        self,
        method: str,
        url: str,
        json: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Make a request to Apple Developer Services."""
        if not self._auth.session:
            raise WeeklySigningError("No active session")
        
        headers = {
            "Content-Type": "application/vnd.api+json",
            "User-Agent": "Xcode",
            "X-Xcode-Version": "15.0 (15A240d)",
            "X-Apple-I-Identity-Id": self._auth.session.dsid,
            "X-Apple-GS-Token": self._auth.session.session_token,
        }
        
        import requests as req
        
        response = req.request(
            method,
            url,
            json=json,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            try:
                return response.json() if response.text and response.text.strip() else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        
        # Handle errors
        try:
            error_data = response.json()
            error_msg = error_data.get("userString", error_data.get("resultString", "Unknown error"))
        except Exception:
            error_msg = f"HTTP {response.status_code}"
        
        raise WeeklySigningError(f"API error: {error_msg}")
    
    # =========================================================================
    # Info
    # =========================================================================
    
    def get_info(self) -> Dict[str, Any]:
        """Get signer configuration info."""
        return {
            "method": "weekly",
            "authenticated": self.is_authenticated,
            "team_id": self._team_id,
            "certificates_count": len(self._certificates),
            "app_ids_count": len(self._app_ids),
            "limits": {
                "signature_validity_days": self.LIMITS.signature_validity_days,
                "max_app_ids_per_week": self.LIMITS.max_app_ids_per_week,
                "max_certificates_per_week": self.LIMITS.max_certificates_per_week,
            }
        }


def get_weekly_signing_info() -> str:
    """Get information about weekly signing."""
    return """
Weekly Signing (Apple ID Sideloading)
======================================

This signing method uses a free Apple ID to sign apps
for 7 days, similar to AltStore and Sideloadly.

Requirements:
- Apple ID (free account works)
- Device UDID
- Internet connection

Limitations (Apple-imposed):
- Signatures valid for 7 days only
- Maximum 3 apps signed simultaneously
- Maximum 10 App IDs per week
- Must re-sign every 7 days

How to get Device UDID:
1. Connect device to computer
2. Open iTunes/Finder
3. Click on device info until UDID appears
4. Copy the 40-character string

Or use: ios-tool device-info (if device connected)

Python dependencies:
    pip install cryptography requests

Usage example:
    from signing.weekly import WeeklySigner
    
    signer = WeeklySigner()
    
    # Authenticate
    success, msg = signer.authenticate(
        "appleid@example.com",
        "password"
    )
    
    if success:
        result = signer.sign_ipa(
            "app.ipa",
            device_udid="00008101-..."
        )
        
        if result.success:
            print(f"Signed: {result.output_path}")
            print(f"Install within 7 days!")
"""
