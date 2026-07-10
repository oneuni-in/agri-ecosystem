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
