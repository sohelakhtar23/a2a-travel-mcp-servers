"""
MCP Server — Real Flight Price Search (FlightAPI.io)
=======================================================
One tool: search_flights(dep_iata, arr_iata, date, cabin) -- calls
FlightAPI.io's one-way trip search and returns REAL live fares for a
SPECIFIC date, cheapest first: airline, flight numbers, times, stops,
price, and which real booking site is offering that price (Kiwi.com,
Expedia, Trip.com, etc).

Needs a FLIGHTAPI_KEY environment variable set on whatever host runs
this. Free tier: 100 requests / 30 days, no credit card. Sign up at
https://api.flightapi.io/register

This server runs over Streamable HTTP (not stdio), so it can be
deployed as a standalone remote service and reached by any MCP client
over a plain URL. Binds to $PORT (Render, and most PaaS hosts, inject
this automatically) or 8000 for local testing.
"""

import os
import time

import requests
from mcp.server.fastmcp import FastMCP

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP("flight-price-server", host="0.0.0.0", port=PORT)

BASE_URL = "https://api.flightapi.io/onewaytrip"

# How many of the real itineraries FlightAPI finds to hand back --
# capped so the payload (and the LLM's context) stays sane; they're
# already sorted cheapest-first so nothing important gets cut.
MAX_ITINERARIES = 10


@mcp.tool()
def search_flights(dep_iata: str, arr_iata: str, date: str, cabin: str = "Economy") -> dict:
    """
    Search REAL live flight prices for a specific route and date.

    Args:
        dep_iata: 3-letter IATA code of the departure airport, e.g. "SKT"
        arr_iata: 3-letter IATA code of the arrival airport, e.g. "DXB"
        date: travel date in YYYY-MM-DD format, e.g. "2026-07-21"
        cabin: "Economy" or "Business"
    """
    api_key = os.environ.get("FLIGHTAPI_KEY", "")
    if not api_key:
        return {"ok": False, "error": "No FLIGHTAPI_KEY configured on this server's environment."}

    cabin_key = "Business" if cabin.strip().lower() == "business" else "Economy"
    url = f"{BASE_URL}/{api_key}/{dep_iata}/{arr_iata}/{date}/1/0/0/{cabin_key}/USD"

    # FlightAPI occasionally returns a transient "something went wrong,
    # please try again" -- one retry clears that up most of the time, so
    # we don't fail the whole booking over a one-off upstream hiccup.
    response = requests.get(url, timeout=20)
    if response.status_code != 200:
        time.sleep(1.5)
        response = requests.get(url, timeout=20)

    if response.status_code != 200:
        return {"ok": False, "error": f"FlightAPI returned {response.status_code}: {response.text[:200]}"}

    data = response.json()

    carriers = {c["id"]: c["name"] for c in data.get("carriers", [])}
    agents = {a["id"]: a["name"] for a in data.get("agents", [])}
    legs = {leg["id"]: leg for leg in data.get("legs", [])}
    segments = {seg["id"]: seg for seg in data.get("segments", [])}

    itineraries = []
    for it in data.get("itineraries", []):
        leg_ids = it.get("leg_ids") or []
        leg = legs.get(leg_ids[0]) if leg_ids else None
        if not leg:
            continue

        priced_options = [
            p for p in it.get("pricing_options", [])
            if p.get("price", {}).get("amount") is not None
        ]
        if not priced_options:
            continue
        best = min(priced_options, key=lambda p: p["price"]["amount"])
        agent_id = best["agent_ids"][0] if best.get("agent_ids") else None

        seg_labels = []
        for sid in leg.get("segment_ids", []):
            seg = segments.get(sid, {})
            carrier_name = carriers.get(seg.get("marketing_carrier_id"), "Unknown airline")
            flight_no = seg.get("marketing_flight_number", "?")
            seg_labels.append(f"{carrier_name} {flight_no}")

        itineraries.append({
            "airlines": " + ".join(seg_labels) if seg_labels else "Unknown airline",
            "departure": leg.get("departure"),
            "arrival": leg.get("arrival"),
            "stops": leg.get("stop_count"),
            "duration_minutes": leg.get("duration"),
            "price_usd": best["price"]["amount"],
            "booking_site": agents.get(agent_id, agent_id or "Unknown"),
        })

    itineraries.sort(key=lambda x: x["price_usd"])

    return {
        "ok": True,
        "route": f"{dep_iata} -> {arr_iata}",
        "date": date,
        "cabin": cabin_key,
        "total_found": len(itineraries),
        "itineraries": itineraries[:MAX_ITINERARIES],
    }


if __name__ == "__main__":
    # Streamable HTTP -- this process listens on a real port and serves
    # MCP over HTTP, so any client (local or remote) can connect via
    # its URL instead of spawning this as a local subprocess.
    mcp.run(transport="streamable-http")
