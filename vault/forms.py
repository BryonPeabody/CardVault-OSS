from django import forms
from .models import Card
from vault.utils import fetch_card_price, extract_card_price


class CardForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cleaned_price = None

    class Meta:
        model = Card
        fields = ["card_name", "set_name", "language", "card_number", "condition"]

    def clean(self):
        """
        Validates card pricing data against the external price API.

        Ensures the submitted card name, set, and card number can be matched
        to a valid pricing entry before allowing form submission.

        Caches parsed pricing data on self.cleaned_price so the view can
        reuse the API result without making a second request.

        Uses:
        - fetch_card_price() (utils.py)
        - extract_card_price() (utils.py)
        """

        cleaned = super().clean()
        card_name = cleaned.get("card_name")
        set_name = cleaned.get("set_name")
        card_number = cleaned.get("card_number")

        # Let required-field validation happen first
        if not (card_name and set_name and card_number):
            return cleaned

        data = fetch_card_price(card_name, set_name)
        if "error" in data:
            raise forms.ValidationError(
                "Price lookup failed (service unavailable or rate-limited). Please try again."
            )

        parsed = extract_card_price(data, card_number)
        if "error" in parsed:
            # Attach to card_name so it feels like “spelling”
            self.add_error(
                "card_name",
                "Could not find pricing for this card. Double-check spelling, set, and card number.",
            )
            # Still return cleaned; form will be invalid due to add_error
            return cleaned

        # Cache parsed result so the view can reuse it without another API call
        self.cleaned_price = parsed  # e.g. {"price": ..., "price_date": ...}
        return cleaned


class CardUpdateForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ["condition"]
