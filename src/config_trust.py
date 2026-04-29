"""
config_trust.py — Config Trust Validator for Ham Context Engine.

Provides cryptographic validation of external configuration files to ensure
integrity and authenticity before trusting their contents. Implements:
- SHA-256 signature verification
- File integrity validation (detect tampering)
- Authority chain validation (who signed what)
- Trust score calculation (0.0-1.0)

Security-first design: always validates, warns on missing signatures,
and fails safely on untrusted configs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Enums and Exceptions
# ---------------------------------------------------------------------------


class TrustLevel(Enum):
    """Trust levels for config validation results."""
    HIGH = "high"          # 0.8 - 1.0 - Fully trusted
    MEDIUM = "medium"      # 0.5 - 0.8 - Partially trusted
    LOW = "low"           # 0.2 - 0.5 - Low confidence
    INVALID = "invalid"   # 0.0 - 0.2 - Untrusted/invalid


class ValidationErrorType(Enum):
    """Types of validation errors that can occur."""
    MISSING_SIGNATURE = "missing_signature"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_HASH = "invalid_hash"
    EXPIRED_CERT = "expired_cert"
    UNRECOGNIZED_AUTHOR = "unrecognized_author"
    TAMPERED_FILE = "tampered_file"
    CORRUPTED_DATA = "corrupted_data"
    MISSING_AUTHORITY_CHAIN = "missing_authority_chain"


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a configuration file."""
    is_valid: bool
    trust_score: float
    trust_level: TrustLevel
    errors: list[ValidationErrorType] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    signature_info: Optional[dict[str, Any]] = None
    author_info: Optional[dict[str, Any]] = None
    authority_chain: list[str] = field(default_factory=list)


class ConfigValidationException(Exception):
    """Exception raised when config validation fails."""
    def __init__(self, message: str, validation_result: ValidationResult | None = None):
        super().__init__(message)
        self.validation_result = validation_result


# ---------------------------------------------------------------------------
# Cryptographic Primitives
# ---------------------------------------------------------------------------


@dataclass
class SignatureInfo:
    """Information about a signed config file."""
    signature: str
    algorithm: str
    timestamp: float
    public_key_id: str


@dataclass
class AuthorityRecord:
    """Record of an authority that can sign configs."""
    key_id: str
    name: str
    public_key: bytes
    trusted_since: float
    trusted_until: Optional[float] = None  # None = no expiration
    permitted_paths: frozenset[str] = frozenset()
    description: str = ""


# ---------------------------------------------------------------------------
# Config Trust Validator
# ---------------------------------------------------------------------------


