"""
MCP Server — Real Hotel Search (SerpApi / Google Hotels)
=========================================================
One tool: search_hotels(city, arrival_date, departure_date, adults) --
calls SerpApi's Google Hotels engine in a SINGLE request and returns a
SMALL, cleaned list sorted cheapest first: name, price per night,
total price, rating, review count, star class.

Needs a SERPAPI_API_KEY environment variable (the same key the flight
server uses). Free plan: 250 searches per month, shared with flights.

Runs over Streamable HTTP so it can be deployed as a standalone remote
service (e.g. on Render). Binds to $PORT or 8000 for local testing.
"""

import os
from datetime import date

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP("hotel-price-server", host="0.0.0.0", port=PORT)

SERPAPI_URL = "https://serpapi.com/search.json"

# Cap the payload so the LLM's context stays small.
MAX_HOTELS = 8


@mcp.tool()
def search_hotels(city: str, arrival_date: str, departure_date: str, adults: int = 2) -> dict:
    """
    Search REAL live hotel prices for a city and date range.

    Args:
        city: the city to search, e.g. "Istanbul"
        arrival_date: check-in date in YYYY-MM-DD format
        departure_date: check-out date in YYYY-MM-DD format
        adults: number of adult guests
    """
    api_key = os.environ.get("SERPAPI_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "No SERPAPI_API_KEY configured on this server's environment."}

    try:
        nights = (date.fromisoformat(departure_date) - date.fromisoformat(arrival_date)).days
    except ValueError:
        return {"ok": False, "error": "Dates must be in YYYY-MM-DD format."}
    if nights <= 0:
        return {"ok": False, "error": "departure_date must be after arrival_date."}

    params = {
        "engine": "google_hotels",
        "q": f"hotels in {city}",
        "check_in_date": arrival_date,
        "check_out_date": departure_date,
        "adults": adults,
        "currency": "USD",
        "hl": "en",
        "sort_by": "3",  # 3 = lowest price
        "api_key": api_key,
    }

    # No automatic retry on purpose: the free plan only has 250 searches/month.
    response = requests.get(SERPAPI_URL, params=params, timeout=30)
    if response.status_code != 200:
        return {"ok": False, "error": f"SerpApi returned {response.status_code}: {response.text[:200]}"}

    data = response.json()
    if data.get("error"):
        return {"ok": False, "error": data["error"]}

    hotels = []
    for prop in data.get("properties") or []:
        per_night = (prop.get("rate_per_night") or {}).get("extracted_lowest")
        total = (prop.get("total_rate") or {}).get("extracted_lowest")
        if per_night is None and total is None:
            continue  # no price for these dates, so it's not useful here
        if per_night is None:
            per_night = round(total / nights, 2)
        if total is None:
            total = round(per_night * nights, 2)

        hotels.append({
            "name": prop.get("name", "Unknown hotel"),
            "price_per_night_usd": per_night,
            "total_price_usd": total,
            "rating": prop.get("overall_rating"),
            "review_count": prop.get("reviews"),
            "stars": prop.get("extracted_hotel_class"),
        })

    hotels.sort(key=lambda h: h["price_per_night_usd"])

    return {
        "ok": True,
        "city": city,
        "check_in": arrival_date,
        "check_out": departure_date,
        "nights": nights,
        "adults": adults,
        "total_found": len(hotels),
        "hotels": hotels[:MAX_HOTELS],
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")