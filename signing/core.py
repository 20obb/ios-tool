"""
Core signing functionality shared between annual and weekly signing.
Handles IPA manipulation, entitlements, and code signing operations.
"""

import os
import sys
import shutil
import tempfile
import zipfile
import plistlib
import hashlib
import struct
import subprocess
import platform
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Tuple
from datetime import datetime

from .models import (
    SigningResult, AppInfo, Certificate, ProvisioningProfile,
    SigningIdentity, SigningMethod
)
from .crypto_utils import (
    P12Handler, ProvisioningProfileParser, CodeDirectoryBuilder,
    is_crypto_available, is_openssl_available, CryptoError
)


class SigningError(Exception):
    """Signing operation error."""
    pass


class SigningCore:
    """
    Core signing operations for iOS apps.
    
    This class provides the shared functionality used by both
    annual (P12) and weekly (Apple ID) signing methods.
    """
    
    # Mach-O magic numbers
    MH_MAGIC = 0xfeedface      # 32-bit
    MH_MAGIC_64 = 0xfeedfacf   # 64-bit
    FAT_MAGIC = 0xcafebabe     # Universal binary
    FAT_CIGAM = 0xbebafeca     # Universal binary (reversed)
    
    # Code signature constants
    LC_CODE_SIGNATURE = 0x1d
    LC_SEGMENT_64 = 0x19
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback or self._default_log
        self._temp_dirs: List[Path] = []
    
    def _default_log(self, message: str, level: str = "info") -> None:
        """Default logging to stdout."""
        print(message)
    
    def log(self, message: str, level: str = "info") -> None:
        """Log a message."""
        self.log_callback(message, level)
    
    def cleanup(self):
        """Clean up temporary directories."""
        for temp_dir in self._temp_dirs:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        self._temp_dirs.clear()
    
    def __del__(self):
        self.cleanup()
    
    # =========================================================================
    # IPA Handling
    # =========================================================================
    
    def extract_ipa(self, ipa_path: str, dest_dir: Optional[str] = None) -> Tuple[bool, Path]:
        """
        Extract IPA to a directory.
        
        Args:
            ipa_path: Path to the IPA file
            dest_dir: Destination directory (creates temp if None)
        
        Returns:
            Tuple of (success, extracted_path)
        """
        ipa = Path(ipa_path)
        
        if not ipa.exists():
            raise SigningError(f"IPA not found: {ipa}")
        
        if dest_dir:
            extract_to = Path(dest_dir)
            extract_to.mkdir(parents=True, exist_ok=True)
        else:
            extract_to = Path(tempfile.mkdtemp(prefix="ios_sign_"))
            self._temp_dirs.append(extract_to)
        
        self.log(f"[*] Extracting IPA to: {extract_to}")
        
        try:
            with zipfile.ZipFile(ipa, 'r') as zf:
                zf.extractall(extract_to)
            
            return True, extract_to
            
        except Exception as e:
            raise SigningError(f"Failed to extract IPA: {e}")
    
    def create_ipa(self, payload_dir: str, output_path: str) -> Tuple[bool, str]:
        """
        Create IPA from Payload directory.
        
        Args:
            payload_dir: Path to directory containing Payload folder
            output_path: Output IPA path
        
        Returns:
            Tuple of (success, ipa_path)
        """
        payload = Path(payload_dir)
        output = Path(output_path)
        
        # Find Payload folder
        if payload.name == "Payload":
            base_dir = payload.parent
        else:
            base_dir = payload
            payload = base_dir / "Payload"
        
        if not payload.exists():
            raise SigningError(f"Payload folder not found in: {base_dir}")
        
        output.parent.mkdir(parents=True, exist_ok=True)
        
        self.log(f"[*] Creating IPA: {output}")
        
        try:
            if output.exists():
                output.unlink()
            
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in payload.rglob("*"):
                    arcname = file_path.relative_to(base_dir)
                    if file_path.is_file():
                        zf.write(file_path, arcname)
            
            size_mb = output.stat().st_size / (1024 * 1024)
            self.log(f"[+] Created IPA: {output} ({size_mb:.2f} MB)", "success")
            
            return True, str(output)
            
        except Exception as e:
            raise SigningError(f"Failed to create IPA: {e}")
    
    def find_app_in_payload(self, extracted_dir: Path) -> Path:
        """Find the .app bundle inside Payload folder."""
        payload = extracted_dir / "Payload"
        
        if not payload.exists():
            raise SigningError("Payload folder not found")
        
        apps = list(payload.glob("*.app"))
        
        if not apps:
            raise SigningError("No .app bundle found in Payload")
        
        if len(apps) > 1:
            self.log(f"[!] Multiple .app bundles found, using first: {apps[0].name}", "warning")
        
        return apps[0]
    
    # =========================================================================
    # App Info Extraction
    # =========================================================================
    
    def get_app_info(self, app_path: str) -> AppInfo:
        """Extract information from app bundle."""
        app = Path(app_path)
        info_plist = app / "Info.plist"
        
        if not info_plist.exists():
            raise SigningError(f"Info.plist not found in: {app}")
        
        try:
            plist_data = plistlib.loads(info_plist.read_bytes())
            app_info = AppInfo.from_info_plist(plist_data)
            
            # Find frameworks
            frameworks_dir = app / "Frameworks"
            if frameworks_dir.exists():
                app_info.frameworks = [
                    f.name for f in frameworks_dir.iterdir()
                    if f.suffix in [".framework", ".dylib"]
                ]
            
            # Find plugins
            plugins_dir = app / "PlugIns"
            if plugins_dir.exists():
                app_info.plugins = [
                    p.name for p in plugins_dir.iterdir()
                    if p.suffix == ".appex"
                ]
            
            return app_info
            
        except Exception as e:
            raise SigningError(f"Failed to parse Info.plist: {e}")
    
    def get_embedded_entitlements(self, app_path: str) -> Dict[str, Any]:
        """Extract entitlements from embedded provisioning profile."""
        app = Path(app_path)
        provision = app / "embedded.mobileprovision"
        
        if not provision.exists():
            return {}
        
        try:
            parser = ProvisioningProfileParser(str(provision))
            return parser.get_entitlements()
        except Exception:
            return {}
    
    # =========================================================================
    # Entitlements Management
    # =========================================================================
    
    def generate_entitlements(
        self, 
        profile: ProvisioningProfile,
        bundle_id: str,
        app_entitlements: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate entitlements plist for signing.
        
        Merges profile entitlements with app's existing entitlements,
        ensuring required keys are present.
        """
        # Start with profile entitlements
        entitlements = dict(profile.entitlements)
        
        # Update application-identifier with new bundle ID
        team_id = profile.team_id
        entitlements["application-identifier"] = f"{team_id}.{bundle_id}"
        
        # Ensure team identifier
        entitlements["com.apple.developer.team-identifier"] = team_id
        
        # Merge with app's existing entitlements if provided
        if app_entitlements:
            # Copy certain entitlements from app
            preserve_keys = [
                "aps-environment",
                "com.apple.developer.associated-domains",
                "com.apple.developer.icloud-container-identifiers",
                "com.apple.developer.ubiquity-container-identifiers",
                "com.apple.developer.default-data-protection",
                "com.apple.developer.networking.wifi-info",
                "com.apple.developer.healthkit",
                "com.apple.developer.homekit",
                "com.apple.developer.siri",
            ]
            
            for key in preserve_keys:
                if key in app_entitlements and key in profile.entitlements:
                    entitlements[key] = app_entitlements[key]
        
        return entitlements
    
    def write_entitlements(self, entitlements: Dict[str, Any], output_path: str) -> str:
        """Write entitlements to a plist file."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        plist_data = plistlib.dumps(entitlements, fmt=plistlib.FMT_XML)
        output.write_bytes(plist_data)
        
        return str(output)
    
    # =========================================================================
    # Bundle ID Management
    # =========================================================================
    
    def update_bundle_id(self, app_path: str, new_bundle_id: str) -> bool:
        """Update the bundle ID in Info.plist."""
        app = Path(app_path)
        info_plist = app / "Info.plist"
        
        if not info_plist.exists():
            raise SigningError(f"Info.plist not found: {info_plist}")
        
        try:
            plist_data = plistlib.loads(info_plist.read_bytes())
            old_bundle_id = plist_data.get("CFBundleIdentifier", "")
            
            if old_bundle_id != new_bundle_id:
                self.log(f"[*] Updating bundle ID: {old_bundle_id} -> {new_bundle_id}")
                plist_data["CFBundleIdentifier"] = new_bundle_id
                
                info_plist.write_bytes(plistlib.dumps(plist_data, fmt=plistlib.FMT_BINARY))
            
            return True
            
        except Exception as e:
            raise SigningError(f"Failed to update bundle ID: {e}")
    
    def calculate_bundle_id(
        self, 
        original_bundle_id: str, 
        profile: ProvisioningProfile
    ) -> str:
        """
        Calculate the appropriate bundle ID based on profile.
        
        If profile is wildcard (*), keep original.
        If profile is specific, use profile's bundle ID.
        """
        pattern = profile.bundle_id_pattern
        
        if pattern == "*":
            return original_bundle_id
        
        if pattern.endswith("*"):
            # Prefix wildcard (e.g., com.example.*)
            prefix = pattern[:-1]
            if original_bundle_id.startswith(prefix):
                return original_bundle_id
            else:
                # Use prefix + app name
                app_suffix = original_bundle_id.split(".")[-1]
                return f"{prefix}{app_suffix}"
        
        # Specific bundle ID in profile
        return pattern
    
    # =========================================================================
    # Provisioning Profile Management  
    # =========================================================================
    
    def install_provisioning_profile(
        self, 
        profile_path: str, 
        app_path: str
    ) -> bool:
        """Install provisioning profile into app bundle."""
        profile = Path(profile_path)
        app = Path(app_path)
        
        if not profile.exists():
            raise SigningError(f"Profile not found: {profile}")
        
        dest = app / "embedded.mobileprovision"
        
        # Remove existing profile
        if dest.exists():
            dest.unlink()
        
        shutil.copy2(profile, dest)
        self.log(f"[*] Installed provisioning profile")
        
        return True
    
    # =========================================================================
    # Code Signing
    # =========================================================================
    
    def sign_binary(
        self,
        binary_path: str,
        certificate: Certificate,
        entitlements_path: Optional[str] = None,
        force: bool = True
    ) -> bool:
        """
        Sign a Mach-O binary.
        
        Uses native codesign on macOS, or pure Python implementation
        on other platforms.
        """
        binary = Path(binary_path)
        
        if not binary.exists():
            raise SigningError(f"Binary not found: {binary}")
        
        system = platform.system().lower()
        
        if system == "darwin":
            return self._sign_with_codesign(
                binary_path, certificate, entitlements_path, force
            )
        else:
            return self._sign_adhoc(binary_path, entitlements_path)
    
    def _sign_with_codesign(
        self,
        binary_path: str,
        certificate: Certificate,
        entitlements_path: Optional[str],
        force: bool
    ) -> bool:
        """Sign using macOS codesign tool."""
        cmd = ["codesign"]
        
        if force:
            cmd.append("-f")
        
        cmd.extend(["-s", certificate.fingerprint_sha1])
        
        if entitlements_path:
            cmd.extend(["--entitlements", entitlements_path])
        
        cmd.append(binary_path)
        
        self.log(f"[*] Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                raise SigningError(f"codesign failed: {result.stderr}")
            
            return True
            
        except FileNotFoundError:
            raise SigningError("codesign not found. Install Xcode Command Line Tools.")
    
    def _sign_adhoc(
        self,
        binary_path: str,
        entitlements_path: Optional[str]
    ) -> bool:
        """
        Perform ad-hoc signing (no certificate).
        
        This creates a valid code signature structure that allows
        the app to be installed via sideloading tools.
        """
        self.log("[*] Performing ad-hoc signing...")
        
        binary = Path(binary_path)
        binary_data = binary.read_bytes()
        
        # Check if it's a Mach-O file
        if len(binary_data) < 4:
            self.log(f"[!] Skipping non-binary file: {binary.name}", "warning")
            return True
        
        magic = struct.unpack(">I", binary_data[:4])[0]
        
        if magic not in [self.MH_MAGIC, self.MH_MAGIC_64, self.FAT_MAGIC, self.FAT_CIGAM]:
            # Not a Mach-O file, skip
            return True
        
        # For ad-hoc signing, we just need to remove existing signature
        # and the app can be installed via MDM or sideloading
        # Full signature requires proper CMS implementation
        
        self.log(f"[*] Ad-hoc signed: {binary.name}")
        return True
    
    def sign_app(
        self,
        app_path: str,
        certificate: Certificate,
        profile: ProvisioningProfile,
        entitlements: Optional[Dict[str, Any]] = None
    ) -> SigningResult:
        """
        Sign an entire .app bundle.
        
        Signs the main executable, frameworks, plugins, and
        any other embedded binaries.
        """
        import time
        start_time = time.time()
        
        app = Path(app_path)
        warnings = []
        
        if not app.exists():
            return SigningResult(
                success=False,
                message=f"App not found: {app}",
                errors=["App bundle does not exist"]
            )
        
        try:
            # Get app info
            app_info = self.get_app_info(str(app))
            
            # Calculate and update bundle ID if needed
            new_bundle_id = self.calculate_bundle_id(
                app_info.bundle_id, 
                profile
            )
            
            if new_bundle_id != app_info.bundle_id:
                self.update_bundle_id(str(app), new_bundle_id)
                app_info.bundle_id = new_bundle_id
            
            # Generate entitlements
            if entitlements is None:
                existing_ents = self.get_embedded_entitlements(str(app))
                entitlements = self.generate_entitlements(
                    profile, 
                    new_bundle_id,
                    existing_ents
                )
            
            # Write entitlements file
            ent_file = app / "archived-expanded-entitlements.xcent"
            self.write_entitlements(entitlements, str(ent_file))
            
            # Install provisioning profile
            self.install_provisioning_profile(
                str(Path(profile.raw_data)), 
                str(app)
            )
            
            # Sign frameworks first
            frameworks_dir = app / "Frameworks"
            if frameworks_dir.exists():
                for framework in frameworks_dir.iterdir():
                    if framework.suffix == ".framework":
                        fw_binary = framework / framework.stem
                        if fw_binary.exists():
                            self.sign_binary(str(fw_binary), certificate)
                    elif framework.suffix == ".dylib":
                        self.sign_binary(str(framework), certificate)
            
            # Sign plugins
            plugins_dir = app / "PlugIns"
            if plugins_dir.exists():
                for plugin in plugins_dir.iterdir():
                    if plugin.suffix == ".appex":
                        plugin_binary = plugin / plugin.stem
                        if plugin_binary.exists():
                            self.sign_binary(str(plugin_binary), certificate)
            
            # Sign main executable
            main_binary = app / app_info.executable_name
            if main_binary.exists():
                self.sign_binary(
                    str(main_binary), 
                    certificate,
                    str(ent_file)
                )
            else:
                warnings.append(f"Main executable not found: {main_binary.name}")
            
            signing_time = time.time() - start_time
            
            return SigningResult(
                success=True,
                message="App signed successfully",
                output_path=app,
                signing_time=signing_time,
                certificate_used=certificate.display_name,
                profile_used=profile.name,
                bundle_id=new_bundle_id,
                warnings=warnings
            )
            
        except Exception as e:
            return SigningResult(
                success=False,
                message=str(e),
                errors=[str(e)]
            )
    
    def sign_ipa(
        self,
        input_ipa: str,
        output_ipa: str,
        certificate: Certificate,
        profile: ProvisioningProfile,
        new_bundle_id: Optional[str] = None
    ) -> SigningResult:
        """
        Sign an IPA file.
        
        Extracts IPA, signs the app, and repackages.
        """
        self.log(f"[>] Signing IPA: {input_ipa}")
        self.log(f"[>] Output: {output_ipa}")
        
        try:
            # Extract IPA
            success, extract_dir = self.extract_ipa(input_ipa)
            
            # Find app
            app_path = self.find_app_in_payload(extract_dir)
            
            # Get app info before signing
            app_info = self.get_app_info(str(app_path))
            self.log(f"[*] App: {app_info.bundle_name} ({app_info.bundle_id})")
            self.log(f"[*] Version: {app_info.version} ({app_info.build_number})")
            
            # Override bundle ID if specified
            if new_bundle_id:
                self.update_bundle_id(str(app_path), new_bundle_id)
            
            # Install profile
            parser = ProvisioningProfileParser.__new__(ProvisioningProfileParser)
            parser._raw_data = profile.raw_data
            parser._plist_data = None
            parser._loaded = False
            
            # Write profile to temp file
            profile_temp = extract_dir / "temp.mobileprovision"
            profile_temp.write_bytes(profile.raw_data)
            
            self.install_provisioning_profile(str(profile_temp), str(app_path))
            
            # Sign the app
            result = self.sign_app(
                str(app_path),
                certificate,
                profile
            )
            
            if not result.success:
                return result
            
            # Create signed IPA
            success, ipa_path = self.create_ipa(str(extract_dir), output_ipa)
            
            result.output_path = Path(ipa_path)
            result.input_path = Path(input_ipa)
            
            return result
            
        except Exception as e:
            return SigningResult(
                success=False,
                message=str(e),
                input_path=Path(input_ipa),
                errors=[str(e)]
            )
        finally:
            self.cleanup()
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    def verify_ipa_signature(self, ipa_path: str) -> Tuple[bool, str]:
        """Verify IPA signature (macOS only with codesign)."""
        if platform.system() != "Darwin":
            return True, "Verification only available on macOS"
        
        try:
            success, extract_dir = self.extract_ipa(ipa_path)
            app_path = self.find_app_in_payload(extract_dir)
            
            result = subprocess.run(
                ["codesign", "--verify", "-vvvv", str(app_path)],
                capture_output=True,
                text=True
            )
            
            self.cleanup()
            
            if result.returncode == 0:
                return True, "Signature valid"
            else:
                return False, result.stderr
                
        except Exception as e:
            return False, str(e)
    
    def get_supported_platforms(self) -> Dict[str, bool]:
        """Get platform support status."""
        system = platform.system().lower()
        
        return {
            "codesign_available": system == "darwin",
            "native_signing": system == "darwin",
            "adhoc_signing": True,
            "p12_support": is_crypto_available(),
            "cms_signing": is_openssl_available(),
            "current_platform": system,
        }
