"""
MCP Server — Real Hotel Search (Booking.com via RapidAPI)
============================================================
One tool: search_hotels(city, arrival_date, departure_date, adults) --
calls Booking.com's real search (via RapidAPI) in two steps (resolve
the city to a dest_id, then search hotels) and returns a SMALL, cleaned
list: name, price, currency, rating, review count, star class.

Needs a RAPIDAPI_KEY environment variable set on whatever host runs
this. Sign up free at rapidapi.com and subscribe to the free tier of
"Booking COM" (by DataCrawler).

This server runs over Streamable HTTP (not stdio), so it can be
deployed as a standalone remote service and reached by any MCP client
over a plain URL. Binds to $PORT (Render, and most PaaS hosts, inject
this automatically) or 8000 for local testing.
"""

import os
import requests
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
load_dotenv()

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP("hotel-price-server", host="0.0.0.0", port=PORT)

HOST = "booking-com15.p.rapidapi.com"
DEST_URL = f"https://{HOST}/api/v1/hotels/searchDestination"
HOTELS_URL = f"https://{HOST}/api/v1/hotels/searchHotels"

# How many real hotels to hand back -- capped so the payload (and the
# LLM's context/rate limit) stays sane; already sorted cheapest-first.
MAX_HOTELS = 8


@mcp.tool()
def search_hotels(city: str, arrival_date: str, departure_date: str, adults: int = 2) -> dict:
    """
    Search REAL live hotel prices for a city and date range.

    Args:
        city: the city to search, e.g. "Lahore"
        arrival_date: check-in date in YYYY-MM-DD format
        departure_date: check-out date in YYYY-MM-DD format
        adults: number of adult guests
    """
    api_key = os.environ.get("RAPIDAPI_KEY", "")
    if not api_key:
        return {"ok": False, "error": "No RAPIDAPI_KEY configured on this server's environment."}

    headers = {"x-rapidapi-host": HOST, "x-rapidapi-key": api_key}

    dest_resp = requests.get(DEST_URL, headers=headers, params={"query": city}, timeout=20)
    if dest_resp.status_code != 200:
        return {"ok": False, "error": f"Destination search returned {dest_resp.status_code}: {dest_resp.text[:200]}"}

    destinations = dest_resp.json().get("data") or []
    # Prefer an actual city match over a specific hotel/landmark match.
    dest = next((d for d in destinations if d.get("dest_type") == "city"), None) or (destinations[0] if destinations else None)
    if dest is None:
        return {"ok": True, "city": city, "total_found": 0, "hotels": []}

    hotels_resp = requests.get(
        HOTELS_URL,
        headers=headers,
        params={
            "dest_id": dest["dest_id"],
            "search_type": dest["search_type"],
            "arrival_date": arrival_date,
            "departure_date": departure_date,
            "adults": adults,
            "currency_code": "USD",
        },
        timeout=20,
    )
    if hotels_resp.status_code != 200:
        return {"ok": False, "error": f"Hotel search returned {hotels_resp.status_code}: {hotels_resp.text[:200]}"}

    raw_hotels = (hotels_resp.json().get("data") or {}).get("hotels") or []

    hotels = []
    for h in raw_hotels:
        prop = h.get("property", {})
        price = prop.get("priceBreakdown", {}).get("grossPrice", {})
        hotels.append({
            "name": prop.get("name", "Unknown hotel"),
            "price": price.get("value"),
            "currency": price.get("currency", "USD"),
            "rating": prop.get("reviewScore"),
            "review_count": prop.get("reviewCount"),
            "stars": prop.get("propertyClass") or prop.get("accuratePropertyClass"),
        })
    hotels.sort(key=lambda x: x["price"] if x["price"] is not None else float("inf"))

    return {
        "ok": True,
        "city": dest.get("city_name") or city,
        "check_in": arrival_date,
        "check_out": departure_date,
        "total_found": len(hotels),
        "hotels": hotels[:MAX_HOTELS],
    }


if __name__ == "__main__":
    # Streamable HTTP -- this process listens on a real port and serves
    # MCP over HTTP, so any client (local or remote) can connect via
    # its URL instead of spawning this as a local subprocess.
    mcp.run(transport="streamable-http")
