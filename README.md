# A2A Travel MCP Servers (Remote)

Two standalone [Model Context Protocol](https://modelcontextprotocol.io/) servers, each exposing one real-data tool over **Streamable HTTP** — deployable as independent remote services and reachable by any MCP client over a plain URL, instead of being spawned as a local subprocess.

## Tools

| Server | Tool | Data Source | API Key Required |
|---|---|---|---|
| `flight_price_server.py` | `search_flights(dep_iata, arr_iata, date, cabin)` — real live flight fares for a specific date | [FlightAPI.io](https://www.flightapi.io/) | Yes — `FLIGHTAPI_KEY` |
| `hotel_price_server.py` | `search_hotels(city, arrival_date, departure_date, adults)` — real live hotel prices for specific dates | [Booking.com](https://rapidapi.com/DataCrawler/api/booking-com15) (via RapidAPI) | Yes — `RAPIDAPI_KEY` |

## Why Streamable HTTP

Both servers use the same tool logic you'd find in a local (stdio) MCP server — the only difference is the transport. Instead of an agent spawning these as a local subprocess, each one runs as a persistent web service with its own URL, so any MCP client (local or remote) can connect to it directly.

## Running Locally

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

FLIGHTAPI_KEY=... python flight_price_server.py    # listens on http://localhost:8000/mcp
RAPIDAPI_KEY=... python hotel_price_server.py       # listens on http://localhost:8000/mcp
```

Run one at a time locally (both default to port 8000), or set `PORT` to run them side by side:

```bash
PORT=8001 RAPIDAPI_KEY=... python hotel_price_server.py
```

## Deploying to Render

Each server is deployed as its own **Web Service**, both pointing at this same repository:

1. Push this repo to GitHub.
2. On [Render](https://render.com), click **New +** → **Web Service**, connect this repo.
3. **For the flight service:**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python flight_price_server.py`
   - Add environment variable `FLIGHTAPI_KEY` with your key from [api.flightapi.io/register](https://api.flightapi.io/register).
4. **For the hotel service**, repeat as a separate Web Service:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python hotel_price_server.py`
   - Add environment variable `RAPIDAPI_KEY` with your key from [rapidapi.com](https://rapidapi.com) (subscribed to the free tier of [Booking COM](https://rapidapi.com/DataCrawler/api/booking-com15)).

Render assigns a public HTTPS URL to each service and injects `PORT` automatically — both servers already read it (`os.environ.get("PORT", 8000)`).

## Connecting an Agent

Once deployed, point any MCP client at the service's `/mcp` endpoint. With the OpenAI Agents SDK:

```python
from agents.mcp import MCPServerStreamableHttp

flight_mcp = MCPServerStreamableHttp(
    name="flight-price-server",
    params={"url": "https://<your-flight-service>.onrender.com/mcp"},
)
```

No local process is spawned — the agent talks to the tool entirely over HTTP.
