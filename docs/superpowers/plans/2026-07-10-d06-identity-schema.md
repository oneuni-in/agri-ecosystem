# D06 Identity Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** First real module: `identity` schema (12 tables), pure handle/AG-fallback/phone modules, a structural serialization guard, RBAC seed migration, and a service-layer skeleton — no HTTP.

**Architecture:** Everything rides the D03 machinery: hand-written Alembic migrations built from `shared/migrations.py` helpers, ORM models on `shared/db.py` mixins (UUIDv7 PK, UTC timestamps, soft-delete), one linear revision chain (`0007` tables, `0008` seeds). Pure logic (handles, Crockford encoder, phone) lives in dependency-free modules with exhaustive unit tests. The Pydantic guard makes UUID/phone exposure a class-definition-time `TypeError`, not a review convention.

**Tech Stack:** Python 3.12, SQLAlchemy 2 async, Alembic, Pydantic v2, pytest (asyncio auto mode), Postgres via compose on host port **55432**.

## Global Constraints

- Branch `feat/d06-identity-schema` from `dev`; conventional commits; PR targets `dev`, never `main`.
- All work under `backend/core`; run all commands from `backend\core` with `.\.venv\Scripts\python`.
- No HTTP endpoints, no auth/JWT logic, no profile-completion scoring logic (later specs).
- No cross-module imports (import-linter contract); `modules.identity` may import `shared` and stdlib only.
- `otp_requests` stores a code **hash** column only — never a plaintext code column.
- Internal UUID and phone must be unexposable **by construction** (guard + failing-class test).
- Every migration has a filled `-- THREAT/NOTES:` block (test gate) and downgrades cleanly (CI `migrate_check`).
- OFFSET is banned repo-wide (test gate); no new list queries here anyway.
- Never run `scripts/migrate_check.py` without `ALEMBIC_DATABASE_URL` pointing at a throwaway DB — it downgrades to base and **wipes the target database**.
- Confirmed assumptions (from spec): phone is E.164 with +91 default for bare 10-digit Indian mobiles; `profiles.interests` is a JSONB string array.
- Deliberately deferred: dropping `_demo_all_mixins` (0005 said "dropped once the first real module table exists"). `tests/test_demo_migration.py` is the lockstep gate for the **full** mixin set including `moderation_status`, and no identity table carries UGC moderation. Drop it when the first UGC-bearing table lands (content module). State this in the PR description.

---

### Task 1: Branch + phone normalization module

**Files:**
- Create: `backend/core/modules/identity/phone.py`
- Test: `backend/core/tests/test_identity_phone.py`

**Interfaces:**
- Consumes: nothing (pure stdlib).
- Produces: `normalize_phone(raw: str) -> str` (returns E.164 like `"+919876543210"`, raises `PhoneError`), `PhoneError(ValueError)`. Task 8's service calls `normalize_phone`.

- [ ] **Step 1: Create the branch**

```powershell
git -C d:\agri-ecosystem checkout dev; git -C d:\agri-ecosystem pull; git -C d:\agri-ecosystem checkout -b feat/d06-identity-schema
```

- [ ] **Step 2: Write the failing tests**

Create `backend/core/tests/test_identity_phone.py`:

```python
"""E.164 normalization: +91 default for bare Indian mobiles, strict otherwise."""

import pytest

from modules.identity.phone import PhoneError, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9876543210", "+919876543210"),  # bare Indian mobile -> +91 default
        ("6000000000", "+916000000000"),  # 6-9 are valid first digits
        ("98765 43210", "+919876543210"),  # separators stripped
        ("98765-43210", "+919876543210"),
        ("(98765)43210", "+919876543210"),
        (" +919876543210 ", "+919876543210"),  # already E.164, whitespace trimmed
        ("+14155552671", "+14155552671"),  # non-Indian E.164 passes through
        ("+1 415 555 2671", "+14155552671"),
    ],
)
def test_normalizes_to_e164(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "12345",  # too short
        "5876543210",  # 10 digits but not a mobile prefix (6-9)
        "98765432100",  # 11 bare digits: ambiguous, rejected
        "+0123456789",  # E.164 cannot start +0
        "+1234",  # too short for E.164 body (needs 8-15 digits total)
        "+123456789012345678",  # too long
        "abcdefghij",
        "98765x3210",
    ],
)
def test_rejects_unnormalizable(raw: str) -> None:
    with pytest.raises(PhoneError):
        normalize_phone(raw)


def test_error_message_never_echoes_the_number() -> None:
    """Exceptions get logged; the raw phone (PII) must not ride along."""
    with pytest.raises(PhoneError) as excinfo:
        normalize_phone("5876543210")
    assert "5876543210" not in str(excinfo.value)
```

- [ ] **Step 3: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_phone.py -v
```

Expected: FAIL / collection error with `ModuleNotFoundError: No module named 'modules.identity.phone'`.

- [ ] **Step 4: Write the implementation**

Create `backend/core/modules/identity/phone.py`:

```python
"""Pure E.164 phone normalization (D06 confirmed assumption: +91 default).

Bare 10-digit Indian mobile numbers (first digit 6-9) get the +91 prefix;
anything else must already be valid E.164. Error messages never include the
input value - phone numbers are PII and exceptions end up in logs.
"""

import re

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
_SEPARATORS_RE = re.compile(r"[\s\-()]")


class PhoneError(ValueError):
    """The input cannot be normalized to E.164."""


def normalize_phone(raw: str) -> str:
    cleaned = _SEPARATORS_RE.sub("", raw.strip())
    if _INDIAN_MOBILE_RE.fullmatch(cleaned):
        return f"+91{cleaned}"
    if E164_RE.fullmatch(cleaned):
        return cleaned
    raise PhoneError("phone number is not E.164 and not a bare Indian mobile number")
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_phone.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/core/modules/identity/phone.py backend/core/tests/test_identity_phone.py
git commit -m "feat(d06): E.164 phone normalization with +91 default"
```

---

### Task 2: AG-XXXXXXX Crockford fallback generator

**Files:**
- Create: `backend/core/modules/identity/agri_id.py`
- Test: `backend/core/tests/test_identity_agri_id.py`

**Interfaces:**
- Consumes: nothing (pure stdlib).
- Produces: `encode_crockford(value: int) -> str` (7 chars), `format_agri_id(sequence_value: int) -> str` (returns `"AG-XXXXXXX"`), constants `CROCKFORD_ALPHABET: str`, `AGRI_ID_CODE_LENGTH = 7`, `AGRI_ID_CAPACITY = 32**7`, `AGRI_ID_SEQUENCE = "identity.agri_id_seq"`. Task 8's service calls `format_agri_id` on `nextval(AGRI_ID_SEQUENCE)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/core/tests/test_identity_agri_id.py`:

```python
"""AG-XXXXXXX fallback: injective Crockford base32 over an atomic sequence."""

