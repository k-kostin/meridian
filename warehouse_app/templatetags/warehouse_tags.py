from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def quantity(value, places=3):
    if value in (None, ""):
        return ""
    try:
        places = int(places)
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value

    quantizer = Decimal("1").scaleb(-places)
    normalized = decimal_value.quantize(quantizer)
    return f"{normalized:.{places}f}".replace(".", ",")
