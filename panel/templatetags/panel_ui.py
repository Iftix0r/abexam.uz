"""Small presentation helpers shared by the panel templates."""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def som(value):
    """2200000 -> '2 200 000' (non-breaking spaces, so a sum never wraps)."""
    try:
        number = int(round(Decimal(str(value))))
    except (InvalidOperation, TypeError, ValueError):
        return '0'
    return f'{number:,}'.replace(',', '\u00a0')


@register.simple_tag(takes_context=True)
def qs(context, **changes):
    """The current query string with `changes` applied: `{% qs filter='staff' %}`.

    An empty value drops the parameter. The page number is always dropped
    unless it is one of the changes, because a new filter starts on page 1.
    """
    params = context['request'].GET.copy()
    params.pop('page', None)
    for key, value in changes.items():
        params.pop(key, None)
        if value not in ('', None):
            params[key] = value
    encoded = params.urlencode()
    return f'?{encoded}' if encoded else '?'


@register.simple_tag
def page_numbers(page):
    return page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