import re

import pytest

from modules.identity.agri_id import (
    AGRI_ID_CAPACITY,
    AGRI_ID_CODE_LENGTH,
    CROCKFORD_ALPHABET,
    encode_crockford,
    format_agri_id,
)


def test_alphabet_is_crockford() -> None:
    """32 symbols; ambiguous I, L, O, U are excluded by Crockford's design."""
    assert len(CROCKFORD_ALPHABET) == 32
    assert len(set(CROCKFORD_ALPHABET)) == 32
    for ambiguous in "ILOU":
        assert ambiguous not in CROCKFORD_ALPHABET


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0000000"),
        (1, "0000001"),
        (31, "000000Z"),
        (32, "0000010"),
        (AGRI_ID_CAPACITY - 1, "ZZZZZZZ"),
    ],
)
def test_encodes_known_values(value: int, expected: str) -> None:
    assert encode_crockford(value) == expected


def test_always_seven_chars_from_the_alphabet() -> None:
    for value in (0, 1, 12345, AGRI_ID_CAPACITY - 1):
        code = encode_crockford(value)
        assert len(code) == AGRI_ID_CODE_LENGTH
        assert set(code) <= set(CROCKFORD_ALPHABET)


def test_injective_over_sample_range() -> None:
    """Distinct inputs -> distinct codes: with the atomic sequence as the only
    input source, collisions are impossible by construction."""
    sample = range(0, 200_000, 7)
    codes = {encode_crockford(value) for value in sample}
    assert len(codes) == len(list(sample))


@pytest.mark.parametrize("value", [-1, AGRI_ID_CAPACITY, AGRI_ID_CAPACITY + 1])
def test_out_of_range_raises(value: int) -> None:
    with pytest.raises(ValueError):
        encode_crockford(value)


def test_format_agri_id() -> None:
    assert format_agri_id(0) == "AG-0000000"
    assert re.fullmatch(r"AG-[0-9A-HJKMNP-TV-Z]{7}", format_agri_id(987654321))


def test_fallback_can_never_be_a_valid_handle() -> None:
    """Uppercase + hyphen means an AG- id can never pass the handle regex,
    so the two public-identity namespaces cannot collide."""
    assert not re.fullmatch(r"[a-z0-9_]{4,20}", format_agri_id(42))
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_agri_id.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'modules.identity.agri_id'`.

- [ ] **Step 3: Write the implementation**

Create `backend/core/modules/identity/agri_id.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_agri_id.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/core/modules/identity/agri_id.py backend/core/tests/test_identity_agri_id.py
git commit -m "feat(d06): AG- fallback generator, Crockford base32 over atomic sequence"
```

---

### Task 3: @handle rules module + reserved-word blocklist file

**Files:**
- Create: `backend/core/modules/identity/reserved_handles.txt`
- Create: `backend/core/modules/identity/handles.py`
- Modify: `backend/core/pyproject.toml` (package-data so the .txt ships in wheels)
- Test: `backend/core/tests/test_identity_handles.py`

**Interfaces:**
- Consumes: nothing (pure stdlib + the data file).
- Produces: `validate_handle(raw: str) -> str` (returns normalized handle or raises `HandleError`), `normalize_handle(raw: str) -> str`, `HandleError(ValueError)` with `.code` attribute (`"invalid_format"` | `"reserved"`), `load_reserved_handles(path: Path) -> frozenset[str]`, `RESERVED_HANDLES: frozenset[str]`, `can_change_handle(agri_id_changed_once: bool) -> bool`, `HANDLE_RE: re.Pattern[str]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/core/tests/test_identity_handles.py`:

```python
"""@handle rules (D06.B): charset/length, reserved blocklist, one free change.

The blocklist exists against handle-squatting of official names (threat
model); the extensible file is how new protected names get added without a
code change.
"""

from pathlib import Path

import pytest

from modules.identity.handles import (
    RESERVED_HANDLES,
    HandleError,
    can_change_handle,
    load_reserved_handles,
    normalize_handle,
    validate_handle,
)

SPEC_BLOCKLIST = (
    "admin",
    "agri",
    "milk",
    "organic",
    "official",
    "support",
    "help",
    "root",
    "api",
    "www",
    "aavin",
    "amul",
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ravi", "ravi"),  # 4 chars: minimum
        ("ravi_farm_2026", "ravi_farm_2026"),
        ("a" * 20, "a" * 20),  # 20 chars: maximum
        ("@ravifarm", "ravifarm"),  # leading @ stripped
        ("RaviFarm", "ravifarm"),  # uppercase input normalized down
        (" ravi ", "ravi"),  # whitespace trimmed
        ("1234", "1234"),  # digits-only is legal
        ("_agri_", "_agri_"),  # underscore placement unrestricted
    ],
)
def test_valid_handles_normalize(raw: str, expected: str) -> None:
    assert validate_handle(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "abc",  # 3 chars: too short
        "a" * 21,  # 21 chars: too long
        "ravi-farm",  # hyphen
        "ravi farm",  # inner space
        "ravi.farm",  # dot
        "ரவி_farm",  # non-ascii
        "ravi🌾",  # emoji
        "AG-0000042",  # fallback-shaped: hyphen keeps namespaces disjoint
    ],
)
def test_invalid_format_rejected(raw: str) -> None:
    with pytest.raises(HandleError) as excinfo:
        validate_handle(raw)
    assert excinfo.value.code == "invalid_format"


@pytest.mark.parametrize("word", SPEC_BLOCKLIST)
def test_every_spec_reserved_word_is_blocked(word: str) -> None:
    with pytest.raises(HandleError) as excinfo:
        validate_handle(word)
    assert excinfo.value.code == "reserved"


