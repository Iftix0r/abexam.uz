from decimal import Decimal

from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F
from django.utils.html import escape
from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView
from core.models import PromoCode, SiteSettings
from core.utils import notify_staff_work, parse_json_body, site_link
from . import premium
from .models import PremiumPurchase, Transaction


class TopUpView(LoginRequiredMixin, View):
    """Balance top-up request (requires admin approval for manual method)."""

    def post(self, request):
        data, err = parse_json_body(request)
        if err:
            return err

        amount = data.get('amount', 0)
        method = data.get('method', 'manual')

        try:
            amount = Decimal(str(amount))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Noto\'g\'ri summa'}, status=400)

        if amount <= 0:
            return JsonResponse({'error': 'Summa 0 dan katta bo\'lishi kerak'}, status=400)

        if method not in ('payme', 'click', 'manual'):
            return JsonResponse({'error': 'Noto\'g\'ri to\'lov usuli'}, status=400)

        description = "Balans to'ldirish"
        promo_code = str(data.get('promo_code', '')).strip().upper()
        if promo_code:
            promo = PromoCode.objects.filter(code=promo_code).first()
            if not promo or not promo.is_valid:
                return JsonResponse({'error': "Promo kod yaroqsiz yoki muddati o'tgan"}, status=400)
            # Atomic claim so two concurrent redemptions of the last
            # remaining use can't both succeed (max_uses overrun).
            claimed = PromoCode.objects.filter(
                pk=promo.pk, used_count__lt=F('max_uses'),
            ).update(used_count=F('used_count') + 1)
            if not claimed:
                return JsonResponse({'error': "Promo kod limiti tugagan"}, status=400)
            bonus = (amount * promo.discount_percent / 100) + promo.discount_amount
            amount += bonus
            description += f" (promo: {promo_code}, +{bonus:.0f} bonus)"

        tx = Transaction.objects.create(
            user=request.user,
            amount=amount,
            method=method,
            status='pending',
            description=description,
        )
        notify_staff_work(
            f"💳 <b>To'lov tasdiqlash kutmoqda</b>\n"
            f"👤 {escape(request.user.display_name)} (@{escape(request.user.username)})\n"
            f"💰 {amount:,.0f} so'm · {tx.get_method_display()}",
            [[("💳 Tasdiqlash", site_link('/panel/transactions/?status=pending'))]],
        )

        return JsonResponse({
            'status': 'pending',
            'transaction_id': tx.id,
            'amount': float(amount),
            'message': 'So\'rovingiz qabul qilindi. Admin tasdiqlashidan keyin balans to\'ldiriladi.',
        })


class PremiumView(LoginRequiredMixin, TemplateView):
    template_name = 'premium.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings_obj = SiteSettings.get()
        user = self.request.user
        context.update({
            'price': settings_obj.premium_price, 'days': settings_obj.premium_days,
            'can_buy': user.balance >= settings_obj.premium_price,
            'short_by': max(settings_obj.premium_price - user.balance, 0),
            'transactions': Transaction.objects.filter(user=user)[:8],
            'purchases': PremiumPurchase.objects.filter(user=user)[:5],
        })
        return context


class PremiumBuyView(LoginRequiredMixin, View):
    def post(self, request):
        error = premium.buy(request.user)
        if error:
            messages.error(request, error)
        else:
            messages.success(request, "AB Premium faollashtirildi")
        return redirect('premium')
