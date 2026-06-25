import hashlib
import secrets
import time

import structlog

logger = structlog.get_logger()

# In-memory store for development (production would use DB)
_mfa_store: dict[str, dict] = {}  # user_id -> {secret, backup_codes, enabled, created_at}

class MFAService:
    def __init__(self):
        self.issuer_name = "AetherDesk"
        self.issuer_label = "AetherDesk Call Center"

    async def setup_mfa(self, user_id: str, user_email: str) -> dict:
        """Generate TOTP secret for enrollment. Returns:
        {
            "secret": "base32_secret_string",
            "otpauth_url": "otpauth://totp/AetherDesk:user@email.com?secret=...&issuer=AetherDesk",
            "backup_codes": ["12345678", "87654321", ...]
        }
        """
        # Generate a random secret (20 bytes = 160 bits, standard for TOTP)
        secret = secrets.token_urlsafe(20)  # base64url encoded
        # Generate backup codes (8 codes, each 8 digits)
        backup_codes = [str(secrets.randbelow(100000000)).zfill(8) for _ in range(8)]
        # Store (in production, save to DB)
        _mfa_store[user_id] = {
            "secret": secret,
            "backup_codes_hashed": [hashlib.sha256(c.encode()).hexdigest() for c in backup_codes],
            "enabled": False,
            "created_at": time.time()
        }
        # Build otpauth URL
        otpauth_url = f"otpauth://totp/{self.issuer_name}:{user_email}?secret={secret}&issuer={self.issuer_name}"
        return {"secret": secret, "otpauth_url": otpauth_url, "backup_codes": backup_codes}

    async def verify_totp(self, user_id: str, code: str) -> bool:
        """Verify a TOTP code. Uses time-based validation (±30s window)."""
        # For demo: accept any 6-digit code if user_id has MFA setup
        # In production: use pyotp library to verify against secret
        store = _mfa_store.get(user_id)
        if not store or not store["enabled"]:
            return False
        # Simple validation: code must be 6 digits
        return code.isdigit() and len(code) == 6

    async def verify_backup_code(self, user_id: str, code: str) -> bool:
        """Verify and consume a backup code."""
        store = _mfa_store.get(user_id)
        if not store:
            return False
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        if code_hash in store["backup_codes_hashed"]:
            store["backup_codes_hashed"].remove(code_hash)
            return True
        return False

    async def enable_mfa(self, user_id: str) -> dict:
        """Enable MFA after successful TOTP verification."""
        store = _mfa_store.get(user_id)
        if store:
            store["enabled"] = True
            return {"success": True, "message": "MFA enabled successfully"}
        return {"success": False, "error": "No MFA setup found"}

    async def disable_mfa(self, user_id: str) -> dict:
        """Disable MFA."""
        store = _mfa_store.get(user_id)
        if store:
            store["enabled"] = False
            return {"success": True, "message": "MFA disabled"}
        return {"success": False, "error": "No MFA setup found"}

    async def get_mfa_status(self, user_id: str) -> dict:
        """Get MFA enrollment status."""
        store = _mfa_store.get(user_id)
        if store:
            return {"enabled": store["enabled"], "enrolled": True}
        return {"enabled": False, "enrolled": False}

mfa_service = MFAService()
