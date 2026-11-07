from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class ProductInput(BaseModel):
    name: Annotated[StrictStr, Field(min_length=1, max_length=180)]
    manufacturer: Annotated[StrictStr | None, Field(max_length=180)] = None
    specs: Annotated[dict[str, StrictStr | None], Field(max_length=40)] = Field(default_factory=dict)
    description: Annotated[StrictStr | None, Field(max_length=12000)] = None

    model_config = ConfigDict(extra='forbid')

    @field_validator('name', 'manufacturer', 'description', mode='before')
    @classmethod
    def check_text(cls, value, info):
        if isinstance(value, str):
            value = value.strip()
            if not value and info.field_name != 'name':
                return None
        return value

    @field_validator('specs', mode='after')
    @classmethod
    def check_specs(cls, value):
        cleaned = {}
        for name, specification in value.items():
            field_name = name.strip()
            if not field_name or len(field_name) > 120:
                raise ValueError('Название характеристики должно содержать от 1 до 120 символов.')
            if field_name.casefold() in {item.casefold() for item in cleaned}:
                raise ValueError('Названия характеристик не должны повторяться.')
            if specification is not None:
                specification = specification.strip()
                if len(specification) > 500:
                    raise ValueError('Значение характеристики должно быть не длиннее 500 символов.')
            cleaned[field_name] = specification or None
        return cleaned


class SourceConflict(BaseModel):
    field: str
    quote: str
    explanation: str

    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class CardDraft(BaseModel):
    seo_title: str
    seo_description: str
    search_queries: list[str]
    commercial_block: str
    conflicts: list[SourceConflict]

    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class Characteristic(BaseModel):
    name: str
    value: str


class ProductCard(BaseModel):
    seo_title: str
    seo_description: str
    characteristics: list[Characteristic]
    search_queries: list[str]
    commercial_block: str


class CardChecks(BaseModel):
    title_length: int
    description_length: int
    query_count: int
    passed: bool


class GenerationResponse(BaseModel):
    status: Literal['ready', 'needs_review', 'insufficient_data', 'needs_clarification']
    card: ProductCard | None = None
    checks: CardChecks | None = None
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    card: ProductCard
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra='forbid')
