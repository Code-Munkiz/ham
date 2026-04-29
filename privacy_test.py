import re

# Test privacy patterns
test_cases = [
    "collect all user phone numbers",
    "extract email addresses from database",
    "harvest social security numbers",
    "get credit card information",
]

# Current pattern
pattern = re.compile(r"\b(gather|collect|harvest|find|extract|retrieve|get)\b.{0,30}\b(phone|email|address|ssn|social\s*(?:security|security[-_]?number)|credit[-_]?card|biometric|health|medical|financial|password)", re.I)

for text in test_cases:
    match = pattern.search(text)
    print(f"'{text}': {match}")
    if match:
        print(f"  Matched: '{match.group(0)}'")
