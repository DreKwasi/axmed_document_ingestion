import re
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CORE_DOSAGE_FORMS = (
    "tablet",
    "capsule",
    "syrup",
    "suspension",
    "solution",
    "cream",
    "ointment",
    "gel",
    "drops",
    "spray",
    "injection",
    "suppository",
    "patch",
)


def _core_dosage_form(value: str) -> tuple[str, str | None]:
    """Split a source dosage-form phrase into a core form and presentation qualifier."""
    normalized = re.sub(r"\s+", " ", value.strip().lower().replace("–", "-").replace("—", "-"))
    for core_form in _CORE_DOSAGE_FORMS:
        match = re.search(rf"\b{re.escape(core_form)}s?\b", normalized)
        if match:
            presentation = (normalized[: match.start()] + normalized[match.end() :]).strip(" -,") or None
            return core_form, presentation
    return normalized, None


def _clean_presentation_qualifier(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(
        r"^\d+(?:[.,/]\d+)?\s*[a-zµμ]+(?:\s*/\s*\d+(?:[.,]\d+)?\s*[a-zµμ]+)?\s+",
        "",
        value.strip(),
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" ,-") or None


def _singularize_uom(value: str | None) -> str | None:
    """Normalize grammatical plural UOM labels without changing their commercial category."""

    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) > 3 and normalized.casefold().endswith("s") and not normalized.casefold().endswith("ss"):
        return normalized[:-1]
    return normalized


