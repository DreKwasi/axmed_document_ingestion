"""Deterministic reconciliation of explicit email price statements."""

import re
from decimal import Decimal, InvalidOperation

from app.extraction.contracts import CanonicalQuotation

ITEM_BLOCK_PATTERN = re.compile(
    r"(?ms)^\s*\d+[.)]\s*(?P<item>.*?)(?=^\s*\d+[.)]\s|\Z)"
)
PRICE_PATTERN = re.compile(
    r"(?im)^\s*price\s*:\s*(?:[A-Z]{3}\s*)?(?P<amount>\d+(?:[.,]\d+)?)\s+per\s+(?P<uom>[a-z]+)\b"
)


def reconcile_email_price_uoms(quotation: CanonicalQuotation, body_text: str) -> CanonicalQuotation:
    """Preserve an explicit source UOM when it confirms an extracted quoted amount.

    This intentionally does not infer a UOM from packaging. It only repairs a
    model-normalized UOM when an item's source block states ``Price: amount per
    uom`` and its amount exactly agrees with the structured extraction.
    """

    for line in quotation.line_items:
        name = (line.product.trade_name or "").casefold()
        amount = line.pricing.quoted_price.amount or line.pricing.pack_price
        if not name or amount is None:
            continue
        for block in ITEM_BLOCK_PATTERN.finditer(body_text):
            if name not in block.group("item").casefold():
                continue
            price = PRICE_PATTERN.search(block.group("item"))
            if price is None:
                continue
            try:
                source_amount = Decimal(price.group("amount").replace(",", "."))
            except InvalidOperation:
                continue
            if source_amount == amount:
                line.pricing.quoted_price.uom = price.group("uom").casefold()
            break
    return quotation
