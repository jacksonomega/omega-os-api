from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """
    Modelo base Pydantic v2 que convierte automáticamente snake_case <-> camelCase
    para compatibilidad al 100 % con el frontend Angular 18 de Omega OS.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
    )
