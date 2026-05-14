from django.conf import settings
import logging
from django.utils import timezone
from decimal import Decimal

from vault.utils import fetch_card_price, extract_card_price
from vault.models import Card, PriceSnapshot
from vault.services.image_services import get_card_image_url_or_placeholder

logger = logging.getLogger(__name__)


def create_initial_snapshot(card):
    if card.value_usd is None:
        return False

    today = timezone.localdate()
    PriceSnapshot.objects.update_or_create(
        card=card,
        as_of_date=today,
        defaults={
            "price": card.value_usd,
            "source": "pokemonpricetracker",
            "currency": "USD",
        },
    )
    return True


def refresh_prices_for_user(user) -> int:
    today = timezone.localdate()
    cards = Card.objects.filter(user=user)

    updated = 0
    skipped_current = 0
    image_healed = 0
    fetch_failed = 0
    extract_failed = 0

    logger.info(
        "Starting price refresh for user_id=%s card_count=%s", user.id, cards.count()
    )

    for card in cards:
        # Attempt to heal any missing images
        if not card.image_url or card.image_url == settings.CARD_IMAGE_PLACEHOLDER_URL:
            new_url = get_card_image_url_or_placeholder(
                card_name=card.card_name,
                set_name=card.set_name,
                card_number=card.card_number,
            )

            if (
                new_url != settings.CARD_IMAGE_PLACEHOLDER_URL
                and new_url != card.image_url
            ):
                card.image_url = new_url
                card.save(update_fields=["image_url"])
                image_healed += 1
                logger.info(
                    "Healed missing image for card_id=%s name=%s set=%s number=%s",
                    card.id,
                    card.card_name,
                    card.set_name,
                    card.card_number,
                )
            else:
                logger.warning(
                    "Image healing failed for card_id=%s name=%s set=%s number=%s",
                    card.id,
                    card.card_name,
                    card.set_name,
                    card.card_number,
                )

        if card.price_last_updated == today:
            skipped_current += 1
            continue

        data = fetch_card_price(card.card_name, card.set_name)

        if "error" in data:
            fetch_failed += 1
            logger.warning(
                "Fetch card price failed for card_id=%s name=%s set=%s number=%s status=%s error=%s",
                card.id,
                card.card_name,
                card.set_name,
                card.card_number,
                data.get("status"),
                data.get("error"),
            )
            continue

        result = extract_card_price(data, card.card_number)

        if "error" in result:
            extract_failed += 1
            logger.warning(
                "Price extract failed for card_id=%s name=%s set=%s number=%s error=%s",
                card.id,
                card.card_name,
                card.set_name,
                card.card_number,
                result.get("error"),
            )
            continue

        price = Decimal(str(result["price"]))

        PriceSnapshot.objects.update_or_create(
            card=card,
            as_of_date=today,
            defaults={
                "price": price,
                "source": "pokemonpricetracker",
                "currency": "USD",
            },
        )

        card.value_usd = price
        card.price_last_updated = today
        card.save(update_fields=["value_usd", "price_last_updated"])

        updated += 1

    logger.info(
        "Finished price refresh for user_id=%s updated=%s skipped_current=%s image_healed=%s fetch_failed=%s extract_failed=%s",
        user.id,
        updated,
        skipped_current,
        image_healed,
        fetch_failed,
        extract_failed,
    )

    return updated
