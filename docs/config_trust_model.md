# Config Trust Model

> **Instruction Trust Model for the Ham Context Engine**

A security-focused configuration validation system that ensures the integrity and authenticity of external configuration files before trusting their contents in the Ham Context Engine.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Usage Examples](#usage-examples)
- [Security Considerations](#security-considerations)
- [Threat Model](#threat-model)
- [Integration with memory_heist.py](#integration-with-memory_heistpy)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Config Trust Model provides cryptographic validation of configuration files used by the Ham Context Engine (`memory_heist.py`). It implements:

* **SHA-256 signature verification** for config files
* **File integrity validation** to detect tampering
* **Authority chain validation** to verify who signed what
* **Trust score calculation** (0.0-1.0) based on multiple factors
* **Graceful handling** of missing or invalid signatures

### Security Design Principles

1. **Validate First**: Always validate configs before using them
2. **Fail Safely**: Untrusted configs are rejected or flagged
3. **Warn, Don't Crash**: Missing signatures generate warnings but don't crash
4. **Defense in Depth**: Multiple layers of verification
5. **Audit Trail**: All validation results are trackable

---

## Architecture

### Components

```
ConfigTrustValidator
├── SignatureInfo        # Cryptographic signature metadata
├── AuthorityRecord      # Trusted signing authorities
├── TrustLevel           # Enum: HIGH, MEDIUM, LOW, INVALID
├── ValidationErrorType  # Enum: error types
├── ValidationResult     # Validation outcome
└── Validation Methods:
    ├── compute_file_hash()
    ├── verify_signature()
    ├── check_timestamp_validity()
    ├── verify_authority_chain()
    ├── calculate_trust_score()
    └── validate()
```

### Trust Score Calculation

The trust score (0.0-1.0) is calculated based on:

| Factor | Weight | Description |
|--------|--------|-------------|
| Signature Present | +0.3 | Config has a signature block |
| Signature Verified | +0.3 | Signature matches authority |
| Known Authority | +0.1 | Authority is in whitelist |
| Path Authorized | +0.1 | Authority signed for this path |
| Hash Match | +0.2 | File content hash is valid |
| Timestamp Valid | +0.1 | Signature is recent (<7 days) |
| Multiple Authorities | +0.05 each | Multi-sig bonus (max 0.1) |

### Trust Levels

| Level | Score Range | Usage |
|-------|-------------|-------|
| **HIGH** | 0.8 - 1.0 | Fully trusted, can be used without restrictions |
| **MEDIUM** | 0.5 - 0.8 | Partially trusted, monitor for suspicious patterns |
| **LOW** | 0.2 - 0.5 | Limited trust, use with caution |
| **INVALID** | 0.0 - 0.2 | Do not trust, reject config |

---

## API Reference

### Classes

#### `ConfigTrustValidator`

The main validator class for configuration files.

**Constructor:**
```python
ConfigTrustValidator(
    default_authorities: Optional[list[AuthorityRecord]] = None,
    require_all_signatures: bool = False,
    min_trust_score: float = 0.5,
    hash_algorithm: str = "sha256",
)
```

**Parameters:**
* `default_authorities` - List of trusted signing authorities
* `require_all_signatures` - If True, fail validation for unsigned configs
* `min_trust_score` - Minimum score (0.0-1.0) required for validation success
* `hash_algorithm` - Hash algorithm (default: "sha256")

**Methods:**

##### `add_authority(authority: AuthorityRecord) -> None`
Add a trusted authority for signature verification.

##### `add_authorities(authorities: list[AuthorityRecord]) -> None`
Add multiple authorities at once.

##### `remove_authority(key_id: str) -> None`
Remove an authority by its key ID.

##### `compute_file_hash(file_path: Path) -> str`
Compute SHA-256 hash of a file.

**Returns:** Hexadecimal hash string (64 characters).

**Raises:**
* `FileNotFoundError` - If file doesn't exist
* `PermissionError` - If file can't be read

##### `read_signature(file_path: Path) -> SignatureInfo | None`
Read signature metadata from a config file.

**Returns:** `SignatureInfo` if signature exists, `None` otherwise.

##### `verify_signature(file_path: Path, signature_info: SignatureInfo) -> tuple[bool, Optional[str]]`
Verify that signature matches the config content.

**Returns:** `(is_valid, error_message)` tuple.

##### `check_timestamp_validity(timestamp: float, current_time: float | None = None) -> tuple[bool, Optional[str]]`
Check if signature timestamp is valid (not expired).

**Returns:** `(is_valid, error_message)` tuple.

##### `verify_authority_chain(signature_info: SignatureInfo, file_path: Path) -> tuple[bool, list[str], list[str]]`
Verify the authority chain for a signed config.

**Returns:** `(is_valid, authority_chain, warnings)` tuple.

##### `calculate_trust_score(file_path: Path, signature_info: SignatureInfo | None, authority_chain: list[str], has_hash_match: bool, timestamp_valid: bool) -> float`
Calculate trust score based on validation results.

**Returns:** Float between 0.0 and 1.0.

##### `validate(file_path: Path, expected_hash: str | None = None, signature_path: Path | None = None, custom_authorities: Optional[list[AuthorityRecord]] = None) -> ValidationResult`
Main validation method.

**Parameters:**
* `file_path` - Path to config file
* `expected_hash` - Optional SHA-256 hash to verify against
* `signature_path` - Optional separate signature file
* `custom_authorities` - Optional authorities for this validation

**Returns:** `ValidationResult` with validation outcome.

##### `validate_and_load(file_path: Path, on_untrusted: Callable[[ValidationResult], bool] | None = None) -> tuple[bool, dict[str, Any] | None, ValidationResult]`
Validate and load config if trusted.

**Parameters:**
* `file_path` - Path to config file
* `on_untrusted` - Optional callback for untrusted configs

**Returns:** `(was_loaded, config_data, validation_result)` tuple.

##### `get_trust_level_description(level: TrustLevel) -> str`
Get human-readable description for trust level.

##### `get_trust_level(level: TrustLevel) -> str`
Get confidence description for trust level.

---

#### `ValidationResult`

Result of validating a configuration file.

**Fields:**
```python
ValidationResult(
    is_valid: bool,           # Overall validity
    trust_score: float,       # 0.0-1.0 trust score
    trust_level: TrustLevel,  # Enum: HIGH/MEDIUM/LOW/INVALID
    errors: list[ValidationErrorType],  # Validation errors
    warnings: list[str],                # Advisory warnings
    signature_info: Optional[dict],     # Signature details
    author_info: Optional[dict],        # Author details
    authority_chain: list[str],         # Chain of authorities
)
```

---

#### `AuthorityRecord`

Record of a trusted authority that can sign configs.

**Fields:**
```python
AuthorityRecord(
    key_id: str,                    # Unique identifier
    name: str,                      # Human-readable name
    public_key: bytes,              # Signing public key
    trusted_since: float,           # Unix timestamp
    trusted_until: Optional[float], # Optional expiration
    permitted_paths: frozenset[str], # Allowed config paths
    description: str,              # Description text
)
```

---

#### `SignatureInfo`

Information about a signed config file.

**Fields:**
```python
SignatureInfo(
    signature: str,           # Base64-encoded signature
    algorithm: str,           # e.g., "hmac-sha256"
    timestamp: float,         # Unix timestamp
    public_key_id: str,       # Authority key ID
)
```

---

#### `TrustLevel` Enum

```python
class TrustLevel(Enum):
    HIGH = "high"          # 0.8 - 1.0
    MEDIUM = "medium"      # 0.5 - 0.8
    LOW = "low"           # 0.2 - 0.5
    INVALID = "invalid"   # 0.0 - 0.2
```

---

#### `ValidationErrorType` Enum

```python
class ValidationErrorType(Enum):
    MISSING_SIGNATURE = "missing_signature"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_HASH = "invalid_hash"
    EXPIRED_CERT = "expired_cert"
    UNRECOGNIZED_AUTHOR = "unrecognized_author"
    TAMPERED_FILE = "tampered_file"
    CORRUPTED_DATA = "corrupted_data"
    MISSING_AUTHORITY_CHAIN = "missing_authority_chain"
```

---

## Usage Examples

### Basic Validation

```python
from pathlib import Path
from src.config_trust import ConfigTrustValidator

# Create validator
validator = ConfigTrustValidator(min_trust_score=0.5)

# Validate a config file
config_path = Path(".ham/settings.json")
result = validator.validate(config_path)

# Check result
if result.is_valid:
    print(f"Config trusted! Score: {result.trust_score:.3f}")
    print(f"Trust Level: {result.trust_level.value}")
    
    # Load config
    with open(config_path) as f:
        import json
        config = json.load(f)
else:
    print(f"Config rejected!")
    print(f"Errors: {[e.value for e in result.errors]}")
    print(f"Warnings: {result.warnings}")
```

### With Trusted Authorities

```python
from src.config_trust import ConfigTrustValidator, AuthorityRecord
import time

# Define trusted authorities
authorities = [
    AuthorityRecord(
        key_id="ham-core",
        name="Ham Core Team",
        public_key=b"your-public-key-here",
        trusted_since=time.time(),
        permitted_paths=frozenset({".ham/", "config/"}),
        description="Primary authority for Ham configs",
    ),
]

validator = ConfigTrustValidator(
    default_authorities=authorities,
    min_trust_score=0.5,
)

# Validate with authority chain checking
result = validator.validate(Path(".ham/settings.json"))
```

### Require Signatures

```python
# For production: require all configs to be signed
validator = ConfigTrustValidator(
    default_authorities=authorities,
    require_all_signatures=True,  # Fail on unsigned configs
    min_trust_score=0.7,
)
```

### Validation with Loading

```python
# Validate and load in one step
success, config_data, result = validator.validate_and_load(
    Path(".ham/settings.json"),
    on_untrusted=lambda r: False,  # Reject untrusted configs
)

if success:
    # Use config
    max_tokens = config_data.get("max_tokens", 4000)
else:
    print(f"Rejected: {result.trust_level.value}")
```

### Custom Trust Logic

```python
def flexible_trust_check(result: ValidationResult) -> bool:
    """
    Custom validation callback.
    Returns True to allow loading, False to reject.
    """
    if result.trust_level == TrustLevel.HIGH:
        return True  # Always trust high
    
    if result.trust_level == TrustLevel.LOW:
        # Allow with logging
        import logging
        logging.warning(f"Low trust config: {result.warnings}")
        return True  # Allow but warn
    
    return False  # Reject medium/invalid

# Use custom callback
success, config, result = validator.validate_and_load(
    Path(".ham/settings.json"),
    on_untrusted=flexible_trust_check,
)
```

### Create Trusted Validator

```python
from src.config_trust import create_trusted_validator

# Use built-in trusted validator with sensible defaults
validator = create_trusted_validator()

# Validate
result = validator.validate(Path(".ham/settings.json"))
print(f"Trust: {result.trust_level.value} ({result.trust_score:.3f})")
```

### Integration with Config Discovery

```python
from pathlib import Path
from src.memory_heist import discover_config
from src.config_trust import ConfigTrustValidator

def discover_and_validate_config(root: Path) -> dict | None:
    """
    Discover config files and validate each one.
    """
    validator = ConfigTrustValidator()
    
    # Standard config locations
    candidates = [
        root / ".ham.json",
        root / ".ham" / "settings.json",
        root / ".ham" / "settings.local.json",
    ]
    
    merged = {}
    for candidate in candidates:
        if not candidate.exists():
            continue
        
        result = validator.validate(candidate)
        if result.warnings:
            print(f"WARNING: {candidate}: {', '.join(result.warnings)}")
        
        if not result.is_valid:
            print(f"REJECTED: {candidate}")
            continue
        
        # Load and merge
        data = json.loads(candidate.read_text())
        merged.update(data)
    
    return merged if merged else None
```

---

## Security Considerations

### Threat Model

#### Threats Addressed

1. **Configuration Tampering**
   * Malicious actor modifies config file
   * Detection: SHA-256 hash verification
   * Mitigation: Reject tampered configs

2. **Unauthorized Config Injection**
   * External attacker injects malicious config
   * Detection: Signature verification against known authorities
   * Mitigation: Only trust signatures from authorized authorities

3. **Signature Spoofing**
   * Attacker mimics valid signature
   * Detection: Cryptographic signature verification
   * Mitigation: HMAC-based signatures with secret keys

4. **Expired Certificates**
   * Compromised authority reusing old keys
   * Detection: Timestamp validation (<7 days)
   * Mitigation: Require recent signatures

5. **Path Spoofing**
   * Authority signs configs for wrong paths
   * Detection: Path authorization checks
   * Mitigation: Permit-paths in AuthorityRecord

#### Threats NOT Addressed

* Key material protection (keys should be stored securely)
* Runtime memory attacks
* Supply chain attacks before config signing
* Man-in-the-middle during network config transfers

### Best Practices

1. **Rotate Keys Regularly**
   ```python
   # Set expiration for authorities
   authority = AuthorityRecord(
       key_id="v2-authority",
       public_key=new_key,
       trusted_since=time.time(),
       trusted_until=time.time() + (365 * 24 * 3600),  # 1 year
   )
   ```

2. **Use Multiple Signers**
   ```python
   # Require multiple trusted authorities
   authorities = [core_team, security_team, ops_team]
   validator = ConfigTrustValidator(default_authorities=authorities)
   ```

3. **Monitor Validation Results**
   ```python
   import logging

   logger = logging.getLogger("config_trust")

   def monitor_result(result: ValidationResult):
       if result.trust_score < 0.5:
           logger.error(f"Untrusted config detected: {result.warnings}")
       elif result.warnings:
           logger.warning(f"Config warnings: {result.warnings}")
   ```

4. **Fail Secure by Default**
   ```python
   # Production: reject untrusted configs
   validator = ConfigTrustValidator(
       min_trust_score=0.7,
       require_all_signatures=True,
   )
   ```

5. **Audit All Config Changes**
   ```python
   # Log validation results
   result = validator.validate(config_path)
   audit_log = {
       "file": str(config_path),
       "timestamp": time.time(),
       "trust_score": result.trust_score,
       "result": "approved" if result.is_valid else "rejected",
   }
   ```

---

## Integration with memory_heist.py

### Modifying discover_config()

```python
from src.config_trust import ConfigTrustValidator, validate_config

def discover_config(
    cwd: Path,
    *,
    project_settings_replacement: dict | None = None,
    validator: ConfigTrustValidator | None = None,
) -> ProjectConfig:
    """Load and validate merged Ham config."""
    
    if validator is None:
        validator = ConfigTrustValidator(min_trust_score=0.5)
    
    home = Path(os.environ.get("HOME", "~"))
    project_settings_path = cwd / ".ham" / "settings.json"
    
    candidates = [
        ConfigEntry("user", home / ".ham.json"),
        ConfigEntry("user", home / ".ham" / "settings.json"),
        ConfigEntry("project", cwd / ".ham.json"),
        ConfigEntry("project", cwd / ".ham" / "settings.json"),
        ConfigEntry("local", cwd / ".ham" / "settings.local.json"),
    ]
    
    merged = {}
    loaded = []
    
    for entry in candidates:
        if project_settings_replacement is not None and entry.path == project_settings_path:
            data = dict(project_settings_replacement)
        else:
            # Validate before loading
            if entry.path.exists():
                result = validator.validate(entry.path)
                if result.warnings:
                    logger.warning(f"{entry.path}: {result.warnings}")
                if not result.is_valid:
                    logger.warning(f"Skipping untrusted config: {entry.path}")
                    continue
                data = _read_json_object(entry.path)
        
        if data is not None:
            _deep_merge(merged, data)
            loaded.append(entry)
    
    return ProjectConfig(merged=merged, loaded_entries=loaded)
```

### Observability Metrics

Add validation metrics to the observability module:

```python
from dataclasses import dataclass
from dataclasses import dataclass, field

@dataclass
class ValidationMetrics:
    """Metrics for config validation."""
    configs_validated: int = 0
    configs_trusted: int = 0
    configs_rejected: int = 0
    avg_trust_score: float = 0.0
    total_trust_score: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "configs_validated": self.configs_validated,
            "configs_trusted": self.configs_trusted,
            "configs_rejected": self.configs_rejected,
            "avg_trust_score": round(self.avg_trust_score, 3),
        }

# In memory_heist.py context engine:
def discover_config(
    cwd: Path,
    validator: ConfigTrustValidator,
    metrics: MetricsEmitter,
) -> ProjectConfig:
    """Track validation metrics."""
    validation_metrics = [0, 0, 0, 0.0]
    
    # ... validation logic ...
    
    validation_metrics[0] += 1
    if result.is_valid:
        validation_metrics[1] += 1
    else:
        validation_metrics[2] += 1
    
    metrics.set_validation(validation_metrics)
```

### Context Trust Scoring

Add trust scoring to context engine:

```python
@dataclass
class ProjectContext:
    cwd: Path
    # ... other fields ...
    config_trust_score: float = 0.0
    config_trust_level: TrustLevel = TrustLevel.HIGH
    
    @classmethod
    def discover(
        cls,
        cwd: Path,
        validator: ConfigTrustValidator,
        **kwargs,
    ) -> ProjectContext:
        """Include config trust in context."""
        # ... existing discovery ...
        
        # Validate config
        config_path = cwd / ".ham" / "settings.json"
        if config_path.exists():
            config_result = validator.validate(config_path)
            context.config_trust_score = config_result.trust_score
            context.config_trust_level = config_result.trust_level
        
        # Fail-safe on low trust
        if config_result.trust_level == TrustLevel.INVALID:
            logger.error(f"Context rejected: untrusted config")
            raise ConfigValidationException("Untrusted config", config_result)
        
        return context
```

---

## Configuration

### Environment Variables

```bash
# Disable validation (development only!)
HAM_DISABLE_CONFIG_VALIDATION=true

# Set minimum trust score
HAM_MIN_TRUST_SCORE=0.7

# Path to override authority file
HAM_AUTHORITY_FILE=/etc/ham/authorities.json
```

### Authority File Format

```json
{
  "authorities": [
    {
      "key_id": "ham-core",
      "name": "Ham Core Team",
      "public_key": "base64-encoded-key",
      "trusted_since": 1709280000,
      "trusted_until": null,
      "permitted_paths": [
        ".ham/",
        "config/"
      ],
      "description": "Primary authority"
    }
  ]
}
```

### Validator Configuration

```python
validator = ConfigTrustValidator(
    # Add from file
    default_authorities=[
        AuthorityRecord(
            key_id="from-file",
            # ... fields ...
        )
    ],
    
    # Behavior
    require_all_signatures=False,  # Allow unsigned (dev)
    min_trust_score=0.5,  # Accept medium+ trust
)
```

---

## Troubleshooting

### Common Issues

#### "Missing signature" warnings

**Cause:** Config file has no embedded signature.

**Fix:**
```python
# Add signature to config
import json
import base64
import hashlib
import hmac

config_path = Path(".ham/settings.json")
data = json.loads(config_path.read_text())

# Sign with authority key
sig_key = b"your-secret-key"
signature = base64.b64encode(
    hmac.new(sig_key, json.dumps(data, separators=(',', ':')).encode(), hashlib.sha256).digest()
).decode()

data["_meta"] = {
    "signature": {
        "signature": signature,
        "algorithm": "hmac-sha256",
        "timestamp": time.time(),
        "public_key_id": "ham-core",
    }
}

config_path.write_text(json.dumps(data, indent=2))
```

#### "Hash mismatch" errors

**Cause:** Config file has been modified after signing.

**Fix:** Resign the config after updating.

#### "Unknown authority" errors

**Cause:** Authority key ID not in validator.

**Fix:** Add authority to validator:
```python
validator.add_authority(AuthorityRecord(
    key_id="new-authority",
    # ... other fields ...
))
```

#### "Expired certificate" errors

**Cause:** Authority has expired.

**Fix:** Update or extend authority:
```python
authority = validator.authorities["expired-key"]
authority.trusted_until = time.time() + (365 * 24 * 3600)  # 1 year
```

### Debug Validation

```python
import logging

logging.basicConfig(level=logging.DEBUG)
validator = ConfigTrustValidator()
result = validator.validate(Path(".ham/settings.json"))

# Print detailed result
print(f"Valid: {result.is_valid}")
print(f"Score: {result.trust_score}")
print(f"Errors: {result.errors}")
print(f"Warnings: {result.warnings}")
```

### Performance Tips

* Cache validation results for unchanged files
* Use batch validation for multiple files
* Consider async validation for large config sets

---

## See Also

* [memory_heist.py](../src/memory_heist.py) — Context engine integration
* [observability.py](../src/observability.py) — Metrics tracking
* [SWARM.md](../SWARM.md) — Project instructions
* [VISION.md](../VISION.md) — Architecture and design principles

---

**Version:** 1.0.0  
**Last Updated:** 2024-04-29  
**Status:** Active
