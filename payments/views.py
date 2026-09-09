from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from core.utils import parse_json_body
from .models import Transaction


class TopUpView(LoginRequiredMixin, View):
    """Balance top-up request (requires admin approval for manual method)."""

    def post(self, request):
        data, err = parse_json_body(request)
        if err:
            return err

        amount = data.get('amount', 0)
        method = data.get('method', 'manual')

        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Noto\'g\'ri summa'}, status=400)

        if amount <= 0:
            return JsonResponse({'error': 'Summa 0 dan katta bo\'lishi kerak'}, status=400)

        if method not in ('payme', 'click', 'manual'):
            return JsonResponse({'error': 'Noto\'g\'ri to\'lov usuli'}, status=400)

        tx = Transaction.objects.create(
            user=request.user,
            amount=amount,
            method=method,
            status='pending',
            description='Balans to\'ldirish',
        )

        return JsonResponse({
            'status': 'pending',
            'transaction_id': tx.id,
            'message': 'So\'rovingiz qabul qilindi. Admin tasdiqlashidan keyin balans to\'ldiriladi.',
        })
