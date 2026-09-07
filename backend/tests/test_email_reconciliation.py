from decimal import Decimal

from app.domain.contracts import CanonicalQuotation, LineItem, Pricing, Product, QuotedPrice
from app.domain.email_reconciliation import reconcile_email_price_uoms


def test_explicit_email_price_uom_overrides_model_normalization_when_amount_matches():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                product=Product(trade_name="Zincora 20"),
                pricing=Pricing(quoted_price=QuotedPrice(amount=Decimal("1.55"), uom="pack")),
            )
        ]
    )

    result = reconcile_email_price_uoms(
        quotation,
        "2) Zincora 20 (zinc sulfate 20 mg)\n   Price: 1.55 per box of 100\n",
    )

    assert result.line_items[0].pricing.quoted_price.uom == "box"


def test_email_price_uom_is_not_changed_when_the_source_amount_disagrees():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                product=Product(trade_name="Zincora 20"),
                pricing=Pricing(quoted_price=QuotedPrice(amount=Decimal("1.60"), uom="pack")),
            )
        ]
    )

    result = reconcile_email_price_uoms(quotation, "2) Zincora 20\nPrice: 1.55 per box of 100\n")

    assert result.line_items[0].pricing.quoted_price.uom == "pack"


def test_email_price_uom_reconciles_a_model_pack_price_with_no_quoted_price():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                product=Product(trade_name="Zincora 20"),
                pricing=Pricing(pack_price=Decimal("1.55")),
            )
        ]
    )

    result = reconcile_email_price_uoms(quotation, "2) Zincora 20\nPrice: 1.55 per box of 100\n")

    assert result.line_items[0].pricing.quoted_price.uom == "box"
