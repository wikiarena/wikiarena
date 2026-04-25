from wikiarena.protocol import stable_sha256


def test_stable_sha256_is_key_order_insensitive() -> None:
    first = {
        "a": 1,
        "b": 2,
    }
    second = {
        "b": 2,
        "a": 1,
    }

    assert stable_sha256(first) == stable_sha256(second)
