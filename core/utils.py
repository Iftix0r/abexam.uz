import json
from datetime import date, timedelta

from django.db.models.functions import TruncDate, TruncMonth
from django.http import JsonResponse
from django.utils import timezone


_IMAGE_TYPE_LABELS = {
    'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP', 'image/svg+xml': 'SVG',
}


def validate_image_upload(file, max_mb, allowed_types):
    """Validate an uploaded image's size and content type.

    Returns an Uzbek error message if invalid, or None if the file is OK.
    """
    if file.size > max_mb * 1024 * 1024:
        return f"Rasm hajmi {max_mb}MB dan oshmasligi kerak"
    if file.content_type not in allowed_types:
        names = ', '.join(_IMAGE_TYPE_LABELS.get(t, t) for t in allowed_types)
        return f"Faqat {names} formatlar qabul qilinadi"
    return None


def parse_json_body(request, error_message="Noto'g'ri so'rov", ok_field=False):
    """Parse `request.body` as JSON.

    Returns (data, None) on success, or (None, response) with a ready-made
    400 JsonResponse the caller should return immediately on failure:

        data, err = parse_json_body(request)
        if err:
            return err
    """
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, TypeError, ValueError):
        payload = {'error': error_message}
        if ok_field:
            payload['ok'] = False
        return None, JsonResponse(payload, status=400)


def daily_series(queryset, date_field, days, agg):
    """Bucket `queryset` into daily values for the last `days` days (oldest
    first) in a single query, instead of one query per day.

    `agg` is a keyword aggregate expression, e.g. Count('id') or Sum('amount').
    """
    now = timezone.now()
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        queryset.filter(**{f'{date_field}__gte': start})
        # Clear any ordering the caller's queryset carries — left in place,
        # Django folds the order-by field into GROUP BY too, splitting each
        # row into its own bucket instead of grouping by day.
        .order_by()
        .annotate(bucket=TruncDate(date_field))
        .values('bucket')
        .annotate(value=agg)
    )
    by_bucket = {row['bucket']: row['value'] for row in rows}
    labels, values = [], []
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        labels.append(day.strftime('%d %b'))
        values.append(by_bucket.get(day) or 0)
    return labels, values


def monthly_series(queryset, date_field, months, agg):
    """Bucket `queryset` into monthly values for the last `months` calendar
    months (oldest first) in a single query.

    Steps back by real calendar months (not `i * 30` days, which drifts
    across months of different lengths), so the returned month for i=5 is
    always exactly 5 calendar months before the current one.
    """
    now = timezone.now()
    rows = (
        queryset.order_by()
        .annotate(bucket=TruncMonth(date_field))
        .values('bucket')
        .annotate(value=agg)
    )
    by_bucket = {(row['bucket'].year, row['bucket'].month): row['value'] for row in rows if row['bucket']}

    labels, values = [], []
    for i in range(months - 1, -1, -1):
        total_months = now.year * 12 + (now.month - 1) - i
        y, m = divmod(total_months, 12)
        m += 1
        labels.append(date(y, m, 1).strftime('%b %Y'))
        values.append(by_bucket.get((y, m)) or 0)
    return labels, values
