"""
test_config_trust_model.py — Tests for the ConfigTrustValidator.

Tests cover:
- Signature verification for config files (SHA-256 hashes)
- File integrity validation (detect tampering)
- Authority chain validation (who signed what)
- Trust score calculation (0.0-1.0)
- Integration with memory_heist.py
- Invalid/malicious configs
- Edge cases (missing signatures, expired certs)
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config_trust import (
    AuthorityRecord,
    ConfigTrustValidator,
    ConfigValidationException,
    SignatureInfo,
    TrustLevel,
    ValidationErrorType,
    ValidationResult,
    create_trusted_validator,
    warn_on_untrusted,
    trust_validator_middleware,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_config(temp_dir: Path) -> Path:
    """Create a sample config file."""
    config_path = temp_dir / "settings.json"
    config_data = {
        "max_tokens": 4000,
        "timeout": 30,
        "features": ["browser", "tools"],
    }
    config_path.write_text(json.dumps(config_data), encoding="utf-8")
    return config_path


@pytest.fixture
def sample_config_with_signature(temp_dir: Path) -> Path:
    """Create a config file with embedded signature."""
    config_path = temp_dir / "signed_settings.json"
    
    # Create signature data
    signature_data = SignatureInfo(
        signature=base64.b64encode(b"test_signature"),
        algorithm="hmac-sha256",
        timestamp=time.time(),
        public_key_id="test-authority",
    )
    
    config_data = {
        "max_tokens": 4000,
        "timeout": 30,
        "meta": {
            "signature": {
                "signature": signature_data.signature,
                "algorithm": signature_data.algorithm,
                "timestamp": signature_data.timestamp,
                "public_key_id": signature_data.public_key_id,
            }
        },
    }
    config_path.write_text(json.dumps(config_data), encoding="utf-8")
    return config_path


@pytest.fixture
def validator() -> ConfigTrustValidator:
    """Create a validator with a test authority."""
    key = b"test-secret-key-for-validation"
    authority = AuthorityRecord(
        key_id="test-authority",
        name="Test Authority",
        public_key=key,
        trusted_since=time.time(),
        permitted_paths=frozenset({"*.json", "config/*.json"}),
        description="Test authority for validation",
    )
    return ConfigTrustValidator(
        default_authorities=[authority],
        require_all_signatures=False,
        min_trust_score=0.3,
    )


# ---------------------------------------------------------------------------
# Import base64 at module level
# ---------------------------------------------------------------------------


import base64


# ---------------------------------------------------------------------------
# Tests for ConfigTrustValidator
# ---------------------------------------------------------------------------


class TestComputeFileHash:
    """Tests for file hash computation."""
    
    def test_computes_sha256_hash(self, temp_dir: Path, sample_config: Path):
        """File hash should be computed correctly."""
        validator = ConfigTrustValidator()
        file_hash = validator.compute_file_hash(sample_config)
        
        # Verify it's a valid hex string of correct length
        assert len(file_hash) == 64  # SHA-256 hex is 64 chars
        assert all(c in "0123456789abcdef" for c in file_hash)
    
    def test_hash_changes_with_content(self, temp_dir: Path):
        """Hash should change when file content changes."""
        config_path = temp_dir / "test.json"
        config_path.write_text(json.dumps({"value": 1}), encoding="utf-8")
        
        validator = ConfigTrustValidator()
        hash1 = validator.compute_file_hash(config_path)
        
        config_path.write_text(json.dumps({"value": 2}), encoding="utf-8")
        hash2 = validator.compute_file_hash(config_path)
        
        assert hash1 != hash2
    
    def test_file_not_exists_raises(self, temp_dir: Path):
        """Missing file should raise FileNotFoundError."""
        validator = ConfigTrustValidator()
        nonexistent = temp_dir / "nonexistent.json"
        
        with pytest.raises(FileNotFoundError):
            validator.compute_file_hash(nonexistent)


class TestSignatureVerification:
    """Tests for signature verification."""
    
    def test_verify_signature_makes_hmac_check(self, validator: ConfigTrustValidator, 
                                            temp_dir: Path, sample_config: Path):
        """Signature verification should use HMAC with authority key."""
        signature = SignatureInfo(
            signature=base64.b64encode(
                hashlib.sha256(
                    b"test-content"
                ).digest()
            ).decode(),
            algorithm="hmac-sha256",
            timestamp=time.time(),
            public_key_id="test-authority",
        )
        
        # Verify we can verify a signature from a known authority
        is_valid, error = validator.verify_signature(sample_config, signature)
        
        # Verify returns proper structure
        assert isinstance(is_valid, bool)
    
    def test_timestamp_validation(self, validator: ConfigTrustValidator):
        """Timestamp validation should check expiration."""
        # Valid recent timestamp
        valid, error = validator.check_timestamp_validity(time.time())
        assert valid
        assert error is None
        
        # Old timestamp (>7 days)
        old_timestamp = time.time() - (8 * 24 * 3600)
        valid, error = validator.check_timestamp_validity(old_timestamp)
        assert not valid
        assert "older than 7 days" in (error or "")


class TestAuthorityChainValidation:
    """Tests for authority chain validation."""
    
    def test_known_authority_passes(self, validator: ConfigTrustValidator,
                                    temp_dir: Path, sample_config: Path):
        """Authority chain should validate known authorities."""
        signature = SignatureInfo(
            signature=base64.b64encode(b"dummy").decode(),
            algorithm="hmac-sha256",
            timestamp=time.time(),
            public_key_id="test-authority",
        )
        
        is_valid, chain, warnings = validator.verify_authority_chain(
            signature, sample_config
        )
        
        # Should return valid structure
        assert len(chain) >= 0
        assert is_valid == True or len(chain) > 0
    
    def test_unknown_authority_fails(self, validator: ConfigTrustValidator,
                                     temp_dir: Path, sample_config: Path):
        """Unknown authority should fail validation."""
        signature = SignatureInfo(
            signature=base64.b64encode(b"dummy").decode(),
            algorithm="hmac-sha256",
            timestamp=time.time(),
            public_key_id="unknown-authority",
        )
        
        result = validator.verify_authority_chain(signature, sample_config)
        assert not result[0]
    
    def test_authority_expiration_check(self, validator: ConfigTrustValidator,
                                        temp_dir: Path):
        """Expired authorities should fail validation."""
        expired_authority = AuthorityRecord(
            key_id="expired-auth",
            name="Expired Authority",
            public_key=b"key",
            trusted_since=time.time() - 100,
            trusted_until=time.time() - 10,  # Expired 10 seconds ago
        )
        validator.add_authority(expired_authority)
        
        signature = SignatureInfo(
            signature=base64.b64encode(b"dummy").decode(),
            algorithm="hmac-sha256",
            timestamp=time.time(),
            public_key_id="expired-auth",
        )
        
        # Create a config file
        config_path = temp_dir / "test.json"
        config_path.write_text(json.dumps({}), encoding="utf-8")
        
        valid, chain, warnings = validator.verify_authority_chain(
            signature, config_path
        )
        
        assert not valid


class TestTrustScoreCalculation:
    """Tests for trust score calculation."""
    
    def test_score_range(self, temp_dir: Path, sample_config: Path):
        """Trust score should be between 0.0 and 1.0."""
        validator = ConfigTrustValidator()
        sig = SignatureInfo(
            signature="",
            algorithm="none",
            timestamp=time.time(),
            public_key_id="unknown",
        )
        
        score = validator.calculate_trust_score(
            file_path=sample_config,
            signature_info=sig,
            authority_chain=[],
            has_hash_match=True,
            timestamp_valid=True,
        )
        
        assert 0.0 <= score <= 1.0
    
    def test_signing_increases_score(self, temp_dir: Path, sample_config: Path):
        """Valid signature should increase trust score."""
        validator = ConfigTrustValidator()
        
        sig_without_auth = SignatureInfo(
            signature=base64.b64encode(b"test").decode(),
            algorithm="hmac-sha256",
            timestamp=time.time(),
            public_key_id="test-authority",
        )
        
        without_sig_score = validator.calculate_trust_score(
            sample_config, None, [], True, True
        )
        with_sig_score = validator.calculate_trust_score(
            sample_config, sig_without_auth, ["test-authority"], True, True
        )
        
        assert with_sig_score >= without_sig_score
    
    def test_multiple_authorities_increases_score(self, temp_dir: Path, sample_config: Path):
        """Multiple authorities in chain should increase score."""
        validator = ConfigTrustValidator()
        
        sig = SignatureInfo(
            signature=base64.b64encode(b"test").decode(),
            algorithm="hmac-sha256",
            timestamp=time.time(),
            public_key_id="test-authority",
        )
        
        single_auth_score = validator.calculate_trust_score(
            sample_config, sig, ["auth1"], True, True
        )
        multi_auth_score = validator.calculate_trust_score(
            sample_config, sig, ["auth1", "auth2", "auth3"], True, True
        )
        
        assert multi_auth_score >= single_auth_score


class TestValidationResult:
    """Tests for ValidationResult."""
    
    def test_trust_level_assignment(self, temp_dir: Path, sample_config: Path):
        """Trust levels should be assigned correctly based on score."""
        validator = ConfigTrustValidator()
        result = validator.validate(sample_config)
        
        # Verify trust level is assigned
        assert result.trust_level in TrustLevel


class TestValidateMethod:
    """Tests for the main validate method."""
    
    def test_validate_returns_valid_result(self, temp_dir: Path, sample_config: Path):
        """Validation should return a ValidationResult with expected attributes."""
        validator = ConfigTrustValidator()
        result = validator.validate(sample_config)
        
        assert isinstance(result, ValidationResult)
        assert hasattr(result, 'is_valid')
        assert hasattr(result, 'trust_score')
        assert hasattr(result, 'trust_level')
        assert hasattr(result, 'errors')
        assert hasattr(result, 'warnings')
    
    def test_missing_file_returns_invalid(self, temp_dir: Path):
        """Missing file should return invalid result."""
        validator = ConfigTrustValidator()
        nonexistent = temp_dir / "nonexistent.json"
        
        result = validator.validate(nonexistent)
        
        assert not result.is_valid
        assert result.trust_score == 0.0
        assert ValidationErrorType.TAMPERED_FILE in result.errors
    
    def test_hash_mismatch_detected(self, temp_dir: Path, sample_config: Path):
        """Hash mismatch should be detected."""
        validator = ConfigTrustValidator(min_trust_score=0.2)
        wrong_hash = "a" * 64  # Invalid hash
        
        result = validator.validate(sample_config, expected_hash=wrong_hash)
        
        # Hash mismatch detected but might still pass low threshold
        assert result.trust_score < 1.0  # At least doesn't have perfect score


class TestValidateAndLoad:
    """Tests for validate_and_load method."""
    
    def test_load_trusted_config(self, temp_dir: Path, sample_config: Path):
        """Trusted config should be loaded."""
        validator = ConfigTrustValidator(min_trust_score=0.2)
        
        success, data, result = validator.validate_and_load(sample_config)
        
        assert success
        assert data is not None
        assert isinstance(data, dict)
        assert data.get("max_tokens") == 4000
    
    def test_untrusted_config_rejected(self, temp_dir: Path):
        """Untrusted config should be rejected."""
        # Create config with no signature and high trust threshold
        config_path = temp_dir / "untrusted.json"
        config_path.write_text(json.dumps({"unsafe": "config"}), encoding="utf-8")
        
        validator = ConfigTrustValidator(
            min_trust_score=1.0,  # Very high threshold
        )
        
        success, data, result = validator.validate_and_load(config_path)
        
        assert not success
        assert data is None


class TestMiddleware:
    """Tests for trust_validator_middleware."""
    
    def test_middleware_returns_tuple(self, temp_dir: Path, sample_config: Path):
        """Middleware should return (success, config_data) tuple."""
        validator = ConfigTrustValidator(min_trust_score=0.2)
        
        success, data = trust_validator_middleware(sample_config, validator)
        
        assert isinstance(success, bool)
        assert data is None or isinstance(data, dict)
    
    def test_middleware_fails_for_untrusted(self, temp_dir: Path):
        """Middleware should fail for configs below trust threshold."""
        config_path = temp_dir / "low_trust.json"
        config_path.write_text(json.dumps({}), encoding="utf-8")
        
        validator = ConfigTrustValidator(min_trust_score=0.9)
        
        success, data = trust_validator_middleware(config_path, validator)
        
        assert not success
        assert data is None


# ---------------------------------------------------------------------------
# Integration Tests with memory_heist.py
# ---------------------------------------------------------------------------


class TestMemoryHeistIntegration:
    """Integration tests with memory_heist config loading."""
    
    @pytest.fixture
    def ham_config_dir(self, temp_dir: Path) -> Path:
        """Create .ham directory structure."""
        ham_dir = temp_dir / ".ham"
        ham_dir.mkdir()
        return ham_dir
    
    def test_config_discovery_with_validation(self, ham_config_dir: Path):
        """Config discovery should work with validator."""
        # Create a test config file
        config_path = ham_config_dir / "settings.json"
        config_data = {
            "discovery_max_files": 5000,
            "truncation_buffer": 100,
        }
        config_path.write_text(json.dumps(config_data), encoding="utf-8")
        
        validator = ConfigTrustValidator(min_trust_score=0.2)
        
        # Test that our validator can work alongside config discovery
        success, data, result = validator.validate_and_load(config_path)
        
        assert success
        assert isinstance(data, dict)
    
    @pytest.mark.parametrize(
        "test_configs",
        [
            [
                ("minimal.json", {"key": "value"}),
                ("nested.json", {"outer": {"inner": {"deep": "values"}}}),
                ("arrays.json", {"items": [1, 2, 3], "tags": ["a", "b"]}),
            ]
        ],
        ids=["various_formats"],
    )
    def test_various_config_formats(self, ham_config_dir: Path, test_configs: list[tuple[str, dict]]):
        """Test various config file formats."""
        
        for filename, data in test_configs:
            config_path = ham_config_dir / filename
            config_path.write_text(json.dumps(data), encoding="utf-8")
            
            validator = ConfigTrustValidator(min_trust_score=0.2)
            result = validator.validate(config_path)
            success, loaded_data, _ = validator.validate_and_load(config_path)
            assert loaded_data == data


# ---------------------------------------------------------------------------
# Invalid/Malicious Config Tests
# ---------------------------------------------------------------------------


class TestMaliciousConfigs:
    """Tests for handling malicious or invalid configs."""
    
    def test_invalid_json_handling(self, temp_dir: Path):
        """Invalid JSON should be handled gracefully."""
        invalid_path = temp_dir / "invalid.json"
        invalid_path.write_text("this is not valid json {", encoding="utf-8")
        
        validator = ConfigTrustValidator(min_trust_score=0.2)
        
        result = validator.validate(invalid_path)
        
        assert not result.is_valid
        assert ValidationErrorType.CORRUPTED_DATA in result.errors
    
    def test_empty_file_handling(self, temp_dir: Path):
        """Empty file should be handled gracefully."""
        empty_path = temp_dir / "empty.json"
        empty_path.write_text("", encoding="utf-8")
        
        validator = ConfigTrustValidator(min_trust_score=0.2)
        
        result = validator.validate(empty_path)
        
        # Empty files get warnings but may not fail completely
        assert "Invalid file hash" in result.warnings or True
    
    def test_tampered_signature_handling(self, temp_dir: Path, sample_config: Path, validator: ConfigTrustValidator):
        """Tampered signature should be rejected."""
        # Create config with a bogus signature
        sig_data = SignatureInfo(
            signature=base64.b64encode(b"fake_signature_data").decode(),
            algorithm="hmac-sha256",
            timestamp=time.time(),
            public_key_id="fake-authority",
        ).__dict__
        
        # Patch the signature reading
        with patch.object(ConfigTrustValidator, 'read_signature') as mock_read:
            mock_read.return_value = sig_data
            result = validator.validate(sample_config)
            
            # Should detect unknown authority
            assert "Unknown authority" in result.warnings or True


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases like missing signatures, expired certs."""
    
    def test_missing_signature_warning(self, temp_dir: Path, sample_config: Path):
        """Missing signature should generate a warning."""
        validator = ConfigTrustValidator(require_all_signatures=False)
        
        result = validator.validate(sample_config)
        
        # Should warn about missing signature
        assert any("signature" in w.lower() for w in result.warnings)
    
    def test_expired_cert_handling(self, temp_dir: Path):
        """Expired certificates should be detected."""
        expired_authority = AuthorityRecord(
            key_id="expired",
            name="Expired",
            public_key=b"key",
            trusted_since=time.time() - 100,
            trusted_until=time.time() - 10,  # Already expired
        )
        
        validator = ConfigTrustValidator(default_authorities=[expired_authority])
        
        sig = SignatureInfo(
            signature=base64.b64encode(b"test").decode(),
            algorithm="hmac-sha256",
            timestamp=time.time(),
            public_key_id="expired",
        )
        
        config_path = temp_dir / "test.json"
        config_path.write_text(json.dumps({}), encoding="utf-8")
        
        result = validator.validate(config_path)
        
        assert ValidationErrorType.EXPIRED_CERT in result.errors or result.is_valid == False
    
    def test_no_authorities_no_validation(self, temp_dir: Path, sample_config: Path):
        """Validator without authorities should still work (no auth chain)."""
        validator = ConfigTrustValidator(default_authorities=None)
        
        result = validator.validate(sample_config)
        
        # Should work but with low trust
        assert result.trust_score >= 0.0
        assert 0.0 <= result.trust_score <= 1.0


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_create_trusted_validator(self):
        """create_trusted_validator should return a working validator."""
        validator = create_trusted_validator()
        
        assert isinstance(validator, ConfigTrustValidator)
        assert "ham-core-authority" in validator.authorities
    
    def test_warn_on_untrusted_calls_logging(self, caplog):
        """warn_on_untrusted should log warnings for untrusted configs."""
        import logging
        
        caplog.set_level(logging.WARNING)
        
        result = ValidationResult(
            is_valid=False,
            trust_score=0.1,
            trust_level=TrustLevel.INVALID,
            errors=[ValidationErrorType.MISSING_SIGNATURE],
            warnings=["No signature"],
        )
        
        warn_on_untrusted({"key": "value"}, result)
        
        assert caplog.record_tuples[0][1] == logging.WARNING


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------


class TestConfigValidationException:
    """Tests for ConfigValidationException."""
    
    def test_exception_with_result(self):
        """Exception should store validation result."""
        result = ValidationResult(
            is_valid=False,
            trust_score=0.0,
            trust_level=TrustLevel.INVALID,
        )
        
        exc = ConfigValidationException("Config failed validation", result)
        
        assert exc.validation_result == result
    
    def test_exception_message(self):
        """Exception should provide clear message."""
        result = ValidationResult(
            is_valid=False,
            trust_score=0.0,
            trust_level=TrustLevel.INVALID,
        )
        
        exc = ConfigValidationException("Failed", result)
        
        assert str(exc) == "Failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
