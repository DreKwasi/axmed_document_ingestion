"""PRD commercial validation and deterministic pricing derivation."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.extraction.contracts import CanonicalQuotation, LineItem, ReviewIssue

# --- Section 1: Rule Engine Context & Evaluator Protocols ---


@dataclass(frozen=True)
class RuleContext:
    """Evaluation context supplied to deterministic commercial rule handlers."""

    quotation: CanonicalQuotation
    line: LineItem | None = None
    line_index: int | None = None

    def issue(self, code: str, field: str, message: str) -> ReviewIssue:
        """Create a targeted ReviewIssue attached to either the document or line item."""
        path = field if self.line_index is None else f"line_items[{self.line_index}].{field}"
        return ReviewIssue(field_path=path, code=code, message=message, severity="error")


RuleEvaluator = Callable[[RuleContext], list[ReviewIssue]]


@dataclass(frozen=True)
class CommercialRule:
    """Declared commercial validation rule bound to document or line-item scope."""

    codes: tuple[str, ...]
    scope: str
    evaluate: RuleEvaluator


# --- Section 2: Document-Level Commercial Rules ---


def _quotation_dates(context: RuleContext) -> list[ReviewIssue]:
    """Validate that quotation issue date is chronologically on or before expiry."""
    quotation = context.quotation
    if not quotation.issue_date or not quotation.valid_until:
        return []
    try:
        invalid = date.fromisoformat(quotation.issue_date) > date.fromisoformat(quotation.valid_until)
    except ValueError:
        invalid = True
    if invalid:
        return [context.issue("invalid_date_range", "valid_until", "Issue date must be on or before expiry.")]
    return []


# --- Section 3: Pricing & Packaging Derivation (Normalized Unit Prices) ---


def _price_and_pack(context: RuleContext) -> list[ReviewIssue]:
    """Validate prices and derive normalized unit prices.

    When pack_price is provided and units_per_pack is positive, computes:
        normalized_price = pack_price / units_per_pack
    If only quoted_price is present, sets quoted price as the normalized amount.
    """
    assert context.line is not None
    pricing = context.line.pricing
    units = context.line.packaging.units_per_pack
    if pricing.pack_price is None:
        if pricing.quoted_price.amount is not None and pricing.quoted_price.uom:
            pricing.normalized_price = {
                "amount": pricing.quoted_price.amount,
                "uom": pricing.quoted_price.uom,
                "calculation": "quoted_price.amount",
                "derived": True,
                "validation_status": "passed",
            }
        return []
    # ``pack_price`` has already been classified by the mapping/reasoning
    # layer. It does not license a global assumption that the source UOM is
    # "pack": it may be a carton, kit, bottle, vial, or an unclassified
    # supplier term. Preserve an explicit quoted-price basis and leave an
    # unknown basis null for review.
    if pricing.quoted_price.amount is None:
        pricing.quoted_price.amount = pricing.pack_price
    issues = []
    if pricing.pack_price <= 0:
        issues.append(context.issue("non_positive_price", "pricing.pack_price", "Quoted pack price must be positive."))
    if units is None:
        return issues
    if units <= 0:
        return issues + [
            context.issue("invalid_pack_units", "packaging.units_per_pack", "Units per pack must be positive.")
        ]
    pricing.normalized_price = {
        "amount": pricing.pack_price / Decimal(units),
        "uom": context.line.packaging.unit_label or "unit",
        "calculation": f"{pricing.pack_price} / {units}",
        "derived": True,
        "validation_status": "passed",
    }
    return issues


# --- Section 4: Volume & Minimum Order Quantity (MOQ) Checks ---


def _minimum_order_quantity(context: RuleContext) -> list[ReviewIssue]:
    """Validate MOQ positivity and flag orders below the supplier threshold."""
    assert context.line is not None
    quantity = context.line.quantity
    moq = quantity.minimum_order_quantity
    if moq is not None and moq < 0:
        return [context.issue("negative_moq", "quantity.minimum_order_quantity", "MOQ cannot be negative.")]
    if (
        quantity.quoted_quantity is not None
        and moq is not None
        and quantity.quoted_quantity < moq
        and (
            quantity.quoted_quantity_uom is None
            or quantity.minimum_order_quantity_uom is None
            or quantity.quoted_quantity_uom == quantity.minimum_order_quantity_uom
        )
    ):
        return [
            context.issue(
                "below_minimum_order_quantity",
                "quantity.quoted_quantity",
                "Quoted quantity is below the minimum order quantity.",
            )
        ]
    return []


# --- Section 5: Surcharges, Discounts & Tiered Pricing Integrity ---


def _percentage_adjustments(context: RuleContext) -> list[ReviewIssue]:
    """Ensure percentage adjustments (discounts/surcharges) are bounded between 0% and 100%."""
    assert context.line is not None
    for adjustment in context.line.pricing.adjustments:
        if (
            adjustment.value_type == "percentage"
            and adjustment.value is not None
            and not Decimal("0") <= adjustment.value <= Decimal("100")
        ):
            return [
                context.issue(
                    "invalid_percentage", "pricing.adjustments", "Percentage adjustments must be between 0 and 100."
                )
            ]
    return []


def _price_tiers(context: RuleContext) -> list[ReviewIssue]:
    """Detect overlapping volume brackets in tiered pricing schedules."""
    assert context.line is not None
    tiers = sorted(context.line.pricing.price_tiers, key=lambda tier: tier.min_quantity or Decimal("0"))
    for previous, current in zip(tiers, tiers[1:], strict=False):
        if (
            previous.max_quantity is not None
            and current.min_quantity is not None
            and current.min_quantity <= previous.max_quantity
        ):
            return [context.issue("overlapping_price_tier", "pricing.price_tiers", "Price-tier ranges overlap.")]
    return []


# --- Section 6: Rule Registry & Pipeline Execution Entry Points ---

RULES = (
    CommercialRule(("invalid_date_range",), "quotation", _quotation_dates),
    CommercialRule(("non_positive_price", "invalid_pack_units"), "line", _price_and_pack),
    CommercialRule(("negative_moq", "below_minimum_order_quantity"), "line", _minimum_order_quantity),
    CommercialRule(("invalid_percentage",), "line", _percentage_adjustments),
    CommercialRule(("overlapping_price_tier",), "line", _price_tiers),
)


def validate_and_derive(quotation: CanonicalQuotation) -> CanonicalQuotation:
    """Apply deterministic PRD rules to canonical data.

    Evaluates both quotation-level and line-level commercial rules, updating the
    quotation's `review_issues` array with actionable errors.

    Args:
        quotation: The canonical quotation to validate and derive.

    Returns:
        The updated canonical quotation with derived pricing and populated review issues.
    """
    rule_codes = {code for rule in RULES for code in rule.codes}
    quotation.review_issues = [issue for issue in quotation.review_issues if issue.code not in rule_codes]
    for rule in RULES:
        if rule.scope == "quotation":
            quotation.review_issues.extend(rule.evaluate(RuleContext(quotation)))
            continue
        for index, line in enumerate(quotation.line_items):
            quotation.review_issues.extend(rule.evaluate(RuleContext(quotation, line, index)))
    return quotation


def apply_commercial_rules(quotation: CanonicalQuotation) -> CanonicalQuotation:
    """Compatibility alias for validate_and_derive."""
    return validate_and_derive(quotation)


# --- Section 7: Human Review Patch Parsing Helpers ---


def decimal_patch(value: object) -> Decimal:
    """Parse and validate arbitrary user-supplied review input into a finite Decimal.

    Args:
        value: Raw scalar input from user patch payload.

    Returns:
        Validated Decimal instance.

    Raises:
        ValueError: If input cannot be parsed into a finite Decimal.
    """
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Commercial numeric corrections must be valid decimals.") from error
    if not decimal_value.is_finite():
        raise ValueError("Commercial numeric corrections must be finite decimals.")
    return decimal_value
