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
                _contains_uuid(field.annotation) for field in annotation.model_fields.values()
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
