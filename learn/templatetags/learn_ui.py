from django import template
from django.utils.html import format_html

register = template.Library()

# Stories keep their emoji in the course data (the mobile app shows it); the
# site draws the matching line icon instead.
STORY_ICONS = {
    '✉': 'mail', '🚆': 'train-front', '🖋': 'pen-tool', '🕌': 'landmark', '📱': 'smartphone', '💼': 'briefcase',
    '💡': 'lightbulb', '🐱': 'cat', '🏫': 'school', '🏘': 'house', '🏃': 'footprints', '🎯': 'target',
    '🎧': 'headphones', '🎂': 'cake', '🍚': 'soup', '🍉': 'cherry', '🌐': 'globe', '🌊': 'waves', '❄': 'snowflake',
}


@register.filter
def story_icon(emoji):
    name = STORY_ICONS.get((emoji or '').replace('️', ''), 'book-open')
    return format_html('<i class="lc-{}"></i>', name)
