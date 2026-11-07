# A2A Travel MCP Servers (Remote)

Two standalone [Model Context Protocol](https://modelcontextprotocol.io/) servers, each exposing one real-data tool over **Streamable HTTP**. Each can be deployed as an independent remote service and reached by any MCP client over a plain URL, instead of being spawned as a local subprocess.

## Tools

| Server | Tool | Data Source | API Key Required |
|---|---|---|---|
| `flight_price_server.py` | `search_flights(dep_iata, arr_iata, date, cabin)`: real one-way flight fares for a specific date, cheapest first | [SerpApi](https://serpapi.com/) (Google Flights engine) | Yes: `SERPAPI_API_KEY` |
| `hotel_price_server.py` | `search_hotels(city, arrival_date, departure_date, adults)`: real hotel prices for specific dates | [Booking.com](https://rapidapi.com/DataCrawler/api/booking-com15) (via RapidAPI) | Yes: `RAPIDAPI_KEY` |

> **Quota note:** SerpApi's free plan allows 250 searches per month, and every `search_flights` call uses one. Check your plan on the SerpApi dashboard, as free-tier terms change.

## Why Streamable HTTP

Both servers use the same tool logic you would find in a local (stdio) MCP server. Only the transport differs: each one runs as a persistent web service with its own URL, so any MCP client (local or remote) can connect to it directly.

## Project Setup (uv)

This project uses [uv](https://docs.astral.sh/uv/) for dependency management. Dependencies are declared in `pyproject.toml` and pinned in `uv.lock` (commit both).

```bash
# Install uv once: https://docs.astral.sh/uv/getting-started/installation/
uv sync
```

## API Keys (`.env`)

Create a `.env` file in the project root (never commit it; make sure `.env` is in `.gitignore`):

```
SERPAPI_API_KEY=your_serpapi_key
RAPIDAPI_KEY=your_rapidapi_key
```

Get keys here:
- SerpApi: https://serpapi.com/users/sign_up
- RapidAPI: https://rapidapi.com (subscribe to the free tier of [Booking COM](https://rapidapi.com/DataCrawler/api/booking-com15))

The servers load `.env` automatically for local runs. In production, set the same variables in your host's environment settings instead of uploading the file.

## Running Locally

```bash
uv run python flight_price_server.py    # listens on http://localhost:8000/mcp
uv run python hotel_price_server.py     # listens on http://localhost:8000/mcp
```

Both default to port 8000. Run one at a time, or set `PORT` to run them side by side:

```bash
# macOS / Linux / Git Bash
PORT=8001 uv run python hotel_price_server.py

# PowerShell
$env:PORT=8001; uv run python hotel_price_server.py
```

## Testing

**1. Check your SerpApi key directly with curl** (uses 1 search):

```bash
curl --get https://serpapi.com/search.json \
  -d engine="google_flights" \
  -d departure_id="ESB" \
  -d arrival_id="IST" \
  -d outbound_date="2026-12-15" \
  -d type="2" \
  -d currency="USD" \
  -d api_key="YOUR_KEY"
```

On Windows (Git Bash), if you see a `CRYPT_E_NO_REVOCATION_CHECK` error, add `--ssl-no-revoke`.

**2. Call the tool through MCP Inspector:**

```bash
npx @modelcontextprotocol/inspector
```

In the Inspector, add a server with transport **Streamable HTTP** and URL `http://localhost:8000/mcp`, connect, open **Tools**, and run `search_flights` with `ESB`, `IST`, `2026-12-15`, `Economy`.

## Deploying to Render

Each server is deployed as its own **Web Service**, both pointing at this same repository.

**Before you deploy**, make sure the repo contains `pyproject.toml`, `uv.lock` and the server files, and that `.env` is **not** committed. Because `requires-python` is `>=3.12`, also commit a `.python-version` file, or set a `PYTHON_VERSION` environment variable on the service, so Render uses a compatible Python.

1. Push this repo to GitHub.
2. On [Render](https://render.com), click **New +** → **Web Service** and connect this repo.
3. **For the flight service:**
   - Language: `Python 3`
   - Build Command: `pip install uv && uv sync --frozen --no-dev`
   - Start Command: `uv run python flight_price_server.py`
   - Environment variable: `SERPAPI_API_KEY` = your key
4. **For the hotel service**, repeat as a separate Web Service:
   - Build Command: `pip install uv && uv sync --frozen --no-dev`
   - Start Command: `uv run python hotel_price_server.py`
   - Environment variable: `RAPIDAPI_KEY` = your key

Keep `uv run` in the start command. Bare `python` may not see the packages installed by uv.

Render assigns a public HTTPS URL to each service and injects `PORT` automatically; both servers already read it (`os.environ.get("PORT", 8000)`).

> On Render's free tier, services spin down after inactivity, so the first request after a quiet period can take 30-60 seconds.

Once deployed, verify with MCP Inspector using `https://<your-service>.onrender.com/mcp`. Opening that URL in a browser will likely show an error, which is expected: it speaks MCP, not plain web pages.

## Connecting an Agent

Point any MCP client at the service's `/mcp` endpoint. With the OpenAI Agents SDK:

```python
from agents.mcp import MCPServerStreamableHttp

flight_mcp = MCPServerStreamableHttp(
    name="flight-price-server",
    params={"url": "https://<your-flight-service>.onrender.com/mcp"},
)
```

No local process is spawned; the agent talks to the tool entirely over HTTP.