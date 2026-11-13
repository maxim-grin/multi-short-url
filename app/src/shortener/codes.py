import random
import string

ALPHABET = string.ascii_lowercase + string.digits
CODE_LENGTH = 6


def new_code(rng: random.Random) -> str:
    """Random code; rng is injected so tests are deterministic."""
    return "".join(rng.choices(ALPHABET, k=CODE_LENGTH))


def is_code(value: str) -> bool:
    """True if value has the exact shape new_code produces."""
    return len(value) == CODE_LENGTH and all(c in ALPHABET for c in value)
