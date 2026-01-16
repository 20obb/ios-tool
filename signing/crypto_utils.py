"""
Cryptographic utilities for iOS signing.
Provides cross-platform certificate and key handling.
"""

import hashlib
import struct
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime
import plistlib
import re

# Lazy imports for optional dependencies
_crypto_available = False
_openssl_available = False

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import NameOID
    _crypto_available = True
except ImportError:
    pass

try:
    from OpenSSL import crypto
    _openssl_available = True
except ImportError:
    pass


def is_crypto_available() -> bool:
    """Check if cryptography module is available."""
    return _crypto_available


def is_openssl_available() -> bool:
    """Check if OpenSSL module is available."""
    return _openssl_available


class CryptoError(Exception):
    """Cryptographic operation error."""
    pass


class P12Handler:
    """Handle PKCS#12 (.p12) certificate files."""
    
    def __init__(self, p12_path: str, password: str = ""):
        self.p12_path = Path(p12_path)
        self.password = password.encode() if password else b""
        self._certificate = None
        self._private_key = None
        self._ca_certs = []
        self._loaded = False
    
    def load(self) -> bool:
        """Load and parse the P12 file."""
        if not self.p12_path.exists():
            raise CryptoError(f"P12 file not found: {self.p12_path}")
        
        if not _crypto_available:
            raise CryptoError("cryptography module not installed. Run: pip install cryptography")
        
        try:
            p12_data = self.p12_path.read_bytes()
            
            # Parse PKCS#12
            private_key, certificate, ca_certs = pkcs12.load_key_and_certificates(
                p12_data, 
                self.password,
                default_backend()
            )
            
            self._private_key = private_key
            self._certificate = certificate
            self._ca_certs = ca_certs or []
            self._loaded = True
            
            return True
            
        except Exception as e:
            raise CryptoError(f"Failed to load P12: {e}")
    
    @property
    def certificate(self):
        """Get the certificate object."""
        if not self._loaded:
            self.load()
        return self._certificate
    
    @property
    def private_key(self):
        """Get the private key object."""
        if not self._loaded:
            self.load()
        return self._private_key
    
    @property
    def ca_certificates(self) -> list:
        """Get CA certificates chain."""
        if not self._loaded:
            self.load()
        return self._ca_certs
    
    def get_certificate_info(self) -> Dict[str, Any]:
        """Extract certificate information."""
        cert = self.certificate
        if not cert:
            return {}
        
        # Extract subject fields
        subject = cert.subject
        
        def get_oid_value(oid):
            try:
                return subject.get_attributes_for_oid(oid)[0].value
            except (IndexError, ValueError):
                return None
        
        common_name = get_oid_value(NameOID.COMMON_NAME)
        org = get_oid_value(NameOID.ORGANIZATION_NAME)
        org_unit = get_oid_value(NameOID.ORGANIZATIONAL_UNIT_NAME)
        
        # Determine certificate type from common name
        cert_type = "unknown"
        if common_name:
            cn_lower = common_name.lower()
            if "development" in cn_lower or "developer" in cn_lower:
                cert_type = "development"
            elif "distribution" in cn_lower:
                cert_type = "distribution"
        
        # Extract Team ID from organizational unit
        team_id = None
        if org_unit:
            # Team ID is typically in format like "ABC123DEF"
            match = re.search(r'([A-Z0-9]{10})', org_unit)
            if match:
                team_id = match.group(1)
        
        # Calculate fingerprints
        cert_der = cert.public_bytes(serialization.Encoding.DER)
        sha1_fp = hashlib.sha1(cert_der).hexdigest().upper()
        sha256_fp = hashlib.sha256(cert_der).hexdigest().upper()
        
        return {
            "common_name": common_name,
            "organization": org,
            "organizational_unit": org_unit,
            "team_id": team_id,
            "cert_type": cert_type,
            "serial_number": format(cert.serial_number, 'x').upper(),
            "not_before": cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before,
            "not_after": cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after,
            "fingerprint_sha1": sha1_fp,
            "fingerprint_sha256": sha256_fp,
            "issuer": cert.issuer.rfc4514_string(),
        }
    
    def get_pem_certificate(self) -> bytes:
        """Export certificate as PEM."""
        if not self.certificate:
            raise CryptoError("No certificate loaded")
        return self.certificate.public_bytes(serialization.Encoding.PEM)
    
    def get_der_certificate(self) -> bytes:
        """Export certificate as DER."""
        if not self.certificate:
            raise CryptoError("No certificate loaded")
        return self.certificate.public_bytes(serialization.Encoding.DER)
    
    def get_pem_private_key(self, password: Optional[bytes] = None) -> bytes:
        """Export private key as PEM."""
        if not self.private_key:
            raise CryptoError("No private key loaded")
        
        encryption = serialization.NoEncryption()
        if password:
            encryption = serialization.BestAvailableEncryption(password)
        
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption
        )


