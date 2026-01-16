"""
Annual Signing Module (Apple Developer Certificate)
====================================================

Signs IPA files using .p12 certificate and mobileprovision files.
Valid for 1 year, works completely offline.

Supports:
- Development certificates
- Distribution certificates
- Enterprise distribution

Usage:
    from signing.annual import AnnualSigner
    
    signer = AnnualSigner(
        p12_path="certificate.p12",
        provision_path="app.mobileprovision",
        p12_password="password"
    )
    
    result = signer.sign_ipa("input.ipa", "output-signed.ipa")
"""

from pathlib import Path
from typing import Optional, Callable, Dict, Any
from datetime import datetime

from .models import (
    SigningResult, Certificate, ProvisioningProfile,
    SigningIdentity, SigningMethod, CertificateType, ProvisioningType
)
from .crypto_utils import (
    P12Handler, ProvisioningProfileParser, CryptoError
)
from .core import SigningCore, SigningError


class AnnualSigner:
    """
    Signs IPA files using Apple Developer Certificate.
    
    This signer uses a .p12 certificate file and mobileprovision
    profile for signing. The resulting signature is valid for
    the duration of the certificate (typically 1 year).
    
    Features:
    - Offline signing (no Apple server required)
    - Development and Distribution support
    - Enterprise distribution support
    - Wildcard and specific App ID support
    - Automatic bundle ID adjustment
    - Framework and plugin signing
    
    Requirements:
    - .p12 certificate file with private key
    - mobileprovision file matching the certificate
    - Optional: p12 password
    """
    
    def __init__(
        self,
        p12_path: str,
        provision_path: str,
        p12_password: str = "",
        log_callback: Optional[Callable[[str, str], None]] = None
    ):
        """
        Initialize the annual signer.
        
        Args:
            p12_path: Path to .p12 certificate file
            provision_path: Path to .mobileprovision file
            p12_password: Password for P12 file (empty if none)
            log_callback: Optional logging callback function
        """
        self.p12_path = Path(p12_path)
        self.provision_path = Path(provision_path)
        self.p12_password = p12_password
        
        self.log_callback = log_callback or self._default_log
        self._core = SigningCore(log_callback=self.log_callback)
        
        self._certificate: Optional[Certificate] = None
        self._profile: Optional[ProvisioningProfile] = None
        self._identity: Optional[SigningIdentity] = None
        self._validated = False
    
    def _default_log(self, message: str, level: str = "info") -> None:
        print(message)
    
    def log(self, message: str, level: str = "info") -> None:
        self.log_callback(message, level)
    
    # =========================================================================
    # Validation
    # =========================================================================
    
    def validate(self) -> tuple[bool, str]:
        """
        Validate the certificate and provisioning profile.
        
        Checks:
        - Files exist
        - P12 can be parsed with password
        - Profile can be parsed
        - Certificate is valid (not expired)
        - Profile is valid (not expired)
        - Certificate is in the profile
        
        Returns:
            Tuple of (success, message)
        """
        errors = []
        
        # Check file existence
        if not self.p12_path.exists():
            errors.append(f"P12 file not found: {self.p12_path}")
        
        if not self.provision_path.exists():
            errors.append(f"Provisioning profile not found: {self.provision_path}")
        
        if errors:
            return False, "\n".join(errors)
        
        # Parse P12
        try:
            p12_handler = P12Handler(str(self.p12_path), self.p12_password)
            cert_info = p12_handler.get_certificate_info()
            
            # Create Certificate object
            cert_type = CertificateType.DEVELOPMENT
            if cert_info.get("cert_type") == "distribution":
                cert_type = CertificateType.DISTRIBUTION
            
            self._certificate = Certificate(
                serial_number=cert_info.get("serial_number", ""),
                common_name=cert_info.get("common_name", ""),
                organization=cert_info.get("organization"),
                team_id=cert_info.get("team_id"),
                cert_type=cert_type,
                not_before=cert_info.get("not_before", datetime.utcnow()),
                not_after=cert_info.get("not_after", datetime.utcnow()),
                fingerprint_sha1=cert_info.get("fingerprint_sha1", ""),
                fingerprint_sha256=cert_info.get("fingerprint_sha256", ""),
                raw_data=p12_handler.get_der_certificate(),
                private_key=p12_handler.get_pem_private_key()
            )
            
            self.log(f"[+] Certificate: {self._certificate.common_name}", "success")
            self.log(f"[*] Team ID: {self._certificate.team_id}")
            self.log(f"[*] Valid until: {self._certificate.not_after}")
            
        except CryptoError as e:
            errors.append(f"Failed to load P12: {e}")
        except Exception as e:
            errors.append(f"P12 error: {e}")
        
        # Parse provisioning profile
        try:
            profile_parser = ProvisioningProfileParser(str(self.provision_path))
            profile_info = profile_parser.get_profile_info()
            
            # Determine profile type
            profile_type_str = profile_info.get("profile_type", "Development")
            profile_type_map = {
                "Development": ProvisioningType.DEVELOPMENT,
                "AdHoc": ProvisioningType.AD_HOC,
                "AppStore": ProvisioningType.APP_STORE,
                "Enterprise": ProvisioningType.ENTERPRISE,
            }
            profile_type = profile_type_map.get(profile_type_str, ProvisioningType.DEVELOPMENT)
            
            self._profile = ProvisioningProfile(
                uuid=profile_info.get("uuid", ""),
                name=profile_info.get("name", ""),
                app_id=profile_info.get("app_id", ""),
                team_id=profile_info.get("team_id", ""),
                team_name=profile_info.get("team_name", ""),
                profile_type=profile_type,
                creation_date=profile_info.get("creation_date", datetime.utcnow()),
                expiration_date=profile_info.get("expiration_date", datetime.utcnow()),
                devices=profile_info.get("devices", []),
                entitlements=profile_info.get("entitlements", {}),
                certificates=profile_info.get("certificates", []),
                raw_data=profile_parser.raw_data
            )
            
            self.log(f"[+] Profile: {self._profile.name}", "success")
            self.log(f"[*] App ID: {self._profile.app_id}")
            self.log(f"[*] Type: {profile_type_str}")
            self.log(f"[*] Valid until: {self._profile.expiration_date}")
            
            if self._profile.devices:
                self.log(f"[*] Registered devices: {len(self._profile.devices)}")
            
        except CryptoError as e:
            errors.append(f"Failed to parse profile: {e}")
        except Exception as e:
            errors.append(f"Profile error: {e}")
        
        if errors:
            return False, "\n".join(errors)
        
        # Validate certificate/profile
        if not self._certificate.is_valid:
            errors.append(f"Certificate expired on {self._certificate.not_after}")
        
        if not self._profile.is_valid:
            errors.append(f"Profile expired on {self._profile.expiration_date}")
        
        # Check certificate is in profile
        if self._certificate and self._profile:
            cert_in_profile = False
            for cert_data in self._profile.certificates:
                import hashlib
                if isinstance(cert_data, bytes):
                    fp = hashlib.sha1(cert_data).hexdigest().upper()
                    if fp == self._certificate.fingerprint_sha1:
                        cert_in_profile = True
                        break
            
            if not cert_in_profile:
                errors.append("Certificate not found in provisioning profile")
        
        # Check team ID match
        if self._certificate and self._profile:
            if self._certificate.team_id != self._profile.team_id:
                errors.append(
                    f"Team ID mismatch: certificate={self._certificate.team_id}, "
                    f"profile={self._profile.team_id}"
                )
        
        if errors:
            return False, "\n".join(errors)
        
        # Create signing identity
        self._identity = SigningIdentity(
            certificate=self._certificate,
            profile=self._profile,
            method=SigningMethod.ANNUAL
        )
        
        self._validated = True
        self.log(f"[+] Signing identity validated successfully", "success")
        self.log(f"[*] Days remaining: {self._identity.days_remaining}")
        
        return True, "Validation successful"
    
    # =========================================================================
    # Signing
    # =========================================================================
    
    def sign_ipa(
        self,
        input_ipa: str,
        output_ipa: Optional[str] = None,
        new_bundle_id: Optional[str] = None,
        force: bool = False
    ) -> SigningResult:
        """
        Sign an IPA file.
        
        Args:
            input_ipa: Path to input IPA file
            output_ipa: Path for signed output (default: input-signed.ipa)
            new_bundle_id: Override bundle ID (optional)
            force: Force signing even with warnings
        
        Returns:
            SigningResult with operation details
        """
        input_path = Path(input_ipa)
        
        # Validate first if not done
        if not self._validated:
            valid, msg = self.validate()
            if not valid:
                return SigningResult(
                    success=False,
                    message=f"Validation failed: {msg}",
                    input_path=input_path,
                    errors=[msg]
                )
        
        # Check input exists
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
        self.log(f"[>] Annual Signing (Developer Certificate)")
        self.log(f"[>] Input: {input_path}")
        self.log(f"[>] Output: {output_path}")
        self.log(f"[>] Certificate: {self._certificate.common_name}")
        self.log(f"[>] Profile: {self._profile.name}")
        
        # Perform signing
        result = self._core.sign_ipa(
            str(input_path),
            str(output_path),
            self._certificate,
            self._profile,
            new_bundle_id
        )
        
        if result.success:
            self.log(f"[+] IPA signed successfully!", "success")
            self.log(f"[+] Output: {result.output_path}", "success")
            self.log(f"[+] Time: {result.signing_time:.2f}s", "success")
        else:
            self.log(f"[-] Signing failed: {result.message}", "error")
        
        return result
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def certificate(self) -> Optional[Certificate]:
        """Get loaded certificate."""
        return self._certificate
    
    @property
    def profile(self) -> Optional[ProvisioningProfile]:
        """Get loaded profile."""
        return self._profile
    
    @property
    def identity(self) -> Optional[SigningIdentity]:
        """Get signing identity."""
        return self._identity
    
    @property
    def is_valid(self) -> bool:
        """Check if signing identity is valid."""
        if not self._validated:
            return False
        return self._identity.is_valid if self._identity else False
    
    @property
    def days_remaining(self) -> int:
        """Days until signing identity expires."""
        if not self._identity:
            return 0
        return self._identity.days_remaining
    
    # =========================================================================
    # Info
    # =========================================================================
    
    def get_info(self) -> Dict[str, Any]:
        """Get signing configuration info."""
        info = {
            "method": "annual",
            "p12_path": str(self.p12_path),
            "provision_path": str(self.provision_path),
            "validated": self._validated,
        }
        
        if self._certificate:
            info["certificate"] = {
                "common_name": self._certificate.common_name,
                "team_id": self._certificate.team_id,
                "type": self._certificate.cert_type.value,
                "valid": self._certificate.is_valid,
                "days_remaining": self._certificate.days_remaining,
                "not_after": str(self._certificate.not_after),
            }
        
        if self._profile:
            info["profile"] = {
                "name": self._profile.name,
                "app_id": self._profile.app_id,
                "team_id": self._profile.team_id,
                "type": self._profile.profile_type.value,
                "valid": self._profile.is_valid,
                "days_remaining": self._profile.days_remaining,
                "devices_count": len(self._profile.devices),
                "is_wildcard": self._profile.is_wildcard,
            }
        
        return info


def get_installation_requirements() -> str:
    """Get requirements for annual signing."""
    return """
Annual Signing Requirements
===========================

Files needed:
1. .p12 Certificate file
   - Export from Keychain Access (macOS)
   - Or generate via Apple Developer Portal
   
2. .mobileprovision file
   - Download from Apple Developer Portal
   - Or export from Xcode

Certificate types supported:
- Apple Development
- Apple Distribution
- iOS Development
- iOS Distribution
- Enterprise Distribution

Python dependencies:
    pip install cryptography

Usage example:
    from signing.annual import AnnualSigner
    
    signer = AnnualSigner(
        p12_path="certificate.p12",
        provision_path="app.mobileprovision", 
        p12_password="yourpassword"
    )
    
    # Validate first
    valid, msg = signer.validate()
    if valid:
        result = signer.sign_ipa("app.ipa")
        if result.success:
            print(f"Signed: {result.output_path}")
"""