def _pack_quantity_from_description(value: str | None) -> tuple[int, str] | None:
    """Read an explicit ``N units per pack`` phrase without choosing a commercial UOM."""

    if not value:
        return None
    match = re.search(
        r"(?P<count>\d[\d,]*)\s+(?P<label>[A-Za-z][A-Za-z -]*?)\s*(?:per|/)\s*"
        r"(?:pack|box|carton|case|kit)\b",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    label = _singularize_uom(match.group("label").strip())
    if not label:
        return None
    return int(match.group("count").replace(",", "")), label


class Strength(BaseModel):
    ingredient: str | None = None
    value: Decimal | None = None
    unit: str | None = None
    per_value: Decimal | None = None
    per_unit: str | None = None

    @field_validator("ingredient")
    @classmethod
    def normalize_active_moiety_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return re.sub(r"\s*\(as\s+[^)]+\)$", "", value.strip(), flags=re.IGNORECASE)


class Supplier(BaseModel):
    name: str | None = None
    supplier_code: str | None = None
    country: str | None = None
    manufacturing_site: str | None = None


class CommercialTerms(BaseModel):
    currency: str | None = None
    incoterm: str | None = None
    incoterm_named_place: str | None = None
    incoterm_country: str | None = None
    payment_terms: str | None = None
    price_basis: str | None = None
    hs_codes: list[str] = Field(default_factory=list)


class Packaging(BaseModel):
    description: str | None = None
    presentation: str | None = None
    primary_pack: str | None = None
    units_per_pack: int | None = None
    unit_label: str | None = None
    packs_per_shipper: int | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_presentation(cls, values: Any) -> Any:
        if not isinstance(values, dict) or not isinstance(values.get("presentation"), str):
            return values
        normalized = dict(values)
        normalized["presentation"] = values["presentation"].strip().lower()
        _, qualifier = _core_dosage_form(values["presentation"])
        if qualifier is not None:
            normalized["presentation"] = (_clean_presentation_qualifier(qualifier) or qualifier).lower()
        return normalized

    @model_validator(mode="after")
    def fill_explicit_pack_quantity(self) -> "Packaging":
        parsed = _pack_quantity_from_description(self.description)
        if parsed is not None:
            units, label = parsed
            if self.units_per_pack is None:
                self.units_per_pack = units
            if self.unit_label is None:
                self.unit_label = label
        if self.presentation is None:
            _, qualifier = _core_dosage_form(self.description or "")
            cleaned = _clean_presentation_qualifier(qualifier)
            if cleaned is not None:
                self.presentation = cleaned.lower()
        return self


class Quantity(BaseModel):
    quoted_quantity: Decimal | None = None
    quoted_quantity_uom: str | None = None
    quantity_basis: str | None = None
    minimum_order_quantity: Decimal | None = None
    minimum_order_quantity_uom: str | None = None

    @field_validator("quoted_quantity_uom", "minimum_order_quantity_uom")
    @classmethod
    def normalize_uom_number(cls, value: str | None) -> str | None:
        return _singularize_uom(value)


class QuotedPrice(BaseModel):
    amount: Decimal | None = None
    uom: str | None = None

    @field_validator("uom")
    @classmethod
    def normalize_uom(cls, value: str | None) -> str | None:
        return _singularize_uom(value)


class PriceTier(BaseModel):
    min_quantity: Decimal | None = None
    max_quantity: Decimal | None = None
    quantity_uom: str | None = None
    price: Decimal | None = None
    price_uom: str | None = None


class Adjustment(BaseModel):
    type: str
    value: Decimal | None = None
    value_type: str | None = None
    condition: str | None = None


class Pricing(BaseModel):
    currency: str | None = None
    quoted_price: QuotedPrice = Field(default_factory=QuotedPrice)
    pack_price: Decimal | None = None
    discount: Decimal | None = None
    extended_price: Decimal | None = None
    price_tiers: list[PriceTier] = Field(default_factory=list)
    adjustments: list[Adjustment] = Field(default_factory=list)
    normalized_price: dict[str, Any] = Field(default_factory=dict)


class Supply(BaseModel):
    lead_time_days: int | None = None
    lead_time_min_days: int | None = None
    lead_time_max_days: int | None = None
    shelf_life_months: int | None = None
    minimum_remaining_shelf_life_percent: Decimal | None = None
    storage_conditions: str | None = None
    cold_chain_required: bool | None = None


class Regulatory(BaseModel):
    who_prequalified: bool | None = None
    who_pq_reference: str | None = None
    registered_markets: list[str] = Field(default_factory=list)
    registration_reference: str | None = None
    regulatory_status: str | None = None


class Product(BaseModel):
    trade_name: str | None = None
    inn: list[str] = Field(default_factory=list)
    strength: list[Strength] = Field(default_factory=list)
    dosage_form: str | None = None
    manufacturer: str | None = None
    country_of_origin: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_dosage_form(cls, values: Any) -> Any:
        if not isinstance(values, dict) or not isinstance(values.get("dosage_form"), str):
            return values

        dosage_form, _ = _core_dosage_form(values["dosage_form"])
        normalized_values = dict(values)
        normalized_values["dosage_form"] = dosage_form
        return normalized_values


class Evidence(BaseModel):
    canonical_field: str
    source_path: str | None = None
    source_location: str | None = None
    extraction_method: str
    confidence: Decimal
    supersedes_source_path: str | None = None


class ReviewIssue(BaseModel):
    field_path: str
    code: str
    message: str
    severity: str = "warning"


class LineItem(BaseModel):
    source_key: str | None = None
    product: Product = Field(default_factory=Product)
    packaging: Packaging = Field(default_factory=Packaging)
    quantity: Quantity = Field(default_factory=Quantity)
    pricing: Pricing = Field(default_factory=Pricing)
    supply: Supply = Field(default_factory=Supply)
    regulatory: Regulatory = Field(default_factory=Regulatory)
    evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def move_dosage_qualifier_to_packaging(cls, values: Any) -> Any:
        if not isinstance(values, dict) or not isinstance(values.get("product"), dict):
            return values
        dosage_form = values["product"].get("dosage_form")
        if not isinstance(dosage_form, str):
            return values

        core_form, presentation = _core_dosage_form(dosage_form)
        normalized_values = dict(values)
        normalized_product = dict(values["product"])
        normalized_product["dosage_form"] = core_form
        normalized_values["product"] = normalized_product
        if presentation:
            packaging = dict(values.get("packaging") or {})
            packaging.setdefault("presentation", presentation)
            normalized_values["packaging"] = packaging
        return normalized_values


class CanonicalQuotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    quotation_reference: str | None = None
    rfq_reference: str | None = None
    document_type: str | None = None
    issue_date: str | None = None
    valid_until: str | None = None
    supplier: Supplier = Field(default_factory=Supplier)
    commercial_terms: CommercialTerms = Field(default_factory=CommercialTerms)
    line_items: list[LineItem] = Field(default_factory=list)
    source: dict[str, str | None] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    review_issues: list[ReviewIssue] = Field(default_factory=list)