@pytest.mark.parametrize("raw", ["Admin", "ADMIN", "@admin", " admin "])
def test_reserved_check_runs_on_the_normalized_form(raw: str) -> None:
    with pytest.raises(HandleError) as excinfo:
        validate_handle(raw)
    assert excinfo.value.code == "reserved"


def test_blocklist_file_contains_the_spec_words() -> None:
    assert set(SPEC_BLOCKLIST) <= RESERVED_HANDLES


def test_blocklist_is_extensible_via_file(tmp_path: Path) -> None:
    extra = tmp_path / "reserved.txt"
    extra.write_text("# comment line\n\nAavinExtra\nnewbrand\n", encoding="utf-8")
    words = load_reserved_handles(extra)
    assert words == frozenset({"aavinextra", "newbrand"})


def test_normalize_handle_is_idempotent() -> None:
    assert normalize_handle(normalize_handle("@RaviFarm")) == "ravifarm"


def test_one_free_change_ever() -> None:
    assert can_change_handle(agri_id_changed_once=False) is True
    assert can_change_handle(agri_id_changed_once=True) is False
```

Design decision the tests encode: the blocklist check runs **before** the format check, so the spec's own reserved words (`api`, `www` are only 3 chars) always report `code == "reserved"` rather than tripping the 4-char floor first.

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_handles.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'modules.identity.handles'`.

- [ ] **Step 3: Write the blocklist file**

Create `backend/core/modules/identity/reserved_handles.txt`:

```text
# Reserved @handles - one per line, lowercase; lines starting with # and
# blank lines are ignored. Extend freely: protects official/brand names
# from handle-squatting (D06 threat model). Loaded by modules/identity/handles.py.
admin
agri
milk
organic
official
support
help
root
api
www
aavin
amul
```

- [ ] **Step 4: Write the implementation**

Create `backend/core/modules/identity/handles.py`:

```python
"""Pure @handle rules (D06.B): lowercase a-z 0-9 underscore, 4-20 chars,
reserved-word blocklist from reserved_handles.txt, one free change ever.

No DB access here - handle uniqueness is the users.agri_id unique constraint,
and the change-once rule is the users.agri_id_changed_once flag; this module
is the single source of truth for what a handle may look like.
"""

import re
from pathlib import Path

HANDLE_RE = re.compile(r"^[a-z0-9_]{4,20}$")
_RESERVED_FILE = Path(__file__).with_name("reserved_handles.txt")


class HandleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_reserved_handles(path: Path = _RESERVED_FILE) -> frozenset[str]:
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if word and not word.startswith("#"):
            words.add(word)
    return frozenset(words)


RESERVED_HANDLES = load_reserved_handles()


def normalize_handle(raw: str) -> str:
    return raw.strip().removeprefix("@").lower()


def validate_handle(raw: str) -> str:
    """Return the normalized handle, or raise HandleError.

    The blocklist runs before the format check so reserved words always
    report code="reserved", even the ones (api, www) that are also too short.
    """
    handle = normalize_handle(raw)
    if handle in RESERVED_HANDLES:
        raise HandleError("reserved", "this handle is reserved")
    if not HANDLE_RE.fullmatch(handle):
        raise HandleError("invalid_format", "handles are 4-20 chars of a-z, 0-9 and _")
    return handle


def can_change_handle(agri_id_changed_once: bool) -> bool:
    """One free change ever; the flag flips on the first change (D06.B)."""
    return not agri_id_changed_once
```

- [ ] **Step 5: Add package-data so the .txt ships with the package**

In `backend/core/pyproject.toml`, after the `[tool.setuptools.packages.find]` block, add:

```toml
[tool.setuptools.package-data]
"modules.identity" = ["*.txt"]
```

- [ ] **Step 6: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_handles.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/core/modules/identity/handles.py backend/core/modules/identity/reserved_handles.txt backend/core/tests/test_identity_handles.py backend/core/pyproject.toml
git commit -m "feat(d06): handle rules with file-extensible reserved blocklist"
```

---

### Task 4: Serialization guard — UUID/phone unexposable by construction

**Files:**
- Create: `backend/core/modules/identity/schemas.py`
- Test: `backend/core/tests/test_identity_schemas.py`

**Interfaces:**
- Consumes: nothing beyond Pydantic.
- Produces: `IdentityPublicSchema(BaseModel)` — the mandatory base for every public identity response model (D07+ will subclass it), `BANNED_FIELD_NAMES: frozenset[str]`. Declaring a subclass with a banned field name or any field whose annotation contains `uuid.UUID` (directly, in generics, unions, or nested models) raises `TypeError` at class-definition time.

- [ ] **Step 1: Write the failing tests**

Create `backend/core/tests/test_identity_schemas.py`:

```python
"""Serialization guard (D06.F): a public identity schema that tries to carry
the internal UUID or phone fails at class DEFINITION, not in review."""

import uuid

import pytest
from pydantic import BaseModel

from modules.identity.schemas import IdentityPublicSchema


def test_clean_public_schema_works() -> None:
    class PublicUser(IdentityPublicSchema):
        agri_id: str
        name: str | None = None

    assert PublicUser(agri_id="AG-0000042").model_dump() == {
        "agri_id": "AG-0000042",
        "name": None,
    }


def test_raw_uuid_field_fails_at_class_definition() -> None:
    with pytest.raises(TypeError, match="uuid"):

        class Leaky(IdentityPublicSchema):
            user_uuid: uuid.UUID


def test_optional_uuid_fails() -> None:
    with pytest.raises(TypeError, match="uuid"):

        class Leaky(IdentityPublicSchema):
            maybe: uuid.UUID | None


def test_uuid_inside_generics_fails() -> None:
    with pytest.raises(TypeError, match="uuid"):

        class Leaky(IdentityPublicSchema):
            ids: list[uuid.UUID]

    with pytest.raises(TypeError, match="uuid"):

        class Leaky2(IdentityPublicSchema):
            mapping: dict[str, uuid.UUID]


def test_uuid_nested_in_another_model_fails() -> None:
    class Inner(BaseModel):
        ref: uuid.UUID

    with pytest.raises(TypeError, match="uuid"):

        class Leaky(IdentityPublicSchema):
            inner: Inner


