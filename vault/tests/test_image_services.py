from unittest.mock import patch
from django.conf import settings

from vault.services.image_services import get_card_image_url_or_placeholder


@patch("vault.services.image_services.fetch_tcgdex_card_image_data")
def test_get_card_image_returns_image_when_present(mock_fetch):
    mock_fetch.return_value = {"image_url": "https://example.com/img.png"}

    result = get_card_image_url_or_placeholder(
        card_name="Pikachu",
        set_name="151",
        card_number="58",
    )

    assert result == "https://example.com/img.png"


@patch("vault.services.image_services.fetch_tcgdex_card_image_data")
def test_get_card_image_returns_placeholder_when_missing(mock_fetch):
    mock_fetch.return_value = {}

    result = get_card_image_url_or_placeholder(
        card_name="Pikachu",
        set_name="151",
        card_number="58",
    )

    assert result == settings.CARD_IMAGE_PLACEHOLDER_URL


@patch("vault.services.image_services.fetch_tcgdex_card_image_data")
def test_get_card_image_returns_placeholder_on_exception(mock_fetch):
    mock_fetch.side_effect = Exception("API down")

    result = get_card_image_url_or_placeholder(
        card_name="Pikachu",
        set_name="151",
        card_number="58",
    )

    assert result == settings.CARD_IMAGE_PLACEHOLDER_URL
