"""
Google Places enrichment for CalendarSense travel destinations.

Calls the Places API (New) Text Search endpoint to find real merchants at a
destination and returns structured results with coordinates so the frontend can
plot them on a map.
"""

import os
import requests
from typing import Optional


# Search query templates keyed by subscription type and keyword.

SEARCH_TEMPLATES = {
    "physical": {
        "gym":       "gyms with day passes or short-term memberships in {dest}",
        "fitness":   "fitness centers with day passes in {dest}",
        "yoga":      "yoga studios with drop-in classes in {dest}",
        "crossfit":  "CrossFit gyms with drop-in rates in {dest}",
        "pool":      "public swimming pools or pool day passes in {dest}",
        "studio":    "fitness studios with day passes in {dest}",
        "cowork":    "coworking spaces with day passes in {dest}",
        "workspace": "coworking spaces with day passes in {dest}",
        "parking":   "monthly parking garages in {dest}",
        "storage":   "short-term storage facilities in {dest}",
        "club":      "social clubs or recreational venues in {dest}",
    },
    "regional_service": {
        "flow":     "prepaid SIM card stores and mobile carrier stores in {dest}",
        "digicel":  "prepaid SIM card stores and mobile carrier stores in {dest}",
        "mobile":   "mobile phone stores with prepaid SIM cards in {dest}",
        "data":     "prepaid SIM card stores and eSIM providers in {dest}",
        "cell":     "mobile carrier stores with prepaid plans in {dest}",
        "internet": "internet cafes and WiFi hotspot providers in {dest}",
        "cable":    "streaming service stores or electronics stores in {dest}",
        "tv":       "electronics stores with streaming devices in {dest}",
    },
    "location_locked_digital": {},
}

# Generic queries used when no subscription keyword matches a template above.
FALLBACK_QUERIES = {
    "physical":                "alternatives to {sub} in {dest}",
    "regional_service":        "mobile carrier stores and SIM card shops in {dest}",
    "location_locked_digital": "internet cafes in {dest}",
}

# Field mask restricting the Places response to billed fields the frontend renders.
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.rating",
    "places.userRatingCount",
    "places.priceLevel",
    "places.googleMapsUri",
    "places.currentOpeningHours",
    "places.nationalPhoneNumber",
    "places.websiteUri",
])


class PlacesService:
    """Search the Google Places API for merchants near a travel destination and return structured results with coordinates for map markers."""

    TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GOOGLE_MAPS_API_KEY not found. "
                "Set it in your .env file to enable Places API search."
            )

    def search_alternatives(
        self,
        subscription_name: str,
        location_type: str,
        destination: str,
        max_results: int = 5,
        search_query: str | None = None,
    ) -> dict:
        """Return alternative merchants for a subscription at the destination using Places Text Search. The result includes a map center, per-place metadata, and the query that was issued."""
        query = (search_query or "").strip() or self._build_search_query(
            subscription_name, location_type, destination
        )
        print(f"[PlacesService] Searching: \"{query}\"")

        try:
            response = requests.post(
                self.TEXT_SEARCH_URL,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": FIELD_MASK,
                },
                json={
                    "textQuery": query,
                    "maxResultCount": max_results,
                },
                timeout=10,
            )

            if response.status_code != 200:
                print(f"[PlacesService] API error {response.status_code}: {response.text[:200]}")
                return self._empty_result(destination, query)

            data = response.json()
            places = data.get("places", [])

            if not places:
                print(f"[PlacesService] No results for query: \"{query}\"")
                return self._empty_result(destination, query)

            options = []
            center_lat, center_lng = None, None

            for place in places:
                loc = place.get("location", {})
                lat = loc.get("latitude")
                lng = loc.get("longitude")

                # The first place with coordinates anchors the map view.
                if center_lat is None and lat is not None:
                    center_lat = lat
                    center_lng = lng

                display_name = place.get("displayName", {})
                hours = place.get("currentOpeningHours", {})

                options.append({
                    "place_id": place.get("id", ""),
                    "name": display_name.get("text", "Unknown"),
                    "address": place.get("formattedAddress", ""),
                    "lat": lat,
                    "lng": lng,
                    "rating": place.get("rating"),
                    "rating_count": place.get("userRatingCount"),
                    "price_level": self._format_price_level(place.get("priceLevel")),
                    "phone": place.get("nationalPhoneNumber"),
                    "website": place.get("websiteUri"),
                    "google_maps_url": place.get("googleMapsUri", ""),
                    "opening_hours": hours.get("weekdayDescriptions") if hours else None,
                })

            print(f"[PlacesService] Found {len(options)} alternatives")

            return {
                "alternatives_found": True,
                "destination": destination,
                "destination_center": {
                    "lat": center_lat,
                    "lng": center_lng,
                },
                "options": options,
                "search_query": query,
            }

        except requests.Timeout:
            print("[PlacesService] Request timed out")
            return self._empty_result(destination, query)
        except Exception as e:
            print(f"[PlacesService] Error: {e}")
            return self._empty_result(destination, query)

    def _build_search_query(self, sub_name: str, location_type: str, destination: str) -> str:
        """Pick a Places Text Search query for a subscription, matching keyword templates first and falling back to a generic query."""
        sub_lower = sub_name.lower()
        templates = SEARCH_TEMPLATES.get(location_type, {})

        for keyword, template in templates.items():
            if keyword in sub_lower:
                return template.format(dest=destination)

        fallback = FALLBACK_QUERIES.get(location_type, "alternatives to {sub} in {dest}")
        return fallback.format(sub=sub_name, dest=destination)

    @staticmethod
    def _format_price_level(level: str | None) -> str | None:
        """Render the Places price-level enum as a dollar-sign string for the UI."""
        mapping = {
            "PRICE_LEVEL_FREE": "Free",
            "PRICE_LEVEL_INEXPENSIVE": "$",
            "PRICE_LEVEL_MODERATE": "$$",
            "PRICE_LEVEL_EXPENSIVE": "$$$",
            "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
        }
        return mapping.get(level) if level else None

    @staticmethod
    def _empty_result(destination: str, query: str) -> dict:
        """Return an empty result structure."""
        return {
            "alternatives_found": False,
            "destination": destination,
            "destination_center": None,
            "options": [],
            "search_query": query,
        }
