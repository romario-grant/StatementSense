"""
PlacesService — Google Places API (New) integration for CalendarSense v2.

Replaces the Gemini-powered alternative search with real Google Places data,
including coordinates for interactive map rendering on the frontend.

Uses the Places API (New) Text Search endpoint via REST:
  POST https://places.googleapis.com/v1/places:searchText
"""

import os
import requests
from typing import Optional


# ── Subscription type → search query mapping ──────────────────────────

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

# Fallback queries when no keyword matches
FALLBACK_QUERIES = {
    "physical":                "alternatives to {sub} in {dest}",
    "regional_service":        "mobile carrier stores and SIM card shops in {dest}",
    "location_locked_digital": "internet cafes in {dest}",
}

# Google Places API field mask — only request what we need to minimize billing
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
    """
    Google Places API (New) integration.
    
    Searches for real business alternatives at a travel destination,
    returning structured data with coordinates for map markers.
    """

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
        """
        Search for real alternatives to a local subscription at the travel
        destination using Google Places API Text Search (New).

        Returns:
            {
                "alternatives_found": bool,
                "destination": str,
                "destination_center": {"lat": float, "lng": float},
                "options": [
                    {
                        "place_id": str,
                        "name": str,
                        "address": str,
                        "lat": float,
                        "lng": float,
                        "rating": float | None,
                        "rating_count": int | None,
                        "price_level": str | None,
                        "phone": str | None,
                        "website": str | None,
                        "google_maps_url": str,
                        "opening_hours": list[str] | None,
                    }
                ],
                "search_query": str,
            }
        """
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

            # Parse results
            options = []
            center_lat, center_lng = None, None

            for place in places:
                loc = place.get("location", {})
                lat = loc.get("latitude")
                lng = loc.get("longitude")

                # Use the first result's location as map center
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
        """Map subscription type + name to an effective Places API search query."""
        sub_lower = sub_name.lower()
        templates = SEARCH_TEMPLATES.get(location_type, {})

        for keyword, template in templates.items():
            if keyword in sub_lower:
                return template.format(dest=destination)

        # Use fallback query
        fallback = FALLBACK_QUERIES.get(location_type, "alternatives to {sub} in {dest}")
        return fallback.format(sub=sub_name, dest=destination)

    @staticmethod
    def _format_price_level(level: str | None) -> str | None:
        """Convert API price level enum to display string."""
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
