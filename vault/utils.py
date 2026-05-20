import requests
from django.conf import settings
import logging

from .constants import IMAGE_SET_MAP, PRICE_SET_MAP


logger = logging.getLogger(__name__)


def _pad_card_number_for_image(n: str | int) -> str:
    """
    TCGdex image id's use a 3-digit card number: ie, '006'
    V2 of pokepricetracker endpoints also use this format for endpoints,
    now using this helper for fetch_card_data (image) and extract_card_price (price)
    """
    s = str(n).strip()
    return s.zfill(3)


def fetch_tcgdex_card_image_data(
    card_name: str, set_name: str, card_number: str | int | None = None
):
    """
    Fetches card image metadata from the TCGdex API.

    Uses IMAGE_SET_MAP normalization to convert internal set names
    into TCGdex-compatible set codes. Filters API results by set code,
    card number, and image availability before returning a single match.

    Intended specifically for image retrieval workflows.

    Called by:
    - get_card_image_url_or_placeholder() (services/image_services.py)

    Used by:
    - refresh_prices_for_user() (services/price_services.py)

    Returns:
        dict containing:
        - name
        - image_url
        - card_id

        or an error dict on failure.
    """
    # use official set name and filter through map in constants to get api set_code
    set_code = IMAGE_SET_MAP.get(set_name)
    # graceful exit if set_code not found
    if not set_code:
        logger.error("Missing IMAGE_SET_MAP code for set '%s'", set_name)
        return {"error": "Invalid set"}
    # hit api to grab a json list of cards with the name from model
    try:
        url = "https://api.tcgdex.net/v2/en/cards"
        # safe timeout after 10 second if no data received
        resp = requests.get(url, params={"name": card_name}, timeout=10)
        # throws exception on bad request so we don't save a 404 page or the like
        resp.raise_for_status()
        # put data in json list if data is good
        data = resp.json() or []  # list
    except Exception as e:
        logger.exception("TCGdex request failed: %s", e)
        return {"error": "Service unavailable"}
    # use list comprehension to save only cards that have that name and also the correct set_code
    prefix = f"{set_code.lower()}-"
    candidates = [c for c in data if c.get("id", "").lower().startswith(prefix)]
    # more list comprehension to save from those only the cards with also a proper card_number
    if card_number:
        # calling this function ensures the card number matches the json data from this api
        # ie, '006' rather than '6'
        num3 = _pad_card_number_for_image(card_number)
        exact_id = f"{set_code.lower()}-{num3}"
        # attempt to find an exact match
        exact = [c for c in candidates if c.get("id", "").lower() == exact_id]
        # if no exact match fall back to softer 'endswith' search
        candidates = exact or [
            c for c in candidates if c.get("id", "").lower().endswith(f"-{num3}")
        ]
    # and from those only ones with an image
    candidates = [c for c in candidates if c.get("image")]
    # graceful exit if no matches found
    if not candidates:
        return {"error": "No matching cards in return"}
    # this list should only have one match by now but in case not we'll take the first item
    card = candidates[0]
    # return the information
    return {
        "name": card.get("name"),
        "image_url": (card.get("image") or "") + "/high.png",
        "card_id": card.get("id"),
    }


def fetch_card_price(card_name: str, set_name: str):
    """
    Fetches pricing data from the PokemonPriceTracker API.

    Uses PRICE_SET_MAP to convert CardVault's internal set names into
    the set codes expected by the price API. Requires CARDVAULT_API_KEY
    to be configured in environment/settings.

    Called by:
    - CardForm (forms.py)
    - refresh_prices_for_user() (services/price_services.py)

    Returns:
        dict:
        API response data on success, or an error dict on failure.
    """
    # the price API requires a key hidden in .env
    api_key = getattr(settings, "CARDVAULT_API_KEY", None)
    # if someone uses this on github and cannot access my key this will fail gracefully unless they add their own
    if not api_key:
        logger.warning("CARDVAULT_API_KEY missing - skipping price fetch.")
        return {"error": "Missing API key"}
    # use the price set map for the set in question
    set_code = PRICE_SET_MAP.get(set_name)
    # if it is not available fail gracefully
    if not set_code:
        logger.error("Missing PRICE_SET_MAP code for set '%s'", set_name)
        return {"error": "Unknown set for price API"}
    # hit the API passing headers and params to access
    url = "https://www.pokemonpricetracker.com/api/v2/cards"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"set": set_code, "search": card_name}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        # if all goes well, return json dictionary (how the API formats their data)
        if resp.status_code == 200:
            return resp.json()
        # if not, fail gracefully
        logger.warning(
            "Price API non-200 response. status=%s card=%s set=%s response=%s",
            resp.status_code,
            card_name,
            set_name,
            resp.text[:300],
        )
        return {"error": resp.text, "status": resp.status_code}

    except requests.RequestException:
        logger.exception(
            "Price API request failed for card=%s set=%s",
            card_name,
            set_name,
        )
        return {"error": "Request failed"}


def extract_card_price(data: dict, card_number: str | int):
    """
    Extracts market price information for a specific card variant
    from the PokemonPriceTracker API response.

    Matches cards using normalized/padded card numbers because the API
    stores values in formats such as "062/197" instead of plain integers.

    Parses and returns:
    - market price
    - last updated date

    Called by:
    - CardForm (forms.py)
    - refresh_prices_for_user() (services/price_services.py)

    Returns:
        dict containing:
        - price
        - price_date

        or an error dict if no matching card is found.
    """
    # Safety: ensure API returned something usable
    if not data or "data" not in data:
        logger.warning("No valid pricing data provided to extract_card_price.")
        return {"error": "No data received from price API"}

    padded = _pad_card_number_for_image(card_number)

    # Loop through all card variants in the response
    for card in data.get("data", []):
        try:
            # v2 stores this field as "cardNumber" (e.g. "062/197")
            if str(card.get("cardNumber", "")).startswith(padded):
                # Pull price data
                price = card["prices"]["market"]

                # lastUpdated is ISO 8601, not YYYY/MM/DD
                raw_date = card["prices"]["lastUpdated"]
                price_date = raw_date.split("T")[0]  # YYYY-MM-DD

                return {
                    "price": price,
                    "price_date": price_date,
                    # The following may be useful in future feature expansion
                    # "tcgplayer_id": card.get("tcgPlayerId"),
                    # "variant": card.get("rarity"),
                }

        except Exception as e:
            logger.exception("Failed parsing a card variant: %s", e)
            continue

    return {"error": f"Card number {padded} not found"}