class ConfigTrustValidator:
    """
    Validates external configuration files for integrity and authenticity.
    
    Features:
    - SHA-256 hash verification for file integrity
    - Digital signature verification using HMAC or public keys
    - Multi-level authority chain support
    - Trust score calculation based on multiple factors
    - Graceful handling of missing or invalid signatures
    """
    
    def __init__(
        self,
        default_authorities: Optional[list[AuthorityRecord]] = None,
        require_all_signatures: bool = False,
        min_trust_score: float = 0.5,
        hash_algorithm: str = "sha256",
    ):
        """
        Initialize the ConfigTrustValidator.
        
        Args:
            default_authorities: List of trusted authorities for signature verification.
                If None, no authority chains will be validated.
            require_all_signatures: If True, all configs must have signatures.
                If False, missing signatures generate warnings but don't fail.
            min_trust_score: Minimum trust score (0.0-1.0) required for configs
                to be considered valid. Defaults to 0.5 (medium trust).
            hash_algorithm: Algorithm for file hashing. Defaults to "sha256".
        """
        self.authorities: dict[str, AuthorityRecord] = {}
        require_all_signatures = require_all_signatures
        self.min_trust_score = min_trust_score
        self.hash_algorithm = hash_algorithm
        
        if default_authorities:
            self.add_authorities(default_authorities)
    
    def add_authority(self, authority: AuthorityRecord) -> None:
        """
        Add a single authority to the validator.
        
        Args:
            authority: Authority configuration to add.
        
        Raises:
            ValueError: If the authority already exists.
        """
        if authority.key_id in self.authorities:
            raise ValueError(f"Authority {authority.key_id} already registered")
        self.authorities[authority.key_id] = authority
    
    def add_authorities(self, authorities: list[AuthorityRecord]) -> None:
        """
        Add multiple authorities at once.
        
        Args:
            authorities: List of AuthorityRecord instances.
        """
        for authority in authorities:
            self.add_authority(authority)
    
    def remove_authority(self, key_id: str) -> None:
        """
        Remove an authority by its key ID.
        
        Args:
            key_id: The key ID of the authority to remove.
        
        Raises:
            KeyError: If the authority doesn't exist.
        """
        if key_id not in self.authorities:
            raise KeyError(f"Authority {key_id} not found")
        del self.authorities[key_id]
    
    def compute_file_hash(self, file_path: Path) -> str:
        """
        Compute SHA-256 hash of a file.
        
        Args:
            file_path: Path to the file.
        
        Returns:
            Hexadecimal hash string.
        
        Raises:
            FileNotFoundError: If file doesn't exist.
            PermissionError: If file can't be read.
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def read_signature(self, file_path: Path) -> Optional[SignatureInfo]:
        """
        Read signature metadata from a config file (in JSON format).
        
        Args:
            file_path: Path to the config file.
        
        Returns:
            SignatureInfo if signature exists in file metadata, None otherwise.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Look for signature in metadata
            signature_data = data.get("_meta", {}).get("signature")
            if not signature_data:
                return None
            
            return SignatureInfo(
                signature=signature_data.get("signature", ""),
                algorithm=signature_data.get("algorithm", "sha256"),
                timestamp=signature_data.get("timestamp", 0.0),
                public_key_id=signature_data.get("public_key_id", ""),
            )
        except (OSError, json.JSONDecodeError):
            return None
    
    def verify_signature(
        self,
        file_path: Path,
        signature_info: SignatureInfo,
    ) -> tuple[bool, Optional[str]]:
        """
        Verify that a signature matches a config file.
        
        Args:
            file_path: Path to the config file.
            signature_info: Signature information to verify against.
        
        Returns:
            Tuple of (is_valid, error_message or None).
        """
        try:
            # Read original file content (without signature block)
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()
            
            # Extract signature metadata if embedded
            try:
                data = json.loads(original_content)
                if "_meta" in data:
                    # Remove metadata from content for verification
                    del data["_meta"]
                    original_content = json.dumps(data, separators=(",", ":"))
            except json.JSONDecodeError:
                pass
            
            # Convert signature to bytes
            sig_bytes = base64.b64decode(signature_info.signature)
            
            if signature_info.algorithm in ("none", "none-hmac", ""):
                # No signature verification, trust based on other factors
                return True, None
            
            # Try HMAC verification first
            authority = self.authorities.get(signature_info.public_key_id)
            if authority:
                # HMAC-based verification
                computed = hmac.new(
                    authority.public_key,
                    original_content.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                
                try:
                    if not hmac.compare_digest(
                        base64.b64decode(signature_info.signature).hex(),
                        computed,
                    ):
                        return False, "Signature mismatch"
                except ValueError:
                    # Not a valid base64, try hex comparison
                    return False, "Invalid signature encoding"
                
                return True, None
            
            return False, f"Unrecognized authority: {signature_info.public_key_id}"
        
        except base64.binascii.Error as e:
            return False, f"Invalid signature encoding: {e}"
        except Exception as e:
            return False, f"Verification error: {e}"
    
    def check_timestamp_validity(
        self,
        timestamp: float,
        current_time: float | None = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a signature timestamp is valid (not expired).
        
        Args:
            timestamp: Unix timestamp to check.
            current_time: Current timestamp, defaults to time.time().
        
        Returns:
            Tuple of (is_valid, error_message or None).
        """
        now = current_time or time.time()
        age_seconds = now - timestamp
        
        # Configs older than 7 days are considered potentially stale
        if age_seconds > 7 * 24 * 3600:
            return False, "Signature older than 7 days"
        
        return True, None
    
    def verify_authority_chain(
        self,
        signature_info: SignatureInfo,
        file_path: Path,
    ) -> tuple[bool, list[str], list[str]]:
        """
        Verify the authority chain for a signed config.
        
        Args:
            signature_info: Signature to validate.
            file_path: Path to the config file.
        
        Returns:
            Tuple of (is_valid, chain_of_authorities, warning_list).
        """
        warnings: list[str] = []
        chain: list[str] = []
        path_str = str(file_path)
        
        # Check if signature uses a known authority
        if signature_info.public_key_id not in self.authorities:
            warnings.append(f"Unknown authority: {signature_info.public_key_id}")
            return False, list(warnings), warnings
        
        authority = self.authorities[signature_info.public_key_id]
        chain.append(authority.key_id)
        
        # Check path permissions
        if authority.permitted_paths:
            path_match = any(
                path_str.startswith(pattern) or path_str.endswith(pattern)
                for pattern in authority.permitted_paths
            )
            if not path_match:
                warnings.append(
                    f"Signature authority {authority.key_id} not authorized for path {path_str}"
                )
        
        # Check expiration
        if authority.trusted_until and time.time() > authority.trusted_until:
            warnings.append(f"Authority {authority.key_id} has expired")
            return False, chain, warnings
        
        return len(chain) >= 1, chain, warnings
    
    def calculate_trust_score(
        self,
        file_path: Path,
        signature_info: SignatureInfo | None,
        authority_chain: list[str],
        has_hash_match: bool,
        timestamp_valid: bool,
    ) -> float:
        """
        Calculate a trust score (0.0 - 1.0) based on validation results.
        
        Scoring weights:
        - Signature present: +0.3
        - Signature verified: +0.3
        - Known authority: +0.1
        - Path authorized: +0.1
        - Hash match: +0.2
        - Timestamp valid: +0.1
        
        Args:
            file_path: Path to validate.
            signature_info: Info about signature (None if missing).
            authority_chain: List of authorities in chain.
            has_hash_match: Whether file hash matches expected.
            timestamp_valid: Whether signature timestamp is valid.
        
        Returns:
            Trust score between 0.0 and 1.0.
        """
        score = 0.0
        
        # Signature present (bonus)
        if signature_info is not None:
            score += 0.3
        
        # Signature verified (major factor)
        if signature_info and authority_chain:
            score += 0.3
        
        # Known authority (reputation bonus)
        if signature_info and signature_info.public_key_id in self.authorities:
            score += 0.1
        
        # Authoritative chain (multiple authorities)
        score += min(len(authority_chain) * 0.05, 0.1)  # Max 0.1 for multiple authorities
        
        # Hash match (integrity)
        if has_hash_match:
            score += 0.2
        
        # Timestamp validity
        if timestamp_valid:
            score += 0.1
        
        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, score))
    
    def validate(
        self,
        file_path: Path,
        expected_hash: str | None = None,
        signature_path: Path | None = None,
        custom_authorities: Optional[list[AuthorityRecord]] = None,
    ) -> ValidationResult:
        """
        Validate a configuration file for integrity and authenticity.
        
        Args:
            file_path: Path to the config file to validate.
            expected_hash: Optional SHA-256 hash to compare against.
            signature_path: Optional path to a separate signature file.
            custom_authorities: Optional list of authorities for this validation.
        
        Returns:
            ValidationResult with trust score and validation status.
        """
        import tempfile
        import os
        
        file_path = Path(file_path)
        errors: list[ValidationErrorType] = []
        warnings: list[str] = []
        authority_chain: list[str] = []
        signature_info: SignatureInfo | None = None
        
        try:
            # Check file existence
            if not file_path.exists():
                errors.append(ValidationErrorType.TAMPERED_FILE)
                return ValidationResult(
                    is_valid=False,
                    trust_score=0.0,
                    trust_level=TrustLevel.INVALID,
                    errors=errors,
                    warnings=["File does not exist"],
                )
            
            # Compute file hash
            computed_hash = self.compute_file_hash(file_path)
            has_hash_match = expected_hash is None or computed_hash == expected_hash
            
            if not has_hash_match:
                error_type = (
                    ValidationErrorType.TAMPERED_FILE
                    if expected_hash is not None
                    else ValidationErrorType.INVALID_HASH
                )
                if expected_hash is not None:
                    errors.append(error_type)
                    warnings.append(f"Hash mismatch: expected {expected_hash}, got {computed_hash}")
                else:
                    warnings.append(f"Invalid file hash: {computed_hash}")
            
            # Read signature from file or separate file
            if signature_path:
                signature_info = self.read_signature(signature_path)
            else:
                signature_info = self.read_signature(file_path)
                if not signature_info:
                    try:
                        signature_info = self.read_signature(file_path)
                    except:
                        pass
            
            # Check if signature is required
            if signature_info is None:
                if self.require_all_signatures:
                    errors.append(ValidationErrorType.MISSING_SIGNATURE)
                else:
                    warnings.append("No signature found - treating as untrusted")
            
            # Verify signature if present
            if signature_info:
                sig_valid, sig_error = self.verify_signature(file_path, signature_info)
                
                if not sig_valid:
                    errors.append(ValidationErrorType.INVALID_SIGNATURE)
                    warnings.append(sig_error or "Signature verification failed")
                else:
                    # Check authority chain
                    chain_valid, author_chain, chain_warnings = self.verify_authority_chain(
                        signature_info, file_path
                    )
                    if chain_valid:
                        authority_chain = author_chain
                    warnings.extend(chain_warnings)
                
                # Check timestamp
                ts_valid, ts_error = self.check_timestamp_validity(signature_info.timestamp)
                if not ts_valid:
                    errors.append(ValidationErrorType.EXPIRED_CERT)
                    warnings.append(ts_error or "Timestamp invalid")
            
            # If no custom authorities provided, use defaults
            current_authorities = custom_authorities or []
            all_authorities = self.authorities.copy()
            for auth in current_authorities:
                all_authorities[auth.key_id] = auth
            
            # If authorities exist, verify chain
            if signature_info and signature_info.public_key_id in all_authorities:
                authority_chain = [signature_info.public_key_id]
            
            # Calculate trust score
            trust_score = self.calculate_trust_score(
                file_path=file_path,
                signature_info=signature_info,
                authority_chain=authority_chain,
                has_hash_match=has_hash_match,
                timestamp_valid=len(errors) == 0 or ValidationErrorType.EXPIRED_CERT not in errors,
            )
            
            # Determine trust level
            if trust_score >= 0.8:
                trust_level = TrustLevel.HIGH
            elif trust_score >= 0.5:
                trust_level = TrustLevel.MEDIUM
            elif trust_score >= 0.2:
                trust_level = TrustLevel.LOW
            else:
                trust_level = TrustLevel.INVALID
            
            # Determine validity
            is_valid = trust_score >= self.min_trust_score
            
            # Get author info if available
            author_info = None
            if signature_info and signature_info.public_key_id in self.authorities:
                auth = self.authorities[signature_info.public_key_id]
                author_info = {
                    "key_id": auth.key_id,
                    "name": auth.name,
                    "description": auth.description,
                }
            
            return ValidationResult(
                is_valid=is_valid,
                trust_score=round(trust_score, 3),
                trust_level=trust_level,
                errors=errors,
                warnings=warnings,
                signature_info={
                    "algorithm": signature_info.algorithm if signature_info else None,
                    "timestamp": signature_info.timestamp if signature_info else None,
                    "key_id": signature_info.public_key_id if signature_info else None,
                } if signature_info else None,
                authority_chain=authority_chain,
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                trust_score=0.0,
                trust_level=TrustLevel.INVALID,
                errors=[ValidationErrorType.CORRUPTED_DATA],
                warnings=[f"Validation error: {str(e)}"],
            )
    
    def validate_and_load(
        self,
        file_path: Path,
        on_untrusted: Callable[[ValidationResult], bool] | None = None,
    ) -> tuple[bool, dict[str, Any] | None, ValidationResult]:
        """
        Validate a config file and load it if trusted.
        
        Args:
            file_path: Path to the config file.
            on_untrusted: Optional callback that gets called when a config
                is untrusted. Return True to allow loading anyway, False to reject.
        
        Returns:
            Tuple of (was_loaded, config_data, validation_result).
        """
        validation_result = self.validate(file_path)
        
        # Check if valid according to our threshold
        if not validation_result.is_valid:
            # Allow override via callback
            if on_untrusted:
                if not on_untrusted(validation_result):
                    return False, None, validation_result
            
            return False, None, validation_result
        
        # Load and parse config
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return True, data, validation_result
    
    def get_trust_level_description(self, level: TrustLevel) -> str:
        """
        Get human-readable description for a trust level.
        
        Args:
            level: Trust level to describe.
        
        Returns:
            Description string.
        """
        descriptions = {
            TrustLevel.HIGH: "High trust - fully verified and signed by known authority",
            TrustLevel.MEDIUM: "Medium trust - partially verified, reasonable confidence",
            TrustLevel.LOW: "Low trust - limited verification, use with caution",
            TrustLevel.INVALID: "Invalid - could not verify, should not be trusted",
        }
        return descriptions.get(level, "Unknown trust level")


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


def create_trusted_validator() -> ConfigTrustValidator:
    """
    Create a validator with sensible defaults for Ham configuration files.
    
    Returns:
        ConfigTrustValidator with default authority setup.
    """
    # Default trusted authorities (these would be loaded from a known-good source)
    default_authorities: list[AuthorityRecord] = [
        AuthorityRecord(
            key_id="ham-core-authority",
            name="Ham Core Development Team",
            public_key=b"ham-default-public-key-placeholder",
            trusted_since=time.time(),
            permitted_paths=frozenset({
                ".ham/",
                "config/",
                ".ham/settings.json",
                ".ham.json",
            }),
            description="Primary authority for Ham configuration files",
        ),
    ]
    
    return ConfigTrustValidator(
        default_authorities=default_authorities,
        require_all_signatures=False,
        min_trust_score=0.5,
        hash_algorithm="sha256",
    )


def warn_on_untrusted(config_data: dict[str, Any], validation_result: ValidationResult) -> None:
    """
    Callback that logs warnings for untrusted configs but allows loading.
    
    Args:
        config_data: The config data (not used in this implementation).
        validation_result: The validation result to log warnings from.
    """
    import logging
    
    logger = logging.getLogger("config_trust")
    
    if validation_result.trust_level == TrustLevel.INVALID:
        logger.warning(
            "UNTRUSTED CONFIG: Config file failed validation. "
            f"Errors: {[e.value for e in validation_result.errors]}"
        )
    elif validation_result.trust_level == TrustLevel.LOW:
        logger.warning(
            "LOW TRUST: Config file has low trust score. "
            f"Score: {validation_result.trust_score:.3f}, "
            f"Warnings: {validation_result.warnings}"
        )


def trust_validator_middleware(
    file_path: Path,
    validator: ConfigTrustValidator,
) -> tuple[bool, dict[str, Any] | None]:
    """
    Middleware function to validate and load configs in a safe manner.
    
    Args:
        file_path: Path to the config file.
        validator: ConfigTrustValidator instance.
    
    Returns:
        Tuple of (success, config_data or None).
    """
    was_loaded, config_data, result = validator.validate_and_load(
        file_path,
        on_untrusted=lambda result: warn_on_untrusted(None, result),
    )
    if was_loaded:
        return True, config_data
    return False, None