@pytest.mark.parametrize("banned", ["id", "user_id", "phone", "phone_number"])
def test_banned_field_names_fail_even_as_str(banned: str) -> None:
    with pytest.raises(TypeError, match=banned):
        type(
            "Leaky",
            (IdentityPublicSchema,),
            {"__annotations__": {banned: str}},
        )


def test_deeply_nested_public_models_are_allowed() -> None:
    class InnerOk(BaseModel):
        district: str

    class PublicProfile(IdentityPublicSchema):
        agri_id: str
        location: InnerOk | None = None

    dumped = PublicProfile(agri_id="ravi_farm", location=InnerOk(district="Erode"))
    assert dumped.model_dump()["location"] == {"district": "Erode"}
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_schemas.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'modules.identity.schemas'`.

- [ ] **Step 3: Write the implementation**

Create `backend/core/modules/identity/schemas.py`:

```python
"""Serialization guard (D06.F): the internal user UUID and phone number are
unexposable BY CONSTRUCTION, not by convention.

Every public identity response model must subclass IdentityPublicSchema.
At class-definition time it rejects (a) banned field names and (b) any field
whose annotation contains uuid.UUID - directly, inside generics/unions, or
via a nested Pydantic model. A violation is an import-time TypeError, so it
can never reach code review as a runtime surprise, let alone production.

Threat model: identity-table leakage. The public identity is users.agri_id
(@handle or AG-XXXXXXX); the UUIDv7 PK and phone stay server-side forever.
"""

import typing
import uuid

from pydantic import BaseModel

BANNED_FIELD_NAMES = frozenset({"id", "user_id", "phone", "phone_number"})


def _contains_uuid(annotation: object) -> bool:
    if isinstance(annotation, type):
        if issubclass(annotation, uuid.UUID):
            return True
        if issubclass(annotation, BaseModel):
            return any(
                _contains_uuid(field.annotation)
                for field in annotation.model_fields.values()
            )
        return False
    return any(_contains_uuid(arg) for arg in typing.get_args(annotation))


class IdentityPublicSchema(BaseModel):
    """Base for all public identity response models. Subclassing enforces the guard."""

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        for name, field in cls.model_fields.items():
            if name in BANNED_FIELD_NAMES:
                raise TypeError(
                    f"{cls.__name__}.{name}: '{name}' is banned in public identity "
                    "schemas (identity-table leakage guard); expose agri_id instead"
                )
            if _contains_uuid(field.annotation):
                raise TypeError(
                    f"{cls.__name__}.{name}: uuid.UUID must never appear in a public "
                    "identity schema (identity-table leakage guard)"
                )
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_schemas.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/core/modules/identity/schemas.py backend/core/tests/test_identity_schemas.py
git commit -m "feat(d06): structural serialization guard - UUID/phone unexposable"
```

---

### Task 5: Migration 0007 — identity schema v1 (12 tables, 2 enums, 1 sequence)

**Files:**
- Create: `backend/core/alembic/versions/0007_identity_v1.py`

**Interfaces:**
- Consumes: `shared.migrations.pk_column/timestamp_columns/soft_delete_column`; schema `identity` already exists (revision 0001).
- Produces: tables `identity.users`, `identity.handles_history`, `identity.otp_requests`, `identity.sessions_refresh`, `identity.emails`, `identity.roles`, `identity.permissions`, `identity.role_permissions`, `identity.user_roles`, `identity.profiles`, `identity.addresses`, `identity.preferences`; enums `identity.user_status` (`active/suspended/deleted`), `identity.user_language` (`en/ta/hi`); sequence `identity.agri_id_seq`. Tasks 6–8 build on these exact names.

- [ ] **Step 1: Write the migration**

Create `backend/core/alembic/versions/0007_identity_v1.py`:

```python
"""identity schema v1: users, handle history, OTP, refresh sessions, emails,
RBAC (roles/permissions), profiles, addresses, preferences, AG-id sequence.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-10

"""
# -- THREAT/NOTES:
# downgrade data loss: drops every identity table, both identity enums, and the
#   agri_id sequence - all accounts, sessions and RBAC assignments are destroyed.
#   Acceptable now: pre-launch, no production users exist; after launch a
#   downgrade of this revision is an incident decision, never routine.
# locks: CREATE/DROP TABLE on empty tables, CREATE TYPE/SEQUENCE; negligible.
# rollout: tables ship empty; 0008 seeds the RBAC baseline. No readers or
#   writers until D07+ adds HTTP. otp_requests.code_hash is hash-only by
#   design - there is deliberately no plaintext code column to migrate later.

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _user_status() -> postgresql.ENUM:
    return postgresql.ENUM(
        "active", "suspended", "deleted",
        name="user_status", schema="identity", create_type=False,
    )


def _user_language() -> postgresql.ENUM:
    return postgresql.ENUM(
        "en", "ta", "hi",
        name="user_language", schema="identity", create_type=False,
    )


def _user_fk(*, index: bool = False, unique: bool = False) -> sa.Column[uuid.UUID]:
    return sa.Column(
        "user_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("identity.users.id"),
        nullable=False,
        index=index,
        unique=unique,
    )


