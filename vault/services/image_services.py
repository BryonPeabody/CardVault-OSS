import logging
from django.conf import settings
from vault.utils import fetch_tcgdex_card_image_data

logger = logging.getLogger(__name__)


def get_card_image_url_or_placeholder(
    *, card_name: str, set_name: str, card_number: str
) -> str:
    """
    Returns a valid card image URL or the configured placeholder image.

    Wraps TCGdex image fetching with graceful fallback behavior so callers
    do not need to handle missing images or API failures themselves.

    Uses:
    - fetch_tcgdex_card_image_data() (utils.py)

    Called by:
    - CardCreateView (views.py)
    - refresh_prices_for_user() (services/price_services.py)
    """

    try:
        data = fetch_tcgdex_card_image_data(card_name, set_name, card_number)
        image_url = (data or {}).get("image_url")
        if image_url:
            return image_url

        logger.warning(
            "Image missing from API for %s | %s | #%s", card_name, set_name, card_number
        )
    except Exception:
        logger.exception(
            "Image fetch failed for %s | %s | #%s", card_name, set_name, card_number
        )

    return settings.CARD_IMAGE_PLACEHOLDER_URL
