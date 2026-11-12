import random
import string

ALPHABET = string.ascii_lowercase + string.digits
CODE_LENGTH = 6


def new_code(rng: random.Random) -> str:
    return "".join(rng.choices(ALPHABET, k=CODE_LENGTH))


def is_code(value: str) -> bool:
    return len(value) == CODE_LENGTH and all(c in ALPHABET for c in value)
