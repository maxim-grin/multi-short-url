import random

from shortener.codes import ALPHABET, CODE_LENGTH, is_code, new_code


def test_new_code_shape():
    code = new_code(random.Random(1))
    assert len(code) == CODE_LENGTH == 6
    assert set(code) <= set(ALPHABET)


def test_new_code_seeded_agree():
    assert new_code(random.Random(7)) == new_code(random.Random(7))


def test_is_code_accepts():
    assert is_code("k3fq9x")


def test_is_code_rejects():
    for bad in ["K3fq9x", "k3fq9", "k3fq9xx", "k3f-9x", ""]:
        assert not is_code(bad)
