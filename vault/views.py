# Standard library
from datetime import timedelta
from decimal import Decimal
import logging

# Django
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    UpdateView,
    DeleteView,
    ListView,
    TemplateView,
)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

# Local app
from .models import Card, PriceSnapshot
from .forms import CardForm, CardUpdateForm
from vault.services.image_services import get_card_image_url_or_placeholder
from vault.services.price_services import (
    refresh_prices_for_user,
    create_initial_snapshot,
)

logger = logging.getLogger(__name__)


class CardCreateView(LoginRequiredMixin, CreateView):
    model = Card
    form_class = CardForm
    template_name = "vault/card_form.html"
    success_url = reverse_lazy("card-list")

    def form_valid(self, form):
        form.instance.user = self.request.user

        form.instance.image_url = get_card_image_url_or_placeholder(
            card_name=form.instance.card_name,
            set_name=form.instance.set_name,
            card_number=form.instance.card_number,
        )

        parsed = getattr(form, "cleaned_price", None)
        if parsed and "price" in parsed:
            form.instance.value_usd = parsed["price"]
            form.instance.price_last_updated = parsed["price_date"]

        response = super().form_valid(form)
        create_initial_snapshot(self.object)
        return response


class CardListView(LoginRequiredMixin, ListView):
    model = Card
    template_name = "vault/card_list.html"
    context_object_name = "cards"

    def get_queryset(self):
        qs = Card.objects.filter(user=self.request.user)

        sort = self.request.GET.get("sort", "value_desc")

        if sort == "value_asc":
            return qs.order_by("value_usd", "card_name")
        elif sort == "value_desc":
            return qs.order_by("-value_usd", "card_name")
        elif sort == "set_asc":
            return qs.order_by("set_name", "card_number")
        elif sort == "set_desc":
            return qs.order_by("-set_name", "card_number")
        else:
            return qs.order_by("-value_usd", "card_name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["current_sort"] = self.request.GET.get("sort", "value_desc")

        # Total value across the user's entire collection
        user_cards = Card.objects.filter(user=self.request.user)
        aggregates = user_cards.aggregate(
            total=Coalesce(Sum("value_usd"), Decimal("0"))
        )

        context["total_value_usd"] = aggregates["total"]

        return context


class CardUpdateView(LoginRequiredMixin, UpdateView):
    model = Card
    form_class = CardUpdateForm
    template_name = "vault/card_form.html"
    success_url = reverse_lazy("card-list")

    def get_queryset(self):
        return Card.objects.filter(user=self.request.user)

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class CardDeleteView(LoginRequiredMixin, DeleteView):
    model = Card
    template_name = "vault/card_delete.html"
    success_url = reverse_lazy("card-list")

    def get_queryset(self):
        return Card.objects.filter(user=self.request.user)


class RegisterView(CreateView):
    form_class = UserCreationForm
    template_name = "vault/register.html"
    success_url = reverse_lazy("login")


# ----------------------- PriceSnapshot Views --------------------


@login_required
def collection_value_series(request):
    range_key = request.GET.get("range", "30d").lower()
    today = timezone.localdate()

    if range_key == "30d":
        start = today - timedelta(days=29)
    elif range_key == "90d":
        start = today - timedelta(days=89)
    elif range_key in ("1y", "365d", "year"):
        start = today - timedelta(days=364)
    elif range_key == "all":
        start = None
    else:
        # fallback
        start = today - timedelta(days=29)

    qs = PriceSnapshot.objects.filter(card__user=request.user)

    if start is not None:
        qs = qs.filter(as_of_date__gte=start)

    rows = qs.values("as_of_date").annotate(total=Sum("price")).order_by("as_of_date")

    data = [
        {"date": r["as_of_date"].isoformat(), "value": str(r["total"] or 0)}
        for r in rows
    ]

    return JsonResponse(data, safe=False)


class CollectionGraphView(LoginRequiredMixin, TemplateView):
    template_name = "vault/collection_graph.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["range"] = self.request.GET.get("range", "30d")
        return ctx


@login_required
def refresh_prices(request):
    if request.method == "POST":
        refresh_prices_for_user(request.user)
    return redirect("card-list")


# ----------------------------------test helper


def health_check(request):
    return HttpResponse("OK", status=200)
