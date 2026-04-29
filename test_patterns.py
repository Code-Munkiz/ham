import re

# Test patterns with normalization (lowercase + single spaces)
text = "send me your api key"

# Our fixed pattern
pattern = re.compile(r"\b(send|share|disclose|expose|dump|leak|reveal|provide|give|extract|get)\b.{0,30}\b(api\s*(?:[-_]\s*)?key|secret\s*(?:[-_]\s*)?key|access\s*(?:[-_]\s*)?token|bearer|(?:private\s*)?key|credential)", re.I)
match = pattern.search(text)
print(f"'{text}': {match}")
if match:
    print(f"  Matched: '{match.group(0)}'")

# "Share your access token"
text2 = "share your access token"
match2 = pattern.search(text2)
print(f"\n'{text2}': {match2}")
if match2:
    print(f"  Matched: '{match2.group(0)}'")

# "provide the bearer token"
text3 = "provide the bearer token"
match3 = pattern.search(text3)
print(f"\n'{text3}': {match3}")
if match3:
    print(f"  Matched: '{match3.group(0)}'")

# "extract api-key from config"
text4 = "extract api-key from config"
match4 = pattern.search(text4)
print(f"\n'{text4}': {match4}")
if match4:
    print(f"  Matched: '{match4.group(0)}'")
