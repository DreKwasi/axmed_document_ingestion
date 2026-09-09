"""Canonical quotation contract and domain models for document intelligence."""

import re
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- Section 1: Grammatical & Text Normalization Helpers ---


def _singularize_uom(value: str | None) -> str | None:
    """Normalize grammatical plural unit-of-measure labels without changing category.

    Examples:
        - "tablets" -> "tablet"
        - "vials" -> "vial"
        - "boxes" -> "box"

    Args:
        value: Raw UOM string or None.

    Returns:
        Singularized string or None.
    """
    if value is None:
        return None
    normalized = value.strip()
    if normalized.casefold() == "boxes":
        return normalized[:-2]
    if len(normalized) > 3 and normalized.casefold().endswith("s") and not normalized.casefold().endswith("ss"):
        return normalized[:-1]
    return normalized


def _pack_quantity_from_description(value: str | None) -> tuple[int, str] | None:
    """Extract explicit packaging counts from freeform descriptions.

    Parses patterns such as "100 tablets per box" or "50 vials/carton" into a count
    and a normalized singular unit label.

    Args:
        value: Packaging description string or None.

    Returns:
        Tuple of (units_per_pack, singular_unit_label) or None if no match.
    """
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


# --- Section 2: Product Identity & Active Ingredients (INN) ---


class Strength(BaseModel):
    """Pharmaceutical strength and concentration specification.

    Captures active ingredient potency per administration unit (e.g. 500 mg per 1 tablet,
    or 5 mg/ml per 10 ml ampoule).
    """

    ingredient: str | None = Field(
        default=None,
        description="Active ingredient this potency belongs to; pair combination strengths with INNs in source order.",
    )
    value: Decimal | None = Field(default=None, description="Numeric potency before any denominator.")
    unit: str | None = Field(default=None, description="Potency unit, for example mg, mcg, g, IU, or percent.")
    per_value: Decimal | None = Field(
        default=None,
        description="Explicit denominator quantity; use 1 for concentrations written with only '/mL'.",
    )
    per_unit: str | None = Field(default=None, description="Explicit denominator unit, for example mL or actuation.")

    @field_validator("ingredient")
    @classmethod
    def normalize_active_moiety_name(cls, value: str | None) -> str | None:
        """Strip redundant salt / ester parentheticals from ingredient labels."""
        if value is None:
            return None
        return re.sub(r"\s*\(as\s+[^)]+\)$", "", value.strip(), flags=re.IGNORECASE)


class Product(BaseModel):
    """Core pharmaceutical product identification.

    Distinguishes proprietary trade names from generic International Nonproprietary
    Names (INN) and captures dosage form, manufacturer, and country of origin.
    """

    trade_name: str | None = Field(default=None, description="Supplier brand or proprietary product name.")
    inn: list[str] = Field(
        default_factory=list,
        description="Active ingredients or International Nonproprietary Names in source order.",
    )
    strength: list[Strength] = Field(
        default_factory=list,
        description="Structured potency or concentration entries paired to active ingredients in source order.",
    )
    dosage_form: str | None = None
    manufacturer: str | None = None
    country_of_origin: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_dosage_form(cls, values: Any) -> Any:
        """Normalize dashes, whitespace, and case in dosage forms (e.g. 'tablet', 'solution for injection')."""
        if not isinstance(values, dict) or not isinstance(values.get("dosage_form"), str):
            return values

        normalized_values = dict(values)
        normalized_values["dosage_form"] = re.sub(
            r"\s+", " ", values["dosage_form"].strip().lower().replace("–", "-").replace("—", "-")
        )
        return normalized_values


# --- Section 3: Supplier Profile & Commercial Terms ---


class Supplier(BaseModel):
    """Commercial supplier entity profile and manufacturing site references."""

    name: str | None = None
    supplier_code: str | None = None
    country: str | None = None
    manufacturing_site: str | None = None


class CommercialTerms(BaseModel):
    """Document-level trade conditions, Incoterms, and tariff codes.

    Incoterms specify transfer of logistics risk (e.g., FOB, CIF, EXW, DDP).
    """

    currency: str | None = None
    incoterm: str | None = None
    incoterm_named_place: str | None = None
    incoterm_country: str | None = None
    payment_terms: str | None = None
    price_basis: str | None = None
    transit_time_days: int | None = None
    transit_time_min_days: int | None = None
    transit_time_max_days: int | None = None
    hs_codes: list[str] = Field(default_factory=list)


# --- Section 4: Packaging Hierarchies & Quantity Specifications ---


