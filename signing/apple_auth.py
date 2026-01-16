"""
Apple ID Authentication for Weekly Signing
============================================

Handles authentication with Apple's servers for free sideloading.
Uses Anisette data from community servers for proper authentication.
"""

import json
import hashlib
import base64
import uuid
import time
import os
from typing import Optional, Dict, Any, Tuple, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path

# Optional requests import
_requests_available = False
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    _requests_available = True
except ImportError:
    pass


def is_requests_available() -> bool:
    return _requests_available


class AuthenticationError(Exception):
    """Authentication failed."""
    pass


class TwoFactorRequired(Exception):
    """Two-factor authentication is required."""
    def __init__(self, message: str, session_data: Dict[str, Any]):
        super().__init__(message)
        self.session_data = session_data


@dataclass
class AppleSession:
    """Apple authentication session data."""
    dsid: str
    token: str
    scnt: str = ""
    session_id: str = ""
    auth_type: str = "password"
    team_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = None
    
    def __post_init__(self):
        if not self.expires_at:
            self.expires_at = self.created_at + timedelta(days=30)
    
    @property
    def is_valid(self) -> bool:
        return datetime.utcnow() < self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dsid": self.dsid,
            "token": self.token,
            "scnt": self.scnt,
            "session_id": self.session_id,
            "auth_type": self.auth_type,
            "team_id": self.team_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppleSession":
        return cls(
            dsid=data["dsid"],
            token=data["token"],
            scnt=data.get("scnt", ""),
            session_id=data.get("session_id", ""),
            auth_type=data.get("auth_type", "password"),
            team_id=data.get("team_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )


class AppleAuthenticator:
    """
    Authenticates with Apple ID for free signing.
    Uses Anisette data from SideStore servers.
    """
    
    # Anisette servers (try multiple)
    ANISETTE_SERVERS = [
        "https://ani.sidestore.io/",
        "https://sideloadly.io/anisette/generate",
    ]
    
    # Apple authentication endpoints
    AUTH_ENDPOINT = "https://idmsa.apple.com/appleauth/auth"
    
    # Developer services
    DEV_ENDPOINT = "https://developerservices2.apple.com/services"
    
    def __init__(self, log_callback=None):
        self.log_callback = log_callback or print
        self._session: Optional[AppleSession] = None
        self._http: Optional[requests.Session] = None
        self._anisette_data: Dict[str, str] = {}
        self._auth_headers: Dict[str, str] = {}
        self._pending_session: Dict[str, Any] = {}  # Store session while waiting for 2FA
        
    def log(self, message: str, level: str = "info"):
        """Log a message."""
        if callable(self.log_callback):
            self.log_callback(message, level)
        else:
            print(message)
    
    def _safe_json(self, response) -> Dict[str, Any]:
        """Safely parse JSON response."""
        if not response.text or not response.text.strip():
            return {}
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError):
            return {}
    
    def _get_http(self) -> "requests.Session":
        """Get HTTP session."""
        if not _requests_available:
            raise AuthenticationError("requests module required: pip install requests")
        
        if self._http is None:
            self._http = requests.Session()
            
            retry = Retry(total=2, backoff_factor=0.5)
            adapter = HTTPAdapter(max_retries=retry)
            self._http.mount("https://", adapter)
        
        return self._http
    
    def _fetch_anisette(self) -> Dict[str, str]:
        """Fetch fresh Anisette data from available servers."""
        self.log("[*] Fetching Anisette data...")
        
        http = self._get_http()
        
        last_error = None
        for server_url in self.ANISETTE_SERVERS:
            try:
                self.log(f"[*] Trying: {server_url}")
                response = http.get(
                    server_url,
                    headers={"User-Agent": "AltStore/1.6.1"},
                    timeout=15
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check if we got valid data
                    md = data.get("X-Apple-I-MD", "")
                    md_m = data.get("X-Apple-I-MD-M", "")
                    
                    if not md or not md_m:
                        self.log(f"[!] Server returned incomplete data, trying next...", "warning")
                        continue
                    
                    self._anisette_data = {
                        "X-Apple-I-MD": md,
                        "X-Apple-I-MD-M": md_m,
                        "X-Apple-I-MD-RINFO": data.get("X-Apple-I-MD-RINFO", "17106176"),
                        "X-Apple-I-MD-LU": data.get("X-Apple-I-MD-LU", ""),
                        "X-Apple-I-SRL-NO": data.get("X-Apple-I-SRL-NO", "0"),
                        "X-Mme-Client-Info": data.get("X-Mme-Client-Info", 
                            "<iMac20,1> <Mac OS X;13.0;22A380> <com.apple.AuthKit/1 (com.apple.dt.Xcode/3594.4.19)>"),
                        "X-Mme-Device-Id": data.get("X-Mme-Device-Id", str(uuid.uuid4()).upper()),
                        "X-Apple-I-TimeZone": data.get("X-Apple-I-TimeZone", "UTC"),
                        "X-Apple-I-Client-Time": data.get("X-Apple-I-Client-Time", 
                            datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),
                        "X-Apple-Locale": data.get("X-Apple-Locale", "en_US"),
                    }
                    self.log(f"[+] Anisette data fetched (MD length: {len(md)})", "success")
                    return self._anisette_data
                    
            except Exception as e:
                last_error = e
                self.log(f"[!] Server failed: {e}", "warning")
                continue
        
        raise AuthenticationError(f"Failed to fetch Anisette data from any server: {last_error}")
    
    def _build_auth_headers(self, session_data: Dict = None) -> Dict[str, str]:
        """Build authentication headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Xcode",
            "X-Apple-Widget-Key": "e0b80c3bf78523bfe80974d320935bfa30add02e1bff88ec2166c6bd5a706c42",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://idmsa.apple.com",
            "Referer": "https://idmsa.apple.com/",
        }
        
        # Add Anisette data
        headers.update(self._anisette_data)
        
        # Add session tokens if available
        if session_data:
            if session_data.get("scnt"):
                headers["scnt"] = session_data["scnt"]
            if session_data.get("session_id"):
                headers["X-Apple-ID-Session-Id"] = session_data["session_id"]
        
        return headers
    
    # =========================================================================
    # Main Authentication
    # =========================================================================
    
    def authenticate(
        self, 
        apple_id: str, 
        password: str,
        two_factor_code: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Authenticate with Apple ID.
        
        Flow:
        1. Fetch Anisette data
        2. Sign in with credentials
        3. If 2FA required, send code to devices
        4. User enters code
        5. Verify code
        """
        self.log(f"[*] Authenticating as: {apple_id}")
        
        try:
            # If we have a pending session and a 2FA code, verify it directly
            if two_factor_code and self._pending_session:
                self.log("[*] Verifying 2FA code with existing session...")
                result = self._verify_2fa(self._pending_session, two_factor_code)
                if result[0]:  # Success
                    self._pending_session = {}  # Clear pending session
                return result
            
            # Step 1: Get Anisette data (required!)
            self._fetch_anisette()
            
            # Step 2: Initialize and sign in
            session_data = self._init_and_signin(apple_id, password)
            
            # Step 3: Check if 2FA is needed
            if session_data.get("needs_2fa"):
                if two_factor_code:
                    # Verify the code
                    return self._verify_2fa(session_data, two_factor_code)
                else:
                    # Store session for later verification
                    self._pending_session = session_data.copy()
                    # Send code to devices and tell user
                    self._request_2fa_code(session_data)
                    raise TwoFactorRequired(
                        "Verification code sent to your devices",
                        session_data
                    )
            
            # Success without 2FA
            self._create_session(session_data)
            self.log("[+] Authentication successful", "success")
            return True, "Authentication successful"
            
        except TwoFactorRequired:
            raise
        except AuthenticationError as e:
            self.log(f"[-] {e}", "error")
            return False, str(e)
        except Exception as e:
            self.log(f"[-] Error: {e}", "error")
            return False, str(e)
    
    def _init_and_signin(self, apple_id: str, password: str) -> Dict[str, Any]:
        """Initialize session and sign in."""
        http = self._get_http()
        
        # Build headers with Anisette
        headers = self._build_auth_headers()
        
        # First request to get session tokens
        self.log("[*] Initializing session...")
        
        try:
            init_resp = http.get(
                f"{self.AUTH_ENDPOINT}/signin",
                headers=headers,
                params={"widgetKey": headers["X-Apple-Widget-Key"]},
                timeout=30
            )
            
            session_data = {
                "scnt": init_resp.headers.get("scnt", ""),
                "session_id": init_resp.headers.get("X-Apple-ID-Session-Id", ""),
            }
        except requests.RequestException as e:
            raise AuthenticationError(f"Failed to initialize: {e}")
        
        # Now sign in
        self.log("[*] Signing in...")
        
        headers = self._build_auth_headers(session_data)
        
        payload = {
            "accountName": apple_id,
            "password": password,
            "rememberMe": True,
        }
        
        try:
            response = http.post(
                f"{self.AUTH_ENDPOINT}/signin",
                json=payload,
                headers=headers,
                params={"isRememberMeEnabled": "true"},
                timeout=30
            )
            
            self.log(f"[*] Sign-in response: HTTP {response.status_code}")
            
            # Update session tokens from response
            session_data["scnt"] = response.headers.get("scnt", session_data.get("scnt", ""))
            session_data["session_id"] = response.headers.get(
                "X-Apple-ID-Session-Id", session_data.get("session_id", "")
            )
            
            if response.status_code == 200:
                # Direct success (no 2FA)
                data = self._safe_json(response)
                session_data.update(data)
                session_data["dsid"] = response.headers.get("X-Apple-DS-ID", "")
                session_data["token"] = response.headers.get("X-Apple-Session-Token", "")
                return session_data
            
            elif response.status_code == 409:
                # 2FA required - this is normal
                self.log("[*] Two-factor authentication required")
                self.log(f"[*] Session tokens: scnt={bool(session_data.get('scnt'))}, session_id={bool(session_data.get('session_id'))}")
                session_data["needs_2fa"] = True
                return session_data
            
            elif response.status_code == 401:
                error = self._safe_json(response)
                self.log(f"[!] Auth response: {response.text[:500] if response.text else 'empty'}", "warning")
                msg = "Invalid Apple ID or password"
                if error.get("serviceErrors"):
                    msg = error["serviceErrors"][0].get("message", msg)
                raise AuthenticationError(msg)
            
            elif response.status_code == 403:
                raise AuthenticationError(
                    "Account locked or needs verification at appleid.apple.com"
                )
            
            elif response.status_code == 503:
                raise AuthenticationError(
                    "Apple servers temporarily unavailable. Please try again in a moment."
                )
            
            else:
                error = self._safe_json(response)
                msg = f"Sign in failed (HTTP {response.status_code})"
                if error.get("serviceErrors"):
                    msg = error["serviceErrors"][0].get("message", msg)
                raise AuthenticationError(msg)
                
        except requests.RequestException as e:
            raise AuthenticationError(f"Network error: {e}")
    
    def _request_2fa_code(self, session_data: Dict[str, Any]):
        """Request 2FA code be sent to trusted devices."""
        http = self._get_http()
        headers = self._build_auth_headers(session_data)
        headers["Accept"] = "application/json"
        
        self.log("[*] Requesting verification code...")
        
        try:
            # Request code to be sent to trusted devices via PUT
            # This triggers Apple to push the code
            response = http.put(
                f"{self.AUTH_ENDPOINT}/verify/trusteddevice",
                headers=headers,
                json={},
                timeout=30
            )
            
            self.log(f"[*] Code request response: {response.status_code}")
            
            if response.status_code in [200, 201, 202]:
                self.log("[+] Verification code sent to your trusted devices!", "success")
                return
            
            # If PUT didn't work, try triggering via GET on the 2sv endpoint
            response = http.get(
                f"{self.AUTH_ENDPOINT}/2sv/trust",
                headers=headers,
                timeout=30
            )
            
            if response.status_code in [200, 201, 202, 204]:
                self.log("[+] Verification code sent!", "success")
                return
            
            # Try requesting phone number verification as fallback
            response = http.get(
                f"{self.AUTH_ENDPOINT}/verify/phone",
                headers=headers,
                timeout=30
            )
            
            self.log("[*] Check your trusted devices for the verification code", "info")
                
        except Exception as e:
            self.log(f"[!] Error requesting code: {e}", "warning")
            self.log("[*] Check your trusted devices for the verification code", "info")
    
    def _verify_2fa(self, session_data: Dict[str, Any], code: str) -> Tuple[bool, str]:
        """Verify 2FA code."""
        http = self._get_http()
        
        # Clean code
        code = code.replace(" ", "").replace("-", "")
        if len(code) != 6 or not code.isdigit():
            raise AuthenticationError("Verification code must be 6 digits")
        
        headers = self._build_auth_headers(session_data)
        
        payload = {
            "securityCode": {"code": code}
        }
        
        self.log("[*] Verifying code...")
        
        try:
            response = http.post(
                f"{self.AUTH_ENDPOINT}/verify/trusteddevice/securitycode",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            # Update tokens
            if response.headers.get("scnt"):
                session_data["scnt"] = response.headers.get("scnt")
            if response.headers.get("X-Apple-ID-Session-Id"):
                session_data["session_id"] = response.headers.get("X-Apple-ID-Session-Id")
            
            if response.status_code in [200, 204]:
                # Trust the session
                self._trust_session(session_data)
                
                # Get final tokens
                session_data["dsid"] = response.headers.get("X-Apple-DS-ID", "")
                session_data["token"] = response.headers.get("X-Apple-Session-Token", "")
                
                self._create_session(session_data)
                self.log("[+] Verification successful!", "success")
                return True, "Authentication successful"
            
            elif response.status_code == 401:
                raise AuthenticationError("Invalid verification code. Please try again.")
            
            elif response.status_code == 400:
                raise AuthenticationError("Code expired or invalid. Please request a new code.")
            
            else:
                error = self._safe_json(response)
                msg = f"Verification failed (HTTP {response.status_code})"
                if error.get("serviceErrors"):
                    msg = error["serviceErrors"][0].get("message", msg)
                raise AuthenticationError(msg)
                
        except requests.RequestException as e:
            raise AuthenticationError(f"Network error: {e}")
    
    def _trust_session(self, session_data: Dict[str, Any]):
        """Mark session as trusted."""
        http = self._get_http()
        headers = self._build_auth_headers(session_data)
        
        try:
            http.get(f"{self.AUTH_ENDPOINT}/2sv/trust", headers=headers, timeout=10)
        except Exception:
            pass  # Optional, don't fail
    
    def _create_session(self, session_data: Dict[str, Any]):
        """Create session from auth data."""
        self._session = AppleSession(
            dsid=session_data.get("dsid", ""),
            token=session_data.get("token", ""),
            scnt=session_data.get("scnt", ""),
            session_id=session_data.get("session_id", ""),
            auth_type="2fa" if session_data.get("needs_2fa") else "password",
        )
        
        # Store auth headers for later use
        self._auth_headers = self._build_auth_headers(session_data)
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    @property
    def session(self) -> Optional[AppleSession]:
        return self._session
    
    @property
    def is_authenticated(self) -> bool:
        return self._session is not None and self._session.is_valid
    
    def save_session(self, path: str):
        """Save session to file."""
        if not self._session:
            raise AuthenticationError("No session to save")
        
        data = self._session.to_dict()
        data["anisette"] = self._anisette_data
        Path(path).write_text(json.dumps(data, indent=2))
    
    def load_session(self, path: str) -> bool:
        """Load session from file."""
        try:
            data = json.loads(Path(path).read_text())
            self._session = AppleSession.from_dict(data)
            self._anisette_data = data.get("anisette", {})
            
            if not self._session.is_valid:
                self._session = None
                return False
            
            return True
        except Exception:
            return False
    
    def logout(self):
        """Clear session."""
        self._session = None
        self._anisette_data = {}
        self._auth_headers = {}
        if self._http:
            self._http.close()
            self._http = None
    
    # =========================================================================
    # Developer Services
    # =========================================================================
    
    def get_teams(self) -> List[Dict[str, Any]]:
        """Get development teams."""
        if not self.is_authenticated:
            raise AuthenticationError("Not authenticated")
        
        http = self._get_http()
        headers = self._get_dev_headers()
        
        try:
            response = http.post(
                f"{self.DEV_ENDPOINT}/QH65B2/listTeams.action",
                headers=headers,
                data="",
                timeout=30
            )
            
            if response.status_code == 200:
                data = self._safe_json(response)
                teams = data.get("teams", [])
                
                if teams and self._session and not self._session.team_id:
                    self._session.team_id = teams[0].get("teamId")
                
                return teams
            
            return []
            
        except Exception as e:
            self.log(f"[-] Failed to get teams: {e}", "error")
            return []
    
    def _get_dev_headers(self) -> Dict[str, str]:
        """Get developer service headers."""
        headers = {
            "Content-Type": "text/x-xml-plist",
            "Accept": "text/x-xml-plist",
            "User-Agent": "Xcode",
            "X-Xcode-Version": "15.0 (15A240d)",
        }
        
        cookies = []
        if self._session and self._session.token:
            cookies.append(f"myacinfo={self._session.token}")
        
        if cookies:
            headers["Cookie"] = "; ".join(cookies)
        
        # Add Anisette
        headers.update(self._anisette_data)
        
        return headers


def get_auth_requirements() -> str:
    """Get authentication requirements info."""
    return """
Apple ID Authentication
========================

How Weekly Signing works:

1. Enter your Apple ID email and password
2. Click "Sign IPA (Weekly)"
3. A 6-digit code will be sent to your iPhone/iPad/Mac
4. Enter the code in the "2FA Code" field
5. Click "Sign IPA (Weekly)" again

Requirements:
- Apple ID (free account works)
- Device UDID of target iPhone/iPad

Limitations (Apple's rules):
- Max 3 apps signed per week (free accounts)
- Signature valid for 7 days only
- Must re-sign weekly

Troubleshooting:
- Account locked? Visit appleid.apple.com
- No code received? Check all Apple devices
- Still failing? Wait a few minutes and retry
"""
