"""
MCP Server — Weather Tool (Open-Meteo)
=========================================
One tool: get_weather(city, date) -> real current weather OR a real
dated forecast, up to 16 days ahead. Uses Open-Meteo, which is
completely free with NO API KEY needed at all -- no signup, works for
any city worldwide.

Two real API calls per lookup, both free, no key:
  1. Open-Meteo's geocoding API: city name -> latitude/longitude
  2. Open-Meteo's forecast API: latitude/longitude -> current weather
     AND a 16-day daily forecast in one response

This server runs over Streamable HTTP (not stdio), so it can be
deployed as a standalone remote service and reached by any MCP client
over a plain URL. Binds to $PORT (Render, and most PaaS hosts, inject
this automatically) or 8000 for local testing.
"""

import os

import requests
from mcp.server.fastmcp import FastMCP

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP("weather-server", host="0.0.0.0", port=PORT)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

FORECAST_DAYS = 16   # Open-Meteo's real forecast horizon -- everything beyond this is a guess, not data

# Standard WMO weather codes -> plain English, used by Open-Meteo and
# most national weather services (https://open-meteo.com/en/docs).
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


@mcp.tool()
def get_weather(city: str, date: str = "") -> dict:
    """
    Look up the real weather for a city -- current conditions, or a real
    forecast for a specific future date (up to 16 days ahead).

    Args:
        city: the city to check, e.g. "Karachi" or "London"
        date: optional date in YYYY-MM-DD format. Leave empty for right-now
            current weather. Dates more than 16 days out have no real
            forecast available -- this will say so rather than guess.
    """
    geo_resp = requests.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=10)
    if geo_resp.status_code != 200:
        return {"error": f"Geocoding returned {geo_resp.status_code}: {geo_resp.text[:200]}"}

    geo_results = geo_resp.json().get("results") or []
    if not geo_results:
        return {"error": f"Could not find a location called '{city}'."}

    place = geo_results[0]
    lat, lon = place["latitude"], place["longitude"]
    resolved_city = place.get("name", city)
    country = place.get("country")

    forecast_resp = requests.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "timezone": place.get("timezone", "auto"),
            "current_weather": "true",
            "forecast_days": FORECAST_DAYS,
            "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max",
        },
        timeout=10,
    )
    if forecast_resp.status_code != 200:
        return {"error": f"Forecast API returned {forecast_resp.status_code}: {forecast_resp.text[:200]}"}

    data = forecast_resp.json()

    if not date:
        current = data.get("current_weather", {})
        return {
            "city": resolved_city,
            "country": country,
            "date": current.get("time", "")[:10],
            "condition": WMO_CODES.get(current.get("weathercode"), "Unknown"),
            "temp_c": current.get("temperature"),
            "wind_kph": current.get("windspeed"),
        }

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    if date not in dates:
        return {
            "error": f"No real forecast available for {date} -- Open-Meteo only forecasts "
                     f"{FORECAST_DAYS} days ahead (through {dates[-1] if dates else 'unknown'})."
        }

    idx = dates.index(date)
    return {
        "city": resolved_city,
        "country": country,
        "date": date,
        "condition": WMO_CODES.get(daily.get("weathercode", [None])[idx], "Unknown"),
        "temp_max_c": daily.get("temperature_2m_max", [None])[idx],
        "temp_min_c": daily.get("temperature_2m_min", [None])[idx],
        "chance_of_rain_pct": daily.get("precipitation_probability_max", [None])[idx],
    }


if __name__ == "__main__":
    # Streamable HTTP -- this process listens on a real port and serves
    # MCP over HTTP, so any client (local or remote) can connect via
    # its URL instead of spawning this as a local subprocess.
    mcp.run(transport="streamable-http")
