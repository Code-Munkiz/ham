"""
budget_parser.py — Centralized budget parsing and validation for memory_heist.

Provides type-safe coercion and validation for:
- architect_instruction_chars
- commander_instruction_chars
- critic_instruction_chars
- All MAX_* budget constants (MAX_*_CHARS)
- Session compaction thresholds

Prevents truncation bugs by enforcing positive integer constraints and range
validation with clear error messages.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class BudgetConfig:
    """Configuration for instruction and diff budgets per role."""
    architect_instruction_chars: int
    commander_instruction_chars: int
    critic_instruction_chars: int
    architect_diff_chars: int
    commander_diff_chars: int
    critic_diff_chars: int

    @classmethod
    def defaults(cls) -> "BudgetConfig":
        """Return default budget configuration."""
        return cls(
            architect_instruction_chars=16_000,
            commander_instruction_chars=4_000,
            critic_instruction_chars=8_000,
            architect_diff_chars=8_000,
            commander_diff_chars=2_000,
            critic_diff_chars=8_000,
        )


class BudgetParseError(ValueError):
    """Raised when a budget value fails validation."""
    pass


def _parse_int_coerce(raw: Any, default: int, field_name: str) -> int:
    """
    Coerce a raw value to a positive integer.
    
    Args:
        raw: The raw value (string, int, float, bool, or None)
        default: The default value to use if coercion fails
        field_name: Name of the field for error messages
        
    Returns:
        A positive integer
        
    Raises:
        BudgetParseError: If the value cannot be coerced or is invalid
    """
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        if raw <= 0:
            raise BudgetParseError(
                f"{field_name}: value {raw} is not positive, using default {default}"
            )
        return raw
    if isinstance(raw, float):
        if raw <= 0:
            raise BudgetParseError(
                f"{field_name}: value {raw} is not positive, using default {default}"
            )
        return int(raw)
    if isinstance(raw, str):
        stripped = raw.strip()
        int_match = re.match(r"^\s*(-?\d+)\s*$", stripped)
        if int_match:
            val = int(int_match.group(1))
            if val <= 0:
                raise BudgetParseError(
                    f"{field_name}: value '{raw}' converts to {val}, which is not positive"
                )
            return val
        raise BudgetParseError(
            f"{field_name}: cannot parse '{raw}' as integer"
        )
    if raw is None:
        return default
    raise BudgetParseError(
        f"{field_name}: unexpected type {type(raw).__name__!r}, expected int, str, or None"
    )


def parse_budget_value(raw: Any, default: int) -> int:
    """
    Parse and coerce a budget value to a positive integer.
    
    This is the public API for parsing budget values. It handles:
    - Strings with optional surrounding whitespace (e.g., " 12345  ")
    - Integers and floats (floats are truncated to int)
    - Booleans (return default, treated as invalid)
    - None (return default)
    - Invalid types (raise BudgetParseError)
    
    Args:
        raw: The raw value to parse
        default: The default value to use if parsing fails
        
    Returns:
        A positive integer
        
    Raises:
        BudgetParseError: If the value cannot be coerced to a positive int
    """
    return _parse_int_coerce(raw, default, "budget_value")


def parse_role_budgets(
    raw_config: dict[str, Any],
    *,
    fallback_budget: BudgetConfig | None = None,
) -> BudgetConfig:
    """
    Parse role-specific budgets from a config dict.
    
    Args:
        raw_config: The config dict from project configuration
        fallback_budget: The fallback BudgetConfig to use if fields are missing
        
    Returns:
        A BudgetConfig instance with parsed values
        
    Raises:
        BudgetParseError: If any budget value fails validation
    """
    fallback = fallback_budget or BudgetConfig.defaults()
    
    # Extract memory_heist section if present
    memory_heist_section = raw_config.get("memory_heist", {})
    if not isinstance(memory_heist_section, dict):
        memory_heist_section = {}
    
    def get_budget(key: str, default: int) -> int:
        # First check memory_heist section, then top-level config
        cached_key = key.replace("_instruction_chars", "_cache_token")
        mh_value = memory_heist_section.get(cached_key)
        if mh_value is not None:
            return _parse_int_coerce(mh_value, default, key)
        return _parse_int_coerce(
            raw_config.get(key, default),
            default,
            key
        )
    
    return BudgetConfig(
        architect_instruction_chars=get_budget("architect_instruction_chars", fallback.architect_instruction_chars),
        commander_instruction_chars=get_budget("commander_instruction_chars", fallback.commander_instruction_chars),
        critic_instruction_chars=get_budget("critic_instruction_chars", fallback.critic_instruction_chars),
        architect_diff_chars=_parse_int_coerce(
            memory_heist_section.get("architect_diff_chars", fallback.architect_diff_chars),
            fallback.architect_diff_chars,
            "architect_diff_chars"
        ),
        commander_diff_chars=_parse_int_coerce(
            memory_heist_section.get("commander_diff_chars", fallback.commander_diff_chars),
            fallback.commander_diff_chars,
            "commander_diff_chars"
        ),
        critic_diff_chars=_parse_int_coerce(
            memory_heist_section.get("critic_diff_chars", fallback.critic_diff_chars),
            fallback.critic_diff_chars,
            "critic_diff_chars"
        ),
    )


def coerce_max_chars(value: Any, default: int, min_val: int = 0, max_val: int | None = None) -> int:
    """
    Coerce a MAX_* budget constant with range validation.
    
    Args:
        value: The raw value to coerce
        default: Default value if coercion fails
        min_val: Minimum allowed value
        max_val: Maximum allowed value (optional)
        
    Returns:
        A validated integer within the specified range
        
    Raises:
        BudgetParseError: If the value is out of range
    """
    parsed = _parse_int_coerce(value, default, "max_chars")
    if parsed < min_val:
        raise BudgetParseError(
            f"max_chars: value {parsed} is below minimum {min_val}"
        )
    if max_val is not None and parsed > max_val:
        raise BudgetParseError(
            f"max_chars: value {parsed} exceeds maximum {max_val}"
        )
    return parsed
