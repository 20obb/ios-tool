"""
iOS Signing Module for ios-tool
================================

This module provides IPA signing capabilities with two methods:

1. Annual Signing (Apple Developer Certificate)
   - Uses .p12 certificate + mobileprovision
   - Valid for 1 year
   - Works completely offline

2. Weekly Signing (Apple ID Sideloading)
   - Uses free Apple ID
   - Generates temporary certificates
   - Valid for 7 days
   - Requires Apple server communication

This module is designed as an extension and does NOT modify
any existing ios-tool functionality.

Usage:
    from signing import AnnualSigner, WeeklySigner
    
    # Annual signing
    signer = AnnualSigner(p12_path, provision_path, password)
    success, result = signer.sign_ipa(input_ipa, output_ipa)
    
    # Weekly signing
    signer = WeeklySigner(apple_id, password)
    success, result = signer.sign_ipa(input_ipa, output_ipa, device_udid)

Requirements:
    pip install cryptography pyOpenSSL plistlib
"""

__version__ = "1.0.0"
__author__ = "ios-tool contributors"

from typing import TYPE_CHECKING

# Lazy imports to avoid loading unnecessary dependencies
if TYPE_CHECKING:
    from .annual import AnnualSigner
    from .weekly import WeeklySigner
    from .core import SigningCore

__all__ = [
    "AnnualSigner",
    "WeeklySigner", 
    "SigningCore",
    "is_available",
    "get_signing_info",
]


def is_available() -> bool:
    """Check if signing module dependencies are available."""
    try:
        import cryptography
        from OpenSSL import crypto
        return True
    except ImportError:
        return False


def get_signing_info() -> dict:
    """Get signing module information and status."""
    info = {
        "version": __version__,
        "available": is_available(),
        "dependencies": {
            "cryptography": False,
            "pyOpenSSL": False,
        },
        "methods": {
            "annual": "Apple Developer Certificate (P12 + Provisioning)",
            "weekly": "Apple ID Sideloading (7 days)",
        }
    }
    
    try:
        import cryptography
        info["dependencies"]["cryptography"] = True
        info["cryptography_version"] = cryptography.__version__
    except ImportError:
        pass
    
    try:
        from OpenSSL import crypto
        info["dependencies"]["pyOpenSSL"] = True
    except ImportError:
        pass
    
    return info


def get_installation_instructions() -> str:
    """Get instructions for installing signing dependencies."""
    return """
iOS Signing Module - Installation Instructions
===============================================

Required dependencies:
    pip install cryptography pyOpenSSL

Optional (for enhanced functionality):
    pip install requests  # For Apple ID authentication

Platform-specific notes:

Windows:
    - All signing operations work natively
    - No additional tools required

macOS:
    - Native codesign tool is used when available
    - Provides best compatibility

Linux/BSD:
    - Pure Python signing implementation
    - No external dependencies needed

After installation, restart ios-tool to enable signing features.
"""
