"""Exact money/units. Decimal presentation; rational allocation, never float."""
from decimal import Decimal, localcontext, ROUND_HALF_UP
from fractions import Fraction

class InputError(ValueError):
    pass

def Q(value):
    if isinstance(value, bool) or isinstance(value, float):
        raise InputError('Use decimal strings, Decimal, integers or Fraction; float is forbidden')
    if isinstance(value, Fraction):
        return value
    try:
        d = Decimal(value)
        if not d.is_finite():
            raise InputError('Non-finite number')
        return Fraction(d)
    except (ValueError, TypeError, ArithmeticError) as e:
        raise InputError(f'Invalid exact number: {value!r}') from e

def dec(value, precision=80):
    with localcontext() as ctx:
        ctx.prec = precision
        if isinstance(value, Fraction):
            return Decimal(value.numerator) / Decimal(value.denominator)
        return Decimal(value)

def money(value, places=2):
    with localcontext() as ctx:
        ctx.prec = 80
        return format(dec(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP), 'f')

def encode(value):
    from datetime import date
    from dataclasses import is_dataclass, asdict
    if isinstance(value, Fraction):
        return {'exact': f'{value.numerator}/{value.denominator}', 'decimal': str(dec(value)), 'rounded_whole_if_monetary': money(value, 0)}
    if isinstance(value, Decimal):
        return {'decimal': str(value), 'rounded_whole_if_monetary': money(value, 0)}
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return encode(asdict(value))
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value