class Packaging(BaseModel):
    """Packaging hierarchy from primary container to shipping carton."""

    description: str | None = Field(
        default=None,
        description="Complete source packaging text, preserved without dropping configuration details.",
    )
    presentation: str | None = Field(
        default=None,
        description=(
            "Review-facing product presentation. Use an explicit presentation value when supplied; otherwise retain "
            "the complete packaging description so a differently labelled source does not appear missing."
        ),
    )
    primary_pack: str | None = Field(
        default=None,
        description="Immediate named container or material, such as Alu-Alu blister, HDPE bottle, vial, or ampoule.",
    )
    units_per_pack: int | None = Field(default=None, description="Total count of saleable units in one quoted pack.")
    unit_label: str | None = Field(default=None, description="Saleable unit contained by the pack, singularized.")
    packs_per_shipper: int | None = Field(
        default=None,
        description="Number of packs contained in an outer shipper or shipping carton.",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_presentation(cls, values: Any) -> Any:
        """Normalize packaging presentation strings to lowercase stripped format."""
        if not isinstance(values, dict) or not isinstance(values.get("presentation"), str):
            return values
        normalized = dict(values)
        normalized["presentation"] = values["presentation"].strip().lower()
        return normalized

    @model_validator(mode="after")
    def fill_explicit_pack_quantity(self) -> "Packaging":
        """Retain the review presentation and infer explicit pack quantity from the full description."""
        if self.presentation is None and self.description:
            self.presentation = self.description
        parsed = _pack_quantity_from_description(self.description)
        if parsed is not None:
            units, label = parsed
            if self.units_per_pack is None:
                self.units_per_pack = units
            if self.unit_label is None:
                self.unit_label = label
        return self


class Quantity(BaseModel):
    """Line-item volume terms including quoted quantity and Minimum Order Quantity (MOQ)."""

    quoted_quantity: Decimal | None = None
    quoted_quantity_uom: str | None = None
    quantity_basis: str | None = None
    minimum_order_quantity: Decimal | None = None
    minimum_order_quantity_uom: str | None = None

    @field_validator("quoted_quantity_uom", "minimum_order_quantity_uom")
    @classmethod
    def normalize_uom_number(cls, value: str | None) -> str | None:
        """Singularize volume units (e.g. 'cartons' -> 'carton')."""
        return _singularize_uom(value)


# --- Section 5: Pricing Structures, Price Tiers & Adjustments ---


class QuotedPrice(BaseModel):
    """Base quoted price and unit of measure as stated by supplier."""

    amount: Decimal | None = None
    uom: str | None = None

    @field_validator("uom")
    @classmethod
    def normalize_uom(cls, value: str | None) -> str | None:
        """Singularize price unit of measure."""
        return _singularize_uom(value)


class PriceTier(BaseModel):
    """Volume-dependent tiered price bracket."""

    min_quantity: Decimal | None = None
    max_quantity: Decimal | None = None
    quantity_uom: str | None = None
    price: Decimal | None = None
    price_uom: str | None = None


class Adjustment(BaseModel):
    """Commercial price adjustments such as discounts, freight surcharges, or tariffs."""

    type: str
    value: Decimal | None = None
    value_type: str | None = None
    condition: str | None = None


class Pricing(BaseModel):
    """Comprehensive pricing structure, including derived normalized unit prices."""

    currency: str | None = None
    quoted_price: QuotedPrice = Field(default_factory=QuotedPrice)
    pack_price: Decimal | None = None
    discount: Decimal | None = None
    extended_price: Decimal | None = None
    price_tiers: list[PriceTier] = Field(default_factory=list)
    adjustments: list[Adjustment] = Field(default_factory=list)
    normalized_price: dict[str, Any] = Field(default_factory=dict)


# --- Section 6: Supply Chain Logistics & Regulatory Compliance ---


class Supply(BaseModel):
    """Manufacturing lead times, product shelf life, and storage environmental controls."""

    lead_time_days: int | None = None
    lead_time_min_days: int | None = None
    lead_time_max_days: int | None = None
    shelf_life_months: int | None = None
    minimum_remaining_shelf_life_percent: Decimal | None = None
    storage_conditions: str | None = None
    cold_chain_required: bool | None = None


class Regulatory(BaseModel):
    """Market authorization, WHO prequalification, and registration dossiers."""

    who_prequalified: bool | None = None
    who_pq_reference: str | None = None
    registered_markets: list[str] = Field(default_factory=list)
    registration_reference: str | None = None
    regulatory_status: str | None = None


# --- Section 7: Audit Provenance & Quality Review Issues ---


class Evidence(BaseModel):
    """Audit trail record linking an extracted fact to its raw source coordinates."""

    canonical_field: str
    source_path: str | None = None
    source_location: str | None = None
    extraction_method: str
    confidence: Decimal
    supersedes_source_path: str | None = None


class ReviewIssue(BaseModel):
    """System-generated commercial or extraction issue requiring human review."""

    field_path: str
    code: str
    message: str
    severity: str = "warning"


# --- Section 8: Line Items & Aggregate Canonical Quotation Document ---


class LineItem(BaseModel):
    """One individual product entry within a supplier quotation."""

    source_key: str | None = None
    product: Product = Field(default_factory=Product)
    packaging: Packaging = Field(default_factory=Packaging)
    quantity: Quantity = Field(default_factory=Quantity)
    pricing: Pricing = Field(default_factory=Pricing)
    supply: Supply = Field(default_factory=Supply)
    regulatory: Regulatory = Field(default_factory=Regulatory)
    evidence: list[Evidence] = Field(default_factory=list)


class CanonicalQuotation(BaseModel):
    """Top-level canonical quotation schema aggregating all source facts."""

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
    narrative_summary: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    review_issues: list[ReviewIssue] = Field(default_factory=list)
