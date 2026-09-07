"""PRD commercial validation and derivation."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.domain.contracts import CanonicalQuotation, LineItem, ReviewIssue


@dataclass(frozen=True)
class RuleContext:
    quotation: CanonicalQuotation
    line: LineItem | None = None
    line_index: int | None = None

    def issue(self, code: str, field: str, message: str) -> ReviewIssue:
        path = field if self.line_index is None else f"line_items[{self.line_index}].{field}"
        return ReviewIssue(field_path=path, code=code, message=message, severity="error")


RuleEvaluator = Callable[[RuleContext], list[ReviewIssue]]


@dataclass(frozen=True)
class CommercialRule:
    codes: tuple[str, ...]
    scope: str
    evaluate: RuleEvaluator


def _quotation_dates(context: RuleContext) -> list[ReviewIssue]:
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


def _price_and_pack(context: RuleContext) -> list[ReviewIssue]:
    assert context.line is not None
    pricing = context.line.pricing
    units = context.line.packaging.units_per_pack
    if pricing.pack_price is None:
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


def _minimum_order_quantity(context: RuleContext) -> list[ReviewIssue]:
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


def _percentage_adjustments(context: RuleContext) -> list[ReviewIssue]:
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


RULES = (
    CommercialRule(("invalid_date_range",), "quotation", _quotation_dates),
    CommercialRule(("non_positive_price", "invalid_pack_units"), "line", _price_and_pack),
    CommercialRule(("negative_moq", "below_minimum_order_quantity"), "line", _minimum_order_quantity),
    CommercialRule(("invalid_percentage",), "line", _percentage_adjustments),
    CommercialRule(("overlapping_price_tier",), "line", _price_tiers),
)


def validate_and_derive(quotation: CanonicalQuotation) -> CanonicalQuotation:
    """Apply deterministic PRD rules to canonical data.

    New canonical fields do not change this module unless they introduce a
    deterministic calculation or constraint. Supplier field aliases stay in
    schema mapping.
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
    """Compatibility name while callers move to the validation seam."""

    return validate_and_derive(quotation)


def decimal_patch(value: object) -> Decimal:
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Commercial numeric corrections must be valid decimals.") from error
    if not decimal_value.is_finite():
        raise ValueError("Commercial numeric corrections must be finite decimals.")
    return decimal_value
