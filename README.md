# FlyHND 3.0 — Flight Search and Price Comparison

FlyHND is a Python flight-search application with a Flask web interface and a command-line demo. It collects flight offers, compares prices, filters by budget, and ranks options by fare, duration, and stops.

> **Booking notice:** FlyHND is a search and comparison demo. It does not reserve flights, accept payments, or issue tickets. Demo fares are synthetic and are not live prices.

## Features

- Search for flights using a configured live provider: SerpApi's Google Flights engine or Amadeus.
- Use the included offline dataset for the Pune (PNQ) to Singapore (SIN) demo route.
- Search one-way or return itineraries in the web interface, with passenger count, currency, and optional budget filters.
- Sort and compare results by price, duration, and value; inspect itinerary segments when provider data includes them.
- Open any result's live price and booking options on Google Flights, or go straight to the airline's own website (`tools/booking_links.py`).
- Resolve duplicate quotes by keeping the most recently observed offer for a flight.
- Retrieve policy and prior-search evidence using a small in-project TF-IDF retriever.
- Store policy records, cached flight snapshots, and search history in SQLite.

## Project structure

```text
agents/       Search coordinator and policy, search, and ranking agents
data/         Synthetic demo flights and SQLite memory database
memory/       Working memory, SQLite storage, and TF-IDF retrieval
models/       Flight, search request, task, and agent message models
tools/        Flight provider integration and fare ranking/arbitration
web/          Flask app, HTML template, CSS, JavaScript, and images
main.py       Command-line demo and live-search entry point
run_web.py    Web server launcher
requirements.txt
```

## Requirements

- Python 3.10 or later
- Packages listed in `requirements.txt`
- A SerpApi key or Amadeus credentials for live search; credentials are not needed for the offline demo

## Setup

Create and activate a virtual environment, then install the dependencies:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

For live search, copy `.env.example` to `.env` and add the credentials for one provider:

```dotenv
SERPAPI_API_KEY=your_serpapi_key
```

Or configure Amadeus instead:

```dotenv
AMADEUS_CLIENT_ID=your_amadeus_client_id
AMADEUS_CLIENT_SECRET=your_amadeus_client_secret
```

Keep `.env` private; it contains credentials and should not be committed.

## Run the web app

```bash
python run_web.py
```

The launcher starts the Flask server at `http://localhost:5000` by default and opens a browser. Use `--no-browser` to prevent opening a browser, or `--port 8000` to choose another port.

Without provider credentials, the site runs in demo mode. The bundled synthetic data is for PNQ → SIN; it should not be treated as real fares for other routes.

## Run the command-line demo

```bash
python main.py --demo
```

For live CLI search, configure credentials first, then run:

```bash
python main.py --live --from PNQ --to SIN --date 2027-01-15 --budget 30000
```

Other CLI options include `--passengers` and `--currency`. Dates use `YYYY-MM-DD`.

## Search flow

1. The Flask route validates the request and resolves free-text places when live autocomplete is available.
2. `RequestCoordinator` asks the policy-memory agent for related evidence and the flight-search agent for offers.
3. `ValidationRankingAgent` resolves duplicate quotes, filters offers above the budget, and ranks the remaining results.
4. The web interface displays the offers and their source. Completed searches are recorded in SQLite.

The ranking score currently combines fare, a per-stop penalty, and a duration penalty. The SQLite file is local application state; it is ignored by `.gitignore`.

## Important limitations

- The bundled demo dataset only represents a synthetic PNQ → SIN benchmark.
- Live results depend on the configured provider, its access, and its response data.
- Search results are not bookable through this application. There is no checkout, payment gateway, booking confirmation, or ticket issuance flow.
- The bundled SQLite database contains local memory and search history, not a trained machine-learning model.