class ProvisioningProfileParser:
    """Parse and extract data from mobileprovision files."""
    
    def __init__(self, profile_path: str):
        self.profile_path = Path(profile_path)
        self._plist_data = None
        self._raw_data = None
        self._loaded = False
    
    def load(self) -> bool:
        """Load and parse the provisioning profile."""
        if not self.profile_path.exists():
            raise CryptoError(f"Profile not found: {self.profile_path}")
        
        try:
            self._raw_data = self.profile_path.read_bytes()
            
            # Extract plist from CMS/PKCS7 envelope
            plist_data = self._extract_plist(self._raw_data)
            self._plist_data = plistlib.loads(plist_data)
            self._loaded = True
            
            return True
            
        except Exception as e:
            raise CryptoError(f"Failed to parse profile: {e}")
    
    def _extract_plist(self, data: bytes) -> bytes:
        """Extract plist data from CMS envelope."""
        # Find plist markers
        plist_start = data.find(b"<?xml")
        if plist_start == -1:
            plist_start = data.find(b"<plist")
        
        plist_end = data.rfind(b"</plist>")
        
        if plist_start == -1 or plist_end == -1:
            raise CryptoError("Could not find plist data in profile")
        
        return data[plist_start:plist_end + len(b"</plist>")]
    
    @property
    def plist(self) -> Dict[str, Any]:
        """Get the parsed plist data."""
        if not self._loaded:
            self.load()
        return self._plist_data or {}
    
    @property
    def raw_data(self) -> bytes:
        """Get the raw profile data."""
        if not self._loaded:
            self.load()
        return self._raw_data or b""
    
    def get_profile_info(self) -> Dict[str, Any]:
        """Extract profile information."""
        plist = self.plist
        
        # Parse dates
        creation_date = plist.get("CreationDate")
        expiration_date = plist.get("ExpirationDate")
        
        # Get profile type
        provisions_all = plist.get("ProvisionsAllDevices", False)
        get_task_allow = plist.get("Entitlements", {}).get("get-task-allow", False)
        
        if provisions_all:
            profile_type = "Enterprise"
        elif get_task_allow:
            profile_type = "Development"
        else:
            # Check for devices list
            if plist.get("ProvisionedDevices"):
                profile_type = "AdHoc"
            else:
                profile_type = "AppStore"
        
        # Extract entitlements
        entitlements = plist.get("Entitlements", {})
        app_id = entitlements.get("application-identifier", "")
        
        return {
            "uuid": plist.get("UUID", ""),
            "name": plist.get("Name", ""),
            "app_id": app_id,
            "team_id": plist.get("TeamIdentifier", [""])[0],
            "team_name": plist.get("TeamName", ""),
            "profile_type": profile_type,
            "creation_date": creation_date,
            "expiration_date": expiration_date,
            "devices": plist.get("ProvisionedDevices", []),
            "entitlements": entitlements,
            "certificates": plist.get("DeveloperCertificates", []),
            "provisions_all_devices": provisions_all,
        }
    
    def get_entitlements(self) -> Dict[str, Any]:
        """Get entitlements from the profile."""
        return self.plist.get("Entitlements", {})
    
    def get_bundle_id_pattern(self) -> str:
        """Get the bundle ID pattern."""
        app_id = self.plist.get("Entitlements", {}).get("application-identifier", "")
        parts = app_id.split(".", 1)
        return parts[1] if len(parts) > 1 else "*"
    
    def contains_certificate(self, cert_fingerprint: str) -> bool:
        """Check if profile contains a specific certificate."""
        cert_fingerprint = cert_fingerprint.upper().replace(":", "")
        
        for cert_data in self.plist.get("DeveloperCertificates", []):
            if isinstance(cert_data, bytes):
                fp = hashlib.sha1(cert_data).hexdigest().upper()
                if fp == cert_fingerprint:
                    return True
        
        return False


class CodeDirectoryBuilder:
    """Build iOS Code Directory structures for signing."""
    
    # Magic values
    CSMAGIC_REQUIREMENT = 0xfade0c00
    CSMAGIC_REQUIREMENTS = 0xfade0c01
    CSMAGIC_CODEDIRECTORY = 0xfade0c02
    CSMAGIC_EMBEDDED_SIGNATURE = 0xfade0cc0
    CSMAGIC_BLOBWRAPPER = 0xfade0b01
    
    # Hash types
    CS_HASHTYPE_SHA1 = 1
    CS_HASHTYPE_SHA256 = 2
    CS_HASHTYPE_SHA256_TRUNCATED = 3
    
    def __init__(self, binary_path: str):
        self.binary_path = Path(binary_path)
        self._binary_data = None
    
    def load_binary(self) -> bool:
        """Load the Mach-O binary."""
        if not self.binary_path.exists():
            raise CryptoError(f"Binary not found: {self.binary_path}")
        
        self._binary_data = self.binary_path.read_bytes()
        return True
    
    def compute_page_hashes(self, page_size: int = 4096) -> List[bytes]:
        """Compute SHA256 hashes for each page of the binary."""
        if not self._binary_data:
            self.load_binary()
        
        hashes = []
        data = self._binary_data
        
        for i in range(0, len(data), page_size):
            page = data[i:i + page_size]
            page_hash = hashlib.sha256(page).digest()
            hashes.append(page_hash)
        
        return hashes
    
    def compute_info_plist_hash(self, plist_path: Path) -> bytes:
        """Compute hash of Info.plist."""
        if not plist_path.exists():
            return b""
        return hashlib.sha256(plist_path.read_bytes()).digest()
    
    def compute_resource_hash(self, resources_path: Path) -> bytes:
        """Compute hash of _CodeSignature/CodeResources."""
        if not resources_path.exists():
            return b""
        return hashlib.sha256(resources_path.read_bytes()).digest()


def generate_cms_signature(data: bytes, certificate, private_key) -> bytes:
    """Generate CMS/PKCS7 signature for code signing."""
    if not _openssl_available:
        raise CryptoError("OpenSSL not available for CMS signing")
    
    # This is a simplified implementation
    # Full CMS signing requires proper PKCS7 structure
    
    # For now, return empty - real implementation needs pyOpenSSL
    # or external codesign tool
    raise NotImplementedError("CMS signing requires additional implementation")


def verify_signature(signed_data: bytes, signature: bytes, certificate) -> bool:
    """Verify a CMS signature."""
    if not _crypto_available:
        raise CryptoError("cryptography module not available")
    
    # Simplified verification
    # Real implementation needs full CMS parsing
    return False
