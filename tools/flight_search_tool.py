import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple

from models.flight import FlightOffer
from memory.long_term_memory import LongTermMemoryStore


class FlightSearchTool:


    def __init__(
        self,
        long_term_memory: Optional[LongTermMemoryStore] = None,
        demo_data_path: Optional[str] = None
    ):
        self.ltm = long_term_memory or LongTermMemoryStore()
        if demo_data_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            demo_data_path = os.path.join(base_dir, "data", "demo_flights.json")
        self.demo_data_path = demo_data_path

        self.client_id = os.getenv("AMADEUS_CLIENT_ID")
        self.client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
        self.amadeus_token: Optional[str] = None
        self.token_expiry: float = 0.0

        self._ensure_cache_seeded()

    def _ensure_cache_seeded(self) -> None:
        try:
            cached = self.ltm.get_cached_flights("PNQ", "SIN")
            if len(cached) < 3 and os.path.exists(self.demo_data_path):
                demo_offers = self.load_demo_flights()
                cache_offers = []
                for o in demo_offers:
                    cache_offers.append(FlightOffer.create(
                        offer_id=f"cache-{o.offer_id}",
                        airline=o.airline,
                        airline_code=o.airline_code,
                        flight_number=o.flight_number,
                        origin=o.origin,
                        destination=o.destination,
                        departure_time=o.departure_time,
                        arrival_time=o.arrival_time,
                        duration=o.duration,
                        duration_minutes=o.duration_minutes,
                        stops=o.stops,
                        layovers=o.layovers,
                        cabin=o.cabin,
                        baggage=o.baggage,
                        base_fare=o.base_fare,
                        tax_fees=o.tax_fees,
                        currency=o.currency,
                        source="OFFLINE_CACHE",
                        observation_timestamp="2026-10-29T08:00:00Z" if o.flight_number == "FL-101" else o.observation_timestamp,
                        status="VALID"
                    ))
                self.ltm.seed_cached_flights(cache_offers)
        except Exception:
            pass

    def load_demo_flights(self) -> List[FlightOffer]:
        if not os.path.exists(self.demo_data_path):
            return []

        with open(self.demo_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        offers = []
        for item in data.get("flights", []):
            offer = FlightOffer.create(
                offer_id=item["offer_id"],
                airline=item["airline"],
                airline_code=item["airline_code"],
                flight_number=item["flight_number"],
                origin=item["origin"],
                destination=item["destination"],
                departure_time=item["departure_time"],
                arrival_time=item["arrival_time"],
                duration=item["duration"],
                duration_minutes=item["duration_minutes"],
                stops=item["stops"],
                layovers=item["layovers"],
                cabin=item["cabin"],
                baggage=item["baggage"],
                base_fare=item["base_fare"],
                tax_fees=item["tax_fees"],
                currency=item.get("currency", "INR"),
                source=item.get("source", "OFFLINE_DEMO"),
                observation_timestamp=item.get("observation_timestamp", datetime.now(timezone.utc).isoformat()),
                status=item.get("status", "VALID")
            )
            offers.append(offer)
        return offers

    def search_live_serpapi(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        currency: str = "INR"
    ) -> List[FlightOffer]:

        serpapi_key = os.getenv("SERPAPI_API_KEY")
        if not serpapi_key:
            raise ValueError("SERPAPI_API_KEY missing from environment.")

        params = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": departure_date,
            "type": "2",
            "currency": currency.upper(),
            "hl": "en",
            "adults": str(adults),
            # Without these Google returns only its short "top flights" list and can omit the cheapest fares.
            "show_hidden": "true",
            "deep_search": "true",
            "api_key": serpapi_key
        }
        query_url = f"https://serpapi.com/search.json?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(query_url, headers={"User-Agent": "FlyHND-Agent/2.0"})

        with urllib.request.urlopen(req, timeout=30.0) as resp:  # deep_search responds slower
            data = json.loads(resp.read().decode("utf-8"))
            return self._parse_serpapi_response(data, origin, destination, departure_date, currency)

    def suggest_locations(
        self,
        query: str,
        country: str = "IN",
        language: str = "en"
    ) -> List[Dict[str, Any]]:
        """Return global city, airport, and region suggestions for a place query."""
        serpapi_key = os.getenv("SERPAPI_API_KEY")
        if not serpapi_key:
            raise ValueError("SERPAPI_API_KEY is required for global place suggestions.")
        if not query.strip():
            return []

        params = {
            "engine": "google_flights_autocomplete",
            "q": query.strip(),
            "gl": country.lower(),
            "hl": language,
            "api_key": serpapi_key
        }
        query_url = f"https://serpapi.com/search.json?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(query_url, headers={"User-Agent": "FlyHND-Agent/3.0"})
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("suggestions", [])

    def _parse_serpapi_response(
        self,
        data: Dict[str, Any],
        origin: str,
        destination: str,
        departure_date: str,
        currency: str = "INR"
    ) -> List[FlightOffer]:
        parsed: List[FlightOffer] = []
        now_utc = datetime.now(timezone.utc).isoformat()

        flight_groups = data.get("best_flights", []) + data.get("other_flights", [])

        for idx, group in enumerate(flight_groups):
            try:
                price_val = group.get("price")
                if not price_val:
                    continue

                total_dec = Decimal(str(price_val))
                # Google Flights exposes the displayed total, not a reliable tax/base split.
                base_dec = total_dec
                tax_dec = Decimal("0.00")

                flights = group.get("flights", [])
                if not flights:
                    continue

                first_flight = flights[0]
                last_flight = flights[-1]
                actual_origin = first_flight.get("departure_airport", {}).get("id", origin)
                actual_destination = last_flight.get("arrival_airport", {}).get("id", destination)

                airline = first_flight.get("airline", "Airline")
                flight_no = first_flight.get("flight_number", f"FL-{idx+100}")
                airline_code = flight_no.split()[0] if " " in flight_no else "FL"

                dep_time = first_flight.get("departure_airport", {}).get("time", f"{departure_date}T06:00:00")
                arr_time = last_flight.get("arrival_airport", {}).get("time", f"{departure_date}T16:00:00")

                total_dur_min = int(group.get("total_duration", 480))
                hours = total_dur_min // 60
                mins = total_dur_min % 60
                duration_str = f"{hours}h {mins}m"

                stops = len(flights) - 1
                layovers = [f.get("arrival_airport", {}).get("id", "") for f in flights[:-1] if f.get("arrival_airport")]

                cabin = "Economy"
                for f in flights:
                    tc = f.get("travel_class", "Economy")
                    if "premium" in tc.lower():
                        cabin = "Premium Economy"
                        break

                parsed_segments = []
                for seg_idx, f in enumerate(flights):
                    dep_ap = f.get("departure_airport", {})
                    arr_ap = f.get("arrival_airport", {})
                    seg_dur_min = int(f.get("duration", 0))
                    seg_h = seg_dur_min // 60
                    seg_m = seg_dur_min % 60
                    seg_dur_str = f"{seg_h}h {seg_m}m" if seg_dur_min > 0 else ""

                    # Layover after this segment (if not last)
                    layover_info = None
                    if seg_idx < len(flights) - 1:
                        raw_layovers = group.get("layovers", [])
                        if seg_idx < len(raw_layovers):
                            lo = raw_layovers[seg_idx]
                            lo_dur = int(lo.get("duration", 0))
                            lo_h = lo_dur // 60
                            lo_m = lo_dur % 60
                            layover_info = {
                                "duration_minutes": lo_dur,
                                "duration_str": f"{lo_h}h {lo_m}m",
                                "name": lo.get("name", arr_ap.get("name", "")),
                                "id": lo.get("id", arr_ap.get("id", ""))
                            }

                    parsed_segments.append({
                        "airline": f.get("airline", airline),
                        "flight_number": f.get("flight_number", ""),
                        "airplane": f.get("airplane", ""),
                        "travel_class": f.get("travel_class", cabin),
                        "duration": seg_dur_str,
                        "duration_minutes": seg_dur_min,
                        "departure_airport": {
                            "name": dep_ap.get("name", ""),
                            "id": dep_ap.get("id", ""),
                            "time": dep_ap.get("time", "")
                        },
                        "arrival_airport": {
                            "name": arr_ap.get("name", ""),
                            "id": arr_ap.get("id", ""),
                            "time": arr_ap.get("time", "")
                        },
                        "layover_after": layover_info
                    })

                offer = FlightOffer.create(
                    offer_id=f"google-flights-{idx+1}",
                    airline=airline,
                    airline_code=airline_code,
                    flight_number=flight_no,
                    origin=actual_origin,
                    destination=actual_destination,
                    departure_time=str(dep_time),
                    arrival_time=str(arr_time),
                    duration=duration_str,
                    duration_minutes=total_dur_min,
                    stops=stops,
                    layovers=layovers,
                    cabin=cabin,
                    baggage="7kg Cabin + Check-in per Airline Policy",
                    base_fare=base_dec,
                    tax_fees=tax_dec,
                    currency=currency.upper(),
                    source="LIVE_GOOGLE_FLIGHTS",
                    observation_timestamp=now_utc,
                    status="VALID",
                    fare_breakdown_available=False,
                    segments=parsed_segments
                )
                parsed.append(offer)
            except Exception:
                continue

        return parsed

    def search_live_amadeus(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        max_results: int = 20
    ) -> List[FlightOffer]:

        if not self.client_id or not self.client_secret:
            raise ValueError("Amadeus API credentials missing from environment.")

        now = time.time()
        if not self.amadeus_token or now >= self.token_expiry:
            token_url = "https://test.api.amadeus.com/v1/security/oauth2/token"
            token_data = urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }).encode("utf-8")

            req = urllib.request.Request(token_url, data=token_data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")

            with urllib.request.urlopen(req, timeout=5.0) as resp:
                token_json = json.loads(resp.read().decode("utf-8"))
                self.amadeus_token = token_json["access_token"]
                self.token_expiry = now + float(token_json.get("expires_in", 1799)) - 60

        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": str(adults),
            "currencyCode": "INR",
            "max": str(max_results)
        }
        query_url = f"https://test.api.amadeus.com/v2/shopping/flight-offers?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(query_url, method="GET")
        req.add_header("Authorization", f"Bearer {self.amadeus_token}")

        with urllib.request.urlopen(req, timeout=8.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return self._parse_amadeus_response(data.get("data", []))

    def _parse_amadeus_response(self, raw_offers: List[Dict[str, Any]]) -> List[FlightOffer]:
        parsed: List[FlightOffer] = []
        now_utc = datetime.now(timezone.utc).isoformat()

        for idx, offer in enumerate(raw_offers):
            try:
                price_data = offer.get("price", {})
                total_val = price_data.get("grandTotal", price_data.get("total", "0"))
                base_val = price_data.get("base", str(float(total_val) * 0.88))
                currency = price_data.get("currency", "INR")
                tax_val = float(total_val) - float(base_val)

                itinerary = offer["itineraries"][0]
                segments = itinerary["segments"]
                first_seg = segments[0]
                last_seg = segments[-1]

                airline_code = first_seg.get("carrierCode", "XX")
                flight_no = f"{airline_code}-{first_seg.get('number', '000')}"
                origin = first_seg["departure"]["iataCode"]
                destination = last_seg["arrival"]["iataCode"]
                dep_time = first_seg["departure"]["at"]
                arr_time = last_seg["arrival"]["at"]

                duration_str = itinerary.get("duration", "PT8H00M").replace("PT", "").replace("H", "h ").replace("M", "m")
                stops = len(segments) - 1
                layovers = [seg["arrival"]["iataCode"] for seg in segments[:-1]]

                cabin = "Economy"
                baggage = "7kg Cabin"
                tp = offer.get("travelerPricings", [])
                if tp:
                    fare_details = tp[0].get("fareDetailsBySegment", [])
                    if fare_details:
                        cabin = fare_details[0].get("cabin", "Economy")
                        bags = fare_details[0].get("includedCheckedBags", {})
                        if "weight" in bags:
                            baggage = f"{bags['weight']} {bags.get('weightUnit', 'KG')} Checked"
                        elif "quantity" in bags:
                            baggage = f"{bags['quantity']} Piece(s) Checked"

                airline_names = {
                    "6E": "IndiGo", "TR": "Scoot", "AK": "AirAsia",
                    "SQ": "Singapore Airlines", "MH": "Malaysia Airlines",
                    "UK": "Vistara", "AI": "Air India"
                }
                airline_name = airline_names.get(airline_code, f"Airlines {airline_code}")

                flight_obj = FlightOffer.create(
                    offer_id=f"amadeus-{offer.get('id', idx)}",
                    airline=airline_name,
                    airline_code=airline_code,
                    flight_number=flight_no,
                    origin=origin,
                    destination=destination,
                    departure_time=dep_time,
                    arrival_time=arr_time,
                    duration=duration_str,
                    duration_minutes=int(stops * 60 + 400),
                    stops=stops,
                    layovers=layovers,
                    cabin=cabin,
                    baggage=baggage,
                    base_fare=base_val,
                    tax_fees=tax_val,
                    currency=currency,
                    source="LIVE_API",
                    observation_timestamp=now_utc,
                    status="VALID"
                )
                parsed.append(flight_obj)
            except Exception:
                continue

        return parsed

    def search(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        mode: str = "offline",  
        adults: int = 1,
        currency: str = "INR"
    ) -> Tuple[List[FlightOffer], List[Dict[str, Any]]]:


        trace: List[Dict[str, Any]] = []

        if mode == "simulate_failure":
            trace.append({
                "step": "ATTEMPT_1",
                "event": "Live flight API call dispatched to provider",
                "status": "TIMEOUT",
                "details": "Simulated Gateway Timeout (HTTP 504) after 2000ms."
            })
            time.sleep(1.0)
            trace.append({
                "step": "RETRY_1",
                "event": "Executing bounded retry with exponential backoff (1000ms delay)",
                "status": "CONNECTION_REFUSED",
                "details": "Remote endpoint unreachable: Max retries (1/1) exceeded."
            })
            trace.append({
                "step": "FALLBACK",
                "event": "Recovering through SQLite persistent flight cache snapshot",
                "status": "ACTIVATED",
                "details": "SQLite flight_cache returned snapshot records."
            })
            cached_offers = self.ltm.get_cached_flights(origin, destination)
            if not cached_offers:
                demo = self.load_demo_flights()
                cached_offers = [o for o in demo if o.origin == origin and o.destination == destination]
            return cached_offers, trace

        if mode == "live":
            serpapi_key = os.getenv("SERPAPI_API_KEY")
            amadeus_configured = bool(self.client_id and self.client_secret)

            if serpapi_key:
                try:
                    trace.append({
                        "step": "LIVE_SERPAPI",
                        "event": f"Querying Live Google Flights via SerpApi for {origin} -> {destination} on {departure_date}",
                        "status": "IN_PROGRESS",
                        "details": "Dispatching HTTPS request to Google Flights engine."
                    })
                    live_results = self.search_live_serpapi(origin, destination, departure_date, adults=adults, currency=currency)
                    if live_results:
                        trace.append({
                            "step": "LIVE_SUCCESS",
                            "event": "Live flight offers successfully retrieved from Google Flights",
                            "status": "COMPLETED",
                            "details": f"Retrieved {len(live_results)} live offers."
                        })
                        return live_results, trace
                except Exception as e_serp:
                    trace.append({
                        "step": "SERPAPI_RETRY",
                        "event": f"SerpApi query failed ({str(e_serp)}). Bounded retry with 1s backoff.",
                        "status": "RETRYING",
                        "details": "Waiting 1.0s before retry attempt."
                    })
                    time.sleep(1.0)
                    try:
                        live_results = self.search_live_serpapi(origin, destination, departure_date, adults=adults, currency=currency)
                        if live_results:
                            return live_results, trace
                    except Exception as e_retry:
                        trace.append({
                            "step": "FALLBACK_TRIGGERED",
                            "event": f"Live query failed ({str(e_retry)}). Switching to local SQLite cache fallback.",
                            "status": "FALLBACK",
                            "details": "Recovered using persistent flight snapshot."
                        })
                        cached = self.ltm.get_cached_flights(origin, destination)
                        if cached:
                            return cached, trace

            elif amadeus_configured:
                try:
                    trace.append({
                        "step": "LIVE_AMADEUS",
                        "event": f"Querying Amadeus live endpoint for {origin} -> {destination} on {departure_date}",
                        "status": "IN_PROGRESS",
                        "details": "Dispatching HTTPS request."
                    })
                    live_results = self.search_live_amadeus(origin, destination, departure_date, adults=adults)
                    if live_results:
                        trace.append({
                            "step": "LIVE_SUCCESS",
                            "event": "Live flight offers received from Amadeus provider",
                            "status": "COMPLETED",
                            "details": f"Retrieved {len(live_results)} live offers."
                        })
                        return live_results, trace
                except Exception as e1:
                    trace.append({
                        "step": "RETRY_BACKOFF",
                        "event": f"Live query failed ({str(e1)}). Initiating bounded retry with backoff.",
                        "status": "RETRYING",
                        "details": "Waiting 1.0s before retry attempt."
                    })
                    time.sleep(1.0)
                    try:
                        live_results = self.search_live_amadeus(origin, destination, departure_date, adults=adults)
                        if live_results:
                            return live_results, trace
                    except Exception as e2:
                        trace.append({
                            "step": "RETRY_EXHAUSTED",
                            "event": f"Retry failed ({str(e2)}). Activating local SQLite cache fallback.",
                            "status": "FALLBACK_TRIGGERED",
                            "details": "Switching to persistent local snapshot."
                        })
                        cached = self.ltm.get_cached_flights(origin, destination)
                        if cached:
                            return cached, trace

            else:
                trace.append({
                    "step": "CONFIG_CHECK",
                    "event": "Missing live API credentials in .env (SERPAPI_API_KEY or AMADEUS_CLIENT_ID)",
                    "status": "FALLBACK_TRIGGERED",
                    "details": "Falling back to bundled benchmark dataset data/demo_flights.json."
                })
                demo = self.load_demo_flights()
                route_results = [o for o in demo if o.origin == origin and o.destination == destination]
                if not route_results:
                    trace[-1]["details"] = "No live provider is configured; the bundled demo only covers PNQ -> SIN. No unrelated demo fares were returned."
                return route_results, trace

        trace.append({
            "step": "OFFLINE_DEMO",
            "event": "Loading bundled synthetic benchmark dataset from data/demo_flights.json",
            "status": "COMPLETED",
            "details": "Deterministic offline dataset loaded successfully."
        })
        demo = self.load_demo_flights()
        route_results = [o for o in demo if o.origin == origin and o.destination == destination]
        if not route_results:
            trace[-1]["details"] = "The bundled offline demo only contains PNQ -> SIN. Configure a live provider for other routes."
        return route_results, trace
