"""
MCP Server — Real Flight Price Search (SerpApi / Google Flights)
=================================================================
One tool: search_flights(dep_iata, arr_iata, date, cabin) -- calls
SerpApi's Google Flights engine for a ONE-WAY trip on a SPECIFIC date
and returns real fares, cheapest first: airline, flight numbers,
times, stops, duration and price.

"""

import os
import requests
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
load_dotenv()

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP("flight-price-server", host="0.0.0.0", port=PORT)

SERPAPI_URL = "https://serpapi.com/search.json"

# Cap the payload (no. of itineraries) so the LLM's context stays small.
MAX_ITINERARIES = 10


@mcp.tool()
def search_flights(dep_iata: str, arr_iata: str, date: str, cabin: str = "Economy") -> dict:
    """
    Search REAL live one-way flight prices for a specific route and date.

    Args:
        dep_iata: 3-letter IATA code of the departure airport, e.g. "ESB"
        arr_iata: 3-letter IATA code of the arrival airport, e.g. "IST"
        date: travel date in YYYY-MM-DD format, e.g. "2026-12-15"
        cabin: "Economy" or "Business"
    """
    api_key = os.environ.get("SERPAPI_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "No SERPAPI_API_KEY configured on this server's environment."}

    is_business = cabin.strip().lower() == "business"
    cabin_label = "Business" if is_business else "Economy"

    params = {
        "engine": "google_flights",
        "departure_id": dep_iata.strip().upper(),
        "arrival_id": arr_iata.strip().upper(),
        "outbound_date": date,
        "type": "2",                                  # 2 = one way
        "travel_class": "3" if is_business else "1",  # 1 = Economy, 3 = Business
        "currency": "USD",
        "hl": "en",
        "api_key": api_key,
    }

    # No automatic retry on purpose: the free plan only has 250 searches/month.
    response = requests.get(SERPAPI_URL, params=params, timeout=30)
    if response.status_code != 200:
        return {"ok": False, "error": f"SerpApi returned {response.status_code}: {response.text[:200]}"}

    data = response.json()
    if data.get("error"):
        return {"ok": False, "error": data["error"]}

    raw = (data.get("best_flights") or []) + (data.get("other_flights") or [])

    itineraries = []
    for item in raw:
        price = item.get("price")
        segments = item.get("flights") or []
        if price is None or not segments:
            continue

        labels = [f"{s.get('airline', 'Unknown airline')} {s.get('flight_number', '?')}" for s in segments]

        itineraries.append({
            "airlines": " + ".join(labels),
            "departure": segments[0].get("departure_airport", {}).get("time"),
            "arrival": segments[-1].get("arrival_airport", {}).get("time"),
            "stops": len(segments) - 1,
            "duration_minutes": item.get("total_duration"),
            "price_usd": price,
        })

    itineraries.sort(key=lambda x: x["price_usd"])

    return {
        "ok": True,
        "route": f"{params['departure_id']} -> {params['arrival_id']}",
        "date": date,
        "cabin": cabin_label,
        "total_found": len(itineraries),
        "itineraries": itineraries[:MAX_ITINERARIES],
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")