def upgrade() -> None:
    bind = op.get_bind()
    sa.Enum("active", "suspended", "deleted", name="user_status", schema="identity").create(
        bind, checkfirst=True
    )
    sa.Enum("en", "ta", "hi", name="user_language", schema="identity").create(
        bind, checkfirst=True
    )
    op.execute("CREATE SEQUENCE identity.agri_id_seq")

    op.create_table(
        "users",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("phone", sa.Text, nullable=False, unique=True),
        sa.Column("phone_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", _user_status(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("agri_id", sa.Text, nullable=False, unique=True),
        sa.Column("agri_id_changed_once", sa.Boolean, server_default=sa.false(), nullable=False),
        schema="identity",
    )
    op.create_table(
        "handles_history",
        pk_column(),
        *timestamp_columns(),
        _user_fk(index=True),
        sa.Column("old_agri_id", sa.Text, nullable=False),
        sa.Column("new_agri_id", sa.Text, nullable=False),
        schema="identity",
    )
    op.create_table(
        "otp_requests",
        pk_column(),
        *timestamp_columns(),
        sa.Column("phone", sa.Text, nullable=False, index=True),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("device_fingerprint", sa.Text, nullable=True),
        schema="identity",
    )
    op.create_table(
        "sessions_refresh",
        pk_column(),
        *timestamp_columns(),
        _user_fk(index=True),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("device_label", sa.Text, nullable=True),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "rotated_from",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.sessions_refresh.id"),
            nullable=True,
        ),
        schema="identity",
    )
    op.create_table(
        "emails",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        _user_fk(index=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_table(
        "roles",
        pk_column(),
        *timestamp_columns(),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        schema="identity",
    )
    op.create_table(
        "permissions",
        pk_column(),
        *timestamp_columns(),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        schema="identity",
    )
    op.create_table(
        "role_permissions",
        pk_column(),
        *timestamp_columns(),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.roles.id"),
            nullable=False,
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.permissions.id"),
            nullable=False,
        ),
        sa.UniqueConstraint("role_id", "permission_id"),
        schema="identity",
    )
    op.create_table(
        "user_roles",
        pk_column(),
        *timestamp_columns(),
        _user_fk(),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.roles.id"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "role_id"),
        schema="identity",
    )
    op.create_table(
        "profiles",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        _user_fk(unique=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("avatar_key", sa.Text, nullable=True),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("district", sa.Text, nullable=True),
        sa.Column("pincode", sa.Text, nullable=True),
        sa.Column(
            "language", _user_language(), server_default=sa.text("'en'"), nullable=False
        ),
        sa.Column(
            "interests", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("completion_score", sa.Integer, server_default=sa.text("0"), nullable=False),
        schema="identity",
    )
    op.create_table(
        "addresses",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        _user_fk(index=True),
        sa.Column("label", sa.Text, nullable=True),
        sa.Column("line1", sa.Text, nullable=False),
        sa.Column("line2", sa.Text, nullable=True),
        sa.Column("district", sa.Text, nullable=True),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("pincode", sa.Text, nullable=True),
        sa.Column("is_default", sa.Boolean, server_default=sa.false(), nullable=False),
        schema="identity",
    )
    op.create_table(
        "preferences",
        pk_column(),
        *timestamp_columns(),
        _user_fk(unique=True),
        sa.Column(
            "notifications", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "privacy", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        schema="identity",
    )


def downgrade() -> None:
    for table in (
        "preferences",
        "addresses",
        "profiles",
        "user_roles",
        "role_permissions",
        "permissions",
        "roles",
        "emails",
        "sessions_refresh",
        "otp_requests",
        "handles_history",
        "users",
    ):
        op.drop_table(table, schema="identity")
    op.execute("DROP SEQUENCE identity.agri_id_seq")
    bind = op.get_bind()
    sa.Enum(name="user_language", schema="identity").drop(bind, checkfirst=True)
    sa.Enum(name="user_status", schema="identity").drop(bind, checkfirst=True)
```

- [ ] **Step 2: Verify up + down + up on a throwaway DB**

The pytest session fixture creates and migrates `agri_test`; reuse it as the scratch target. **Never run migrate_check without `ALEMBIC_DATABASE_URL` — it wipes the target.**

```powershell
.\.venv\Scripts\python -m pytest tests\test_lint_contracts.py -v
$env:ALEMBIC_DATABASE_URL = "postgresql+asyncpg://app:app@localhost:55432/agri_test"
.\.venv\Scripts\python scripts\migrate_check.py
Remove-Item Env:\ALEMBIC_DATABASE_URL
```

Expected: lint contract tests PASS (THREAT/NOTES filled, no TODO); migrate_check prints `migrate_check: all migrations upgrade and downgrade cleanly`. If `agri_test` does not exist yet, run any db test first (e.g. `.\.venv\Scripts\python -m pytest tests\test_mixins.py -v`) to create it.

- [ ] **Step 3: Commit**

```powershell
git add backend/core/alembic/versions/0007_identity_v1.py
git commit -m "feat(d06): identity schema v1 migration - 12 tables, enums, AG sequence"
```

---

### Task 6: ORM models on the D03 mixins + lockstep integration test

**Files:**
- Modify: `backend/core/modules/identity/models.py` (currently a one-line docstring)
- Test: `backend/core/tests/test_identity_models.py`

**Interfaces:**
- Consumes: `shared.db.Base/UUIDv7PKMixin/TimestampMixin/SoftDeleteMixin`; tables from Task 5.
- Produces: ORM classes `User`, `HandleHistory`, `OtpRequest`, `SessionRefresh`, `Email`, `Role`, `Permission`, `RolePermission`, `UserRole`, `Profile`, `Address`, `Preference` — Task 8's service imports `User`, `Role`, `UserRole`.

- [ ] **Step 1: Write the failing tests**

Create `backend/core/tests/test_identity_models.py`:

```python
"""Identity ORM models stay in lockstep with migration 0007, and the D03
mixins (UUIDv7 PK, soft-delete default filter, unique phone) behave on the
real tables."""

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import modules.identity.models  # noqa: F401 - registers tables on Base.metadata
from shared.db import Base, soft_delete

IDENTITY_TABLES = (
    "users",
    "handles_history",
    "otp_requests",
    "sessions_refresh",
    "emails",
    "roles",
    "permissions",
    "role_permissions",
    "user_roles",
    "profiles",
    "addresses",
    "preferences",
)


async def test_orm_and_migration_agree_on_every_column(db_session: AsyncSession) -> None:
    conn = await db_session.connection()

    def _db_columns(sync_conn: Connection) -> dict[str, set[str]]:
        inspector = sa_inspect(sync_conn)
        return {
            table: {col["name"] for col in inspector.get_columns(table, schema="identity")}
            for table in IDENTITY_TABLES
        }

    db_columns = await conn.run_sync(_db_columns)
    for table in IDENTITY_TABLES:
        orm_table = Base.metadata.tables[f"identity.{table}"]
        orm_columns = {column.name for column in orm_table.columns}
        assert orm_columns == db_columns[table], f"identity.{table} drifted from migration 0007"


async def test_user_gets_uuid7_pk_and_defaults(db_session: AsyncSession) -> None:
    from modules.identity.models import User

    user = User(phone="+919876543210", agri_id="AG-0000001")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.id.version == 7
    assert user.status == "active"
    assert user.agri_id_changed_once is False
    assert user.phone_verified_at is None
    assert user.created_at.tzinfo is not None


async def test_one_account_per_phone(db_session: AsyncSession) -> None:
    from modules.identity.models import User

    db_session.add(User(phone="+919876543210", agri_id="AG-0000001"))
    await db_session.flush()
    db_session.add(User(phone="+919876543210", agri_id="AG-0000002"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_soft_deleted_users_hidden_by_default(db_session: AsyncSession) -> None:
    from modules.identity.models import User

    live = User(phone="+919876543210", agri_id="AG-0000001")
    dead = User(phone="+919876543211", agri_id="AG-0000002")
    db_session.add_all([live, dead])
    await db_session.flush()
    soft_delete(dead)
    await db_session.flush()
    db_session.expunge_all()

    phones = (await db_session.scalars(select(User.phone))).all()
    assert phones == ["+919876543210"]


async def test_profile_defaults(db_session: AsyncSession) -> None:
    from modules.identity.models import Profile, User

    user = User(phone="+919876543210", agri_id="AG-0000001")
    db_session.add(user)
    await db_session.flush()
    profile = Profile(user_id=user.id)
    db_session.add(profile)
    await db_session.flush()
    await db_session.refresh(profile)

    assert profile.language == "en"
    assert profile.interests == []
    assert profile.completion_score == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_models.py -v
```

Expected: FAIL — `models.py` defines no classes yet (`ImportError`/`AttributeError`/empty-metadata KeyError).

- [ ] **Step 3: Write the models**

Replace `backend/core/modules/identity/models.py` with:

```python
"""Identity module ORM models (D06.A/D) - mirrors migration 0007 exactly.

Every model rides the D03 mixins. The internal UUIDv7 PK is server-side
forever: it must never appear in a URL, API response, or INFO log. The public
identity is users.agri_id (@handle or AG-XXXXXXX fallback) - the
serialization guard in schemas.py makes leaking structurally impossible.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UUIDv7PKMixin

user_status_enum = postgresql.ENUM(
    "active", "suspended", "deleted", name="user_status", schema="identity", create_type=False
)
user_language_enum = postgresql.ENUM(
    "en", "ta", "hi", name="user_language", schema="identity", create_type=False
)

# user_id FK columns are written out per model rather than through a helper:
# mapped_column() is a dataclass_transform field specifier, and mypy only
# recognizes it when called directly in the class body.


class User(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    phone: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    phone_verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        user_status_enum, server_default=text("'active'"), nullable=False
    )
    agri_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    agri_id_changed_once: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )


class HandleHistory(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "handles_history"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    old_agri_id: Mapped[str] = mapped_column(Text, nullable=False)
    new_agri_id: Mapped[str] = mapped_column(Text, nullable=False)


class OtpRequest(UUIDv7PKMixin, TimestampMixin, Base):
    """Stores the OTP code HASH only - a plaintext code column must never exist."""

    __tablename__ = "otp_requests"
    __table_args__ = {"schema": "identity"}

    phone: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)


class SessionRefresh(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "sessions_refresh"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    device_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    rotated_from: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.sessions_refresh.id"), nullable=True
    )


class Email(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "emails"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class Role(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "identity"}

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Permission(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = {"schema": "identity"}

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class RolePermission(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id"),
        {"schema": "identity"},
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.roles.id"), nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.permissions.id"), nullable=False
    )


class UserRole(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id"),
        {"schema": "identity"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.roles.id"), nullable=False
    )


class Profile(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "profiles"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, unique=True
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    pincode: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(
        user_language_enum, server_default=text("'en'"), nullable=False
    )
    interests: Mapped[list[str]] = mapped_column(
        postgresql.JSONB, server_default=text("'[]'::jsonb"), nullable=False
    )
    completion_score: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )


class Address(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    line1: Mapped[str] = mapped_column(Text, nullable=False)
    line2: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    pincode: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )


class Preference(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "preferences"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, unique=True
    )
    notifications: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    privacy: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_models.py -v
```

Expected: all PASS (skips visibly if Postgres is down — start compose first).

- [ ] **Step 5: Commit**

```powershell
git add backend/core/modules/identity/models.py backend/core/tests/test_identity_models.py
git commit -m "feat(d06): identity ORM models on D03 mixins with lockstep test"
```

---

### Task 7: Migration 0008 — RBAC seed (roles + baseline permissions)

**Files:**
- Create: `backend/core/alembic/versions/0008_identity_seed_roles.py`
- Test: `backend/core/tests/test_identity_seeds.py`

**Interfaces:**
- Consumes: tables from Task 5; `uuid6.uuid7` for client-side PKs.
- Produces: seeded rows — roles `user, farmer, business_owner, staff, super_admin`; permissions `profile.read, profile.write, handle.change, users.suspend, roles.assign`; role→permission grants. Task 8's `assign_role` looks roles up by these names.

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_identity_seeds.py`:

```python
"""Seed migration 0008: the five roles and baseline permissions exist after
upgrade, wired via role_permissions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Permission, Role, RolePermission

EXPECTED_ROLES = {"user", "farmer", "business_owner", "staff", "super_admin"}
EXPECTED_PERMISSIONS = {
    "profile.read",
    "profile.write",
    "handle.change",
    "users.suspend",
    "roles.assign",
}


async def test_roles_seeded(db_session: AsyncSession) -> None:
    names = set((await db_session.scalars(select(Role.name))).all())
    assert EXPECTED_ROLES <= names


async def test_permissions_seeded(db_session: AsyncSession) -> None:
    names = set((await db_session.scalars(select(Permission.name))).all())
    assert EXPECTED_PERMISSIONS <= names


async def test_super_admin_has_every_baseline_permission(db_session: AsyncSession) -> None:
    stmt = (
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == "super_admin")
    )
    granted = set((await db_session.scalars(stmt)).all())
    assert granted == EXPECTED_PERMISSIONS


async def test_plain_user_cannot_suspend_or_assign(db_session: AsyncSession) -> None:
    stmt = (
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == "user")
    )
    granted = set((await db_session.scalars(stmt)).all())
    assert granted == {"profile.read", "profile.write", "handle.change"}
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_seeds.py -v
```

Expected: FAIL — roles table is empty (assertion failure). Note: the session-scoped test DB was migrated before this migration existed; delete the cached DB state by just re-running pytest (the `database_url` fixture drops and recreates `agri_test` every session), so the failure will be the empty-table assertions, not a missing migration.

- [ ] **Step 3: Write the seed migration**

Create `backend/core/alembic/versions/0008_identity_seed_roles.py`:

```python
"""Seed baseline RBAC: five roles, five permissions, and their grants.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-10

"""
# -- THREAT/NOTES:
# downgrade data loss: deletes exactly the seeded role/permission rows (matched
#   by name) and their grants. user_roles rows pointing at seeded roles are
#   deleted too - acceptable pre-launch; post-launch this downgrade would strip
#   role assignments and must be treated as an incident decision.
# locks: a handful of single-row DML statements on tiny tables; negligible.
# rollout: run after 0007; D07+ code may assume these role names exist.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: dict[str, str] = {
    "user": "baseline authenticated account",
    "farmer": "verified farming account",
    "business_owner": "verified business account",
    "staff": "internal moderation/support staff",
    "super_admin": "full administrative access",
}

PERMISSIONS: dict[str, str] = {
    "profile.read": "read own profile",
    "profile.write": "edit own profile",
    "handle.change": "change own @handle (one free change)",
    "users.suspend": "suspend or reinstate accounts",
    "roles.assign": "grant or revoke roles",
}

_BASELINE = ("profile.read", "profile.write", "handle.change")
ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "user": _BASELINE,
    "farmer": _BASELINE,
    "business_owner": _BASELINE,
    "staff": (*_BASELINE, "users.suspend"),
    "super_admin": tuple(PERMISSIONS),
}

_uuid = postgresql.UUID(as_uuid=True)
roles_table = sa.table(
    "roles",
    sa.column("id", _uuid),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
    schema="identity",
)
permissions_table = sa.table(
    "permissions",
    sa.column("id", _uuid),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
    schema="identity",
)
role_permissions_table = sa.table(
    "role_permissions",
    sa.column("id", _uuid),
    sa.column("role_id", _uuid),
    sa.column("permission_id", _uuid),
    schema="identity",
)
user_roles_table = sa.table(
    "user_roles",
    sa.column("role_id", _uuid),
    schema="identity",
)


def upgrade() -> None:
    role_ids = {name: uuid6.uuid7() for name in ROLES}
    permission_ids = {name: uuid6.uuid7() for name in PERMISSIONS}

    op.bulk_insert(
        roles_table,
        [{"id": role_ids[n], "name": n, "description": d} for n, d in ROLES.items()],
    )
    op.bulk_insert(
        permissions_table,
        [{"id": permission_ids[n], "name": n, "description": d} for n, d in PERMISSIONS.items()],
    )
    op.bulk_insert(
        role_permissions_table,
        [
            {"id": uuid6.uuid7(), "role_id": role_ids[role], "permission_id": permission_ids[perm]}
            for role, perms in ROLE_GRANTS.items()
            for perm in perms
        ],
    )


def downgrade() -> None:
    seeded_roles = sa.select(roles_table.c.id).where(roles_table.c.name.in_(list(ROLES)))
    seeded_perms = sa.select(permissions_table.c.id).where(
        permissions_table.c.name.in_(list(PERMISSIONS))
    )
    op.execute(
        role_permissions_table.delete().where(
            role_permissions_table.c.role_id.in_(seeded_roles)
        )
    )
    op.execute(user_roles_table.delete().where(user_roles_table.c.role_id.in_(seeded_roles)))
    op.execute(
        role_permissions_table.delete().where(
            role_permissions_table.c.permission_id.in_(seeded_perms)
        )
    )
    op.execute(permissions_table.delete().where(permissions_table.c.name.in_(list(PERMISSIONS))))
    op.execute(roles_table.delete().where(roles_table.c.name.in_(list(ROLES))))
```

- [ ] **Step 4: Run tests + migrate_check to verify**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_seeds.py tests\test_lint_contracts.py -v
$env:ALEMBIC_DATABASE_URL = "postgresql+asyncpg://app:app@localhost:55432/agri_test"
.\.venv\Scripts\python scripts\migrate_check.py
Remove-Item Env:\ALEMBIC_DATABASE_URL
```

Expected: all PASS; migrate_check clean (proves the seed downgrade deletes cleanly).

- [ ] **Step 5: Commit**

```powershell
git add backend/core/alembic/versions/0008_identity_seed_roles.py backend/core/tests/test_identity_seeds.py
git commit -m "feat(d06): seed baseline roles and permissions"
```

---

### Task 8: Identity service layer skeleton

**Files:**
- Modify: `backend/core/modules/identity/service.py` (currently a one-line docstring)
- Test: `backend/core/tests/test_identity_service.py`

**Interfaces:**
- Consumes: `User`, `Role`, `UserRole` from Task 6; `normalize_phone` (Task 1); `AGRI_ID_SEQUENCE`, `format_agri_id` (Task 2); seeded role names (Task 7).
- Produces: `async create_user(session: AsyncSession, phone: str) -> User`, `async get_by_phone(session: AsyncSession, phone: str) -> User | None`, `async assign_role(session: AsyncSession, user_id: uuid.UUID, role_name: str) -> UserRole`, `UnknownRoleError(LookupError)`. This is the module's public service interface — other modules and D07+ HTTP call these, never the tables.

- [ ] **Step 1: Write the failing tests**

Create `backend/core/tests/test_identity_service.py`:

```python
"""Identity service skeleton (D06.D): create_user / get_by_phone / assign_role.
Service interface only - no HTTP, no commits (transaction scope is the caller's)."""

import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Role, UserRole
from modules.identity.service import UnknownRoleError, assign_role, create_user, get_by_phone

AGRI_ID_PATTERN = re.compile(r"^AG-[0-9A-HJKMNP-TV-Z]{7}$")


async def test_create_user_assigns_ag_fallback(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "9876543210")
    assert user.phone == "+919876543210"  # +91 default applied
    assert AGRI_ID_PATTERN.fullmatch(user.agri_id)
    assert user.agri_id_changed_once is False


async def test_agri_ids_are_distinct(db_session: AsyncSession) -> None:
    first = await create_user(db_session, "9876543210")
    second = await create_user(db_session, "9876543211")
    assert first.agri_id != second.agri_id


async def test_one_account_per_phone_bubbles_integrity_error(db_session: AsyncSession) -> None:
    await create_user(db_session, "9876543210")
    with pytest.raises(IntegrityError):
        await create_user(db_session, "+91 98765 43210")  # same number, different spelling


async def test_get_by_phone_normalizes_before_lookup(db_session: AsyncSession) -> None:
    created = await create_user(db_session, "+919876543210")
    found = await get_by_phone(db_session, "98765 43210")
    assert found is not None
    assert found.id == created.id


async def test_get_by_phone_returns_none_for_unknown(db_session: AsyncSession) -> None:
    assert await get_by_phone(db_session, "9876543299") is None


async def test_assign_role_links_seeded_role(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "9876543210")
    link = await assign_role(db_session, user.id, "farmer")

    role = await db_session.scalar(select(Role).where(Role.id == link.role_id))
    assert role is not None and role.name == "farmer"
    stored = await db_session.scalar(select(UserRole).where(UserRole.user_id == user.id))
    assert stored is not None


async def test_assign_unknown_role_raises(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "9876543210")
    with pytest.raises(UnknownRoleError):
        await assign_role(db_session, user.id, "warlord")


async def test_assign_role_to_missing_user_bubbles_integrity_error(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError):
        await assign_role(db_session, uuid.uuid4(), "user")
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_service.py -v
```

Expected: FAIL with `ImportError: cannot import name 'create_user' from 'modules.identity.service'`.

- [ ] **Step 3: Write the implementation**

Replace `backend/core/modules/identity/service.py` with:

```python
"""Identity module public service interface (D06.D) - no HTTP here.

Other modules and future routers (D07+) go through these functions, never
through the tables. Functions take the caller's AsyncSession and flush but
never commit - transaction scope belongs to the caller. The internal UUID
never leaves the service boundary in any public shape (see schemas.py).
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.agri_id import AGRI_ID_SEQUENCE, format_agri_id
from modules.identity.models import Role, User, UserRole
from modules.identity.phone import normalize_phone


class UnknownRoleError(LookupError):
    """The requested role name is not seeded/known."""


async def create_user(session: AsyncSession, phone: str) -> User:
    """Create a user with an AG- fallback agri_id from the atomic sequence.

    One account per phone is the users.phone unique constraint; a duplicate
    surfaces as IntegrityError at flush - callers translate, never pre-check.
    """
    normalized = normalize_phone(phone)
    sequence_value = await session.scalar(text(f"SELECT nextval('{AGRI_ID_SEQUENCE}')"))
    if sequence_value is None:  # pragma: no cover - nextval cannot return NULL
        raise RuntimeError("agri_id sequence returned no value")
    user = User(phone=normalized, agri_id=format_agri_id(sequence_value))
    session.add(user)
    await session.flush()
    return user


async def get_by_phone(session: AsyncSession, phone: str) -> User | None:
    return await session.scalar(select(User).where(User.phone == normalize_phone(phone)))


async def assign_role(session: AsyncSession, user_id: uuid.UUID, role_name: str) -> UserRole:
    role = await session.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise UnknownRoleError(role_name)
    user_role = UserRole(user_id=user_id, role_id=role.id)
    session.add(user_role)
    await session.flush()
    return user_role
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests\test_identity_service.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/core/modules/identity/service.py backend/core/tests/test_identity_service.py
git commit -m "feat(d06): identity service skeleton - create_user, get_by_phone, assign_role"
```

---

### Task 9: Full gates, line-by-line read, PR

**Files:**
- None new (fixes only, if gates fail).

- [ ] **Step 1: Run every gate locally, from `backend\core`**

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy .
.\.venv\Scripts\lint-imports
.\.venv\Scripts\python -m pytest -v
$env:ALEMBIC_DATABASE_URL = "postgresql+asyncpg://app:app@localhost:55432/agri_test"
.\.venv\Scripts\python scripts\migrate_check.py
Remove-Item Env:\ALEMBIC_DATABASE_URL
```

Expected: ruff clean, mypy clean (strict), import-linter contracts kept (identity imports no sibling module), full pytest suite green (including the pre-existing suites — especially `test_demo_migration.py` and `test_lint_contracts.py`), migrate_check clean. Fix anything that fails before proceeding.

- [ ] **Step 2: 🔍 Definition-of-done read**

Read line-by-line, as the spec requires (not optional): `alembic/versions/0007_identity_v1.py` (every table definition), `alembic/versions/0008_identity_seed_roles.py`, `modules/identity/models.py`, and `modules/identity/schemas.py` (the guard). Confirm: no plaintext OTP column, phone/UUID appear in no public schema, every FK targets `identity.*`, every table has pk + timestamps.

- [ ] **Step 3: Push and open the PR to dev**

```powershell
git push -u origin feat/d06-identity-schema
```

```powershell
gh pr create --base dev --title "feat(d06): identity schema" --body @'
## D06 - Identity schema

- 12 tables in schema `identity` via the D03 migration template (0007), all on pk/timestamp/soft-delete mixin columns
- Pure, exhaustively unit-tested modules: @handle rules + file-extensible reserved blocklist, AG-XXXXXXX Crockford fallback over an atomic PG sequence (collision-impossible by construction), E.164 phone normalization (+91 default)
- Structural serialization guard: a public identity schema containing uuid.UUID or phone fails at class definition (test proves it)
- RBAC seed migration (0008): user/farmer/business_owner/staff/super_admin + baseline permissions
- Service skeleton: create_user / get_by_phone / assign_role - no HTTP (D07+)
- otp_requests stores code_hash only; no plaintext code column exists to leak

Deferred on purpose: dropping `_demo_all_mixins` - it remains the lockstep gate for the full mixin set incl. moderation_status, which no identity table carries; drop it with the first UGC-bearing table.

Verified: ruff, mypy --strict, lint-imports, full pytest, migrate_check (up/down/up) all green locally.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
'@
```

- [ ] **Step 4: Watch CI, merge when green**

```powershell
gh pr checks --watch
```

All 7 required checks green → merge via `gh pr merge --squash` only if the user's standing workflow allows; otherwise report ready-to-merge.
