import random
import string

ALPHABET = string.ascii_lowercase + string.digits
CODE_LENGTH = 6


def new_code(rng: random.Random) -> str:
    """Return a random code.

    Args:
        rng: Randomness source, injected so tests are deterministic.

    Returns:
        CODE_LENGTH characters from ALPHABET.
    """
    return "".join(rng.choices(ALPHABET, k=CODE_LENGTH))


def is_code(value: str) -> bool:
    """Check that a path segment has the shape new_code produces.

    Args:
        value: Candidate code.

    Returns:
        True if it is CODE_LENGTH characters, all from ALPHABET.
    """
    return len(value) == CODE_LENGTH and all(c in ALPHABET for c in value)
