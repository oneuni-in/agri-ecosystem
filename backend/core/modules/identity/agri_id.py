"""AG-XXXXXXX fallback public identity (D06.C).

Encodes a value drawn from the atomic Postgres sequence identity.agri_id_seq
as 7 Crockford base32 characters. The encoding is injective and the sequence
never repeats, so collisions are impossible by construction - no retry loop,
no uniqueness probe. Capacity is 32**7 (~34.4 billion ids).
"""

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
AGRI_ID_CODE_LENGTH = 7
AGRI_ID_CAPACITY = 32**AGRI_ID_CODE_LENGTH
AGRI_ID_SEQUENCE = "identity.agri_id_seq"


def encode_crockford(value: int) -> str:
    if not 0 <= value < AGRI_ID_CAPACITY:
        raise ValueError(f"value must be in [0, {AGRI_ID_CAPACITY}), got {value}")
    chars = []
    for _ in range(AGRI_ID_CODE_LENGTH):
        value, remainder = divmod(value, 32)
        chars.append(CROCKFORD_ALPHABET[remainder])
    return "".join(reversed(chars))


def format_agri_id(sequence_value: int) -> str:
    return f"AG-{encode_crockford(sequence_value)}"
