import logging
from decimal import Decimal

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from vault.models import CatalogCard

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Import Pokémon card catalog data from the Pokémon Price Tracker API
    into the CatalogCard model for a single set.

    This command fetches all cards for a provided set ID using the
    `fetchAllInSet=true` API parameter and stores or updates catalog
    records using stable external identifiers.

    Cards are matched using `price_tracker_card_id` to ensure the
    importer is idempotent and safe to rerun without creating duplicates.

    Imported data includes:
    - Card identity data (name, set, card number)
    - External API identifiers
    - Image URLs
    - Variant and printing metadata
    - Cached market pricing data
    - Artist and rarity metadata

    Example usage:
        python manage.py import_ppt_set --set-id 23821
    """

    help = "Import CatalogCard records for one Pokémon set from Pokémon Price Tracker."

    API_URL = "https://www.pokemonpricetracker.com/api/v2/cards"

    def add_arguments(self, parser):
        parser.add_argument(
            "--set-id",
            type=int,
            required=True,
            help="Pokémon Price Tracker set ID to import.",
        )

    def handle(self, *args, **options):
        set_id = options["set_id"]
        token = getattr(settings, "CARDVAULT_API_KEY", None)

        if not token:
            raise CommandError("Missing CARDVAULT_API_KEY in settings.")

        params = {
            "language": "english",
            "setId": set_id,
            "includeHistory": "false",
            "includeEbay": "false",
            "includeBoth": "false",
            "fetchAllInSet": "true",
            "sortBy": "cardNumber",
            "sortOrder": "asc",
        }

        headers = {
            "Authorization": f"Bearer {token}",
        }

        self.stdout.write(f"Fetching catalog cards for setId={set_id}...")

        try:
            response = requests.get(
                self.API_URL,
                params=params,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Failed to fetch catalog cards for setId=%s", set_id)
            raise CommandError(f"API request failed: {exc}") from exc

        payload = response.json()

        cards = payload.get("data") or payload.get("cards") or []

        if not cards:
            raise CommandError("No cards found in API response. Check response shape.")

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for item in cards:
            price_tracker_card_id = item.get("id")

            if not price_tracker_card_id:
                skipped_count += 1
                logger.warning("Skipping card without id: %s", item)
                continue

            prices = item.get("prices") or {}

            _, created = CatalogCard.objects.update_or_create(
                price_tracker_card_id=price_tracker_card_id,
                defaults={
                    "name": item.get("name") or "",
                    "set_name": item.get("setName") or "",
                    "set_code": (item.get("externalCatalogId") or "").split("-")[0],
                    "card_number": item.get("cardNumber") or "",
                    "tcgplayer_id": item.get("tcgPlayerId") or "",
                    "tcgplayer_url": item.get("tcgPlayerUrl") or "",
                    "rarity": item.get("rarity") or "",
                    "image_url": item.get("imageCdnUrl800")
                    or item.get("imageCdnUrl400")
                    or item.get("imageCdnUrl200")
                    or item.get("imageUrl")
                    or "",
                    "artist": item.get("artist") or "",
                    "printings_available": item.get("printingsAvailable") or [],
                    "variants": item.get("variants") or {},
                    "market_price": (
                        Decimal(str(prices["market"]))
                        if prices.get("market") is not None
                        else None
                    ),
                    "low_price": (
                        Decimal(str(prices["low"]))
                        if prices.get("low") is not None
                        else None
                    ),
                    "price_last_updated": (
                        parse_datetime(prices["lastUpdated"])
                        if prices.get("lastUpdated")
                        else None
                    ),
                    "regulation_mark": "",
                    "standard_legal": None,
                    "expanded_legal": None,
                    "price_tracker_raw_data": item,
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        metadata = payload.get("metadata", {})
        api_calls = (
            metadata.get("apiCallsConsumed", {}).get("total")
            if isinstance(metadata, dict)
            else None
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete for setId={set_id}: "
                f"{created_count} created, "
                f"{updated_count} updated, "
                f"{skipped_count} skipped."
            )
        )
        if api_calls and api_calls > 60:
            self.stdout.write(
                self.style.WARNING(
                    "This import consumed more than 60 API credits. "
                    "Wait before importing another large set."
                )
            )

        if api_calls is not None:
            self.stdout.write(f"API credits consumed: {api_calls}")
