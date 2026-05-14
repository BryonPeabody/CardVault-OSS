from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.utils import timezone


class Card(models.Model):
    CONDITION_CHOICES = [
        ("M", "Mint"),
        ("NM", "Near Mint"),
        ("LP", "Lightly Played"),
        ("MP", "Moderately Played"),
        ("HP", "Heavily Played"),
        ("D", "Damaged"),
    ]

    LANGUAGE_CHOICES = [
        ("EN", "English"),
        ("JP", "Japanese"),
        ("FR", "French"),
        ("DE", "German"),
        # add more as needed
    ]
    SET_CHOICES = [
        ("Scarlet & Violet Base", "Scarlet & Violet Base"),
        ("Paldea Evolved", "Paldea Evolved"),
        ("Obsidian Flames", "Obsidian Flames"),
        ("151", "151"),
        ("Paradox Rift", "Paradox Rift"),
        ("Paldean Fates", "Paldean Fates"),
        ("Temporal Forces", "Temporal Forces"),
        ("Twilight Masquerade", "Twilight Masquerade"),
        ("Shrouded Fable", "Shrouded Fable"),
        ("Stellar Crown", "Stellar Crown"),
        ("Surging Sparks", "Surging Sparks"),
        ("Prismatic Evolutions", "Prismatic Evolutions"),
        ("Journey Together", "Journey Together"),
        ("Destined Rivals", "Destined Rivals"),
        ("Black Bolt", "Black Bolt"),
        ("White Flare", "White Flare"),
        ("Silver Tempest", "Silver Tempest"),
        ("Crown Zenith", "Crown Zenith"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    card_name = models.CharField(max_length=50)
    set_name = models.CharField(max_length=25, choices=SET_CHOICES)
    language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES)
    card_number = models.CharField(max_length=3)
    condition = models.CharField(max_length=2, choices=CONDITION_CHOICES)

    image_url = models.URLField(blank=True, null=True)
    value_usd = models.DecimalField(
        max_digits=8, decimal_places=2, blank=True, null=True
    )
    price_last_updated = models.DateField(blank=True, null=True)

    def save(self, *args, **kwargs):
        """
        Normalizes card names before saving.

        Strips leading/trailing whitespace so duplicate checks and display
        are not affected by accidental user input spacing.
        """
        self.card_name = self.card_name.strip()
        super().save(*args, **kwargs)

    def clean(self):
        """
        Prevents a user from adding the same card to their vault more than once.

        Treats cards as duplicates when the same user already has a card with
        the same name, set, and card number. Excludes self.pk so existing cards
        can be edited without triggering a false duplicate error.

        Called by:
        - Django model validation
        - CardForm validation/save flow
        """
        if not self.user_id:
            return
        if (
            Card.objects.filter(
                user=self.user,
                card_name__iexact=self.card_name,
                set_name__iexact=self.set_name,
                card_number=self.card_number,
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError("You already have this card in your vault.")

    def __str__(self):
        return f"{self.card_name} ({self.set_name} #{self.card_number})"


class PriceSnapshot(models.Model):
    """
    Stores historical daily pricing data for a card.

    Intended for:
    - collection value history
    - future graphing/trend features
    - preserving historical prices independently from Card.value_usd

    Enforces one snapshot per card per day.
    """

    card = models.ForeignKey(
        "Card", on_delete=models.CASCADE, related_name="price_snapshots"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    as_of_date = models.DateField(default=timezone.localdate)
    source = models.CharField(max_length=50, blank=True, default="")
    currency = models.CharField(max_length=10, blank=True, default="USD")

    class Meta:
        indexes = [
            models.Index(fields=["card", "-as_of_date"]),
        ]
        # Only allow one price per day (hopefully help with rate limiting)
        constraints = [
            models.UniqueConstraint(
                fields=["card", "as_of_date"], name="uniq_card_price_per_day"
            )
        ]

    def __str__(self):
        return f"{self.card.card_name} - ${self.price} on {self.as_of_date}"
