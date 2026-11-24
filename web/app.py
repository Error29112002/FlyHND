"""
FlyHND 3.0 — Flask Web Application
Provides a usable web interface for global flight search and price comparison.
Connects directly to the agent search pipeline (agents/, tools/, models/).
Email is fully removed — results display in the browser.
"""

import os
import sys
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_project_root, ".env"))
except ImportError:
    pass

from flask import Flask, render_template, request, jsonify

from models.memory_models import SearchRequest
from agents.orchestrator import RequestCoordinator
from tools.flight_search_tool import FlightSearchTool
from tools.booking_links import airline_site, price_check_url

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
_template_dir = os.path.join(os.path.dirname(__file__), "templates")
_static_dir   = os.path.join(os.path.dirname(__file__), "static")

app = Flask(__name__, template_folder=_template_dir, static_folder=_static_dir)
app.config["JSON_SORT_KEYS"] = False


def _has_live_credentials() -> bool:
    return bool(
        os.getenv("SERPAPI_API_KEY")
        or (os.getenv("AMADEUS_CLIENT_ID") and os.getenv("AMADEUS_CLIENT_SECRET"))
    )


def _provider_label() -> str:
    if os.getenv("SERPAPI_API_KEY"):
        return "SerpApi / Google Flights"
    if os.getenv("AMADEUS_CLIENT_ID"):
        return "Amadeus"
    return "none"


def _resolve_to_provider_id(tool: FlightSearchTool, user_input: str) -> str:
    """
    Ensure the user input is a valid provider identifier (IATA code or Google Flights kgmid).
    If the user entered free text (e.g., 'Pune, Maharashtra' or 'New Delhi' or 'japan' or 'japn'),
    resolve it automatically using Google Flights location autocomplete.
    """
    cleaned = (user_input or "").strip()
    if not cleaned:
        return ""

    # Already an IATA code (3 letters) or a kgmid (/m/...)
    if (len(cleaned) == 3 and cleaned.isalpha()) or cleaned.startswith("/m/"):
        return cleaned

    try:
        suggs = tool.suggest_locations(cleaned)
        if suggs:
            top = suggs[0]
            # If top match is an airport or has an associated airport IATA, prefer that
            airports = top.get("airports", [])
            if airports and airports[0].get("id"):
                return airports[0]["id"]
            if top.get("id"):
                return top["id"]
    except Exception:
        pass

    return cleaned


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        live_configured=_has_live_credentials(),
        provider_label=_provider_label(),
    )


@app.route("/api/suggest")
def api_suggest():
    """
    GET /api/suggest?q=<query>
    Returns location suggestions from SerpApi Google Flights autocomplete,
    enriching cities with their IATA airport codes, and including specific airports.
    """
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify({"suggestions": [], "error": None})

    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if not serpapi_key:
        return jsonify({
            "suggestions": [],
            "error": "No live provider configured. Add SERPAPI_API_KEY to .env to enable location lookup."
        })

    try:
        tool = FlightSearchTool()
        raw  = tool.suggest_locations(query=query, country="IN", language="en")
        suggestions = []
        seen = set()

        for item in raw:
            name = item.get("name") or item.get("description") or ""
            city_id = item.get("id", "")
            item_type = item.get("type", "")
            airports = item.get("airports", [])

            primary_id = city_id
            iata_code = ""
            if airports and airports[0].get("id"):
                iata_code = airports[0]["id"]

            # Main place entry
            display_label = name
            if iata_code and f"({iata_code})" not in display_label:
                display_label = f"{name} ({iata_code})"

            key = (display_label, primary_id)
            if key not in seen and name:
                seen.add(key)
                suggestions.append({
                    "label": display_label,
                    "id": primary_id,
                    "iata": iata_code,
                    "type": item_type or "city"
                })

            # Also show individual airports for domestic/international precision
            for ap in airports:
                ap_name = ap.get("name")
                ap_id = ap.get("id")
                if ap_name and ap_id:
                    ap_label = f"{ap_name} ({ap_id})"
                    ap_key = (ap_label, ap_id)
                    if ap_key not in seen:
                        seen.add(ap_key)
                        suggestions.append({
                            "label": ap_label,
                            "id": ap_id,
                            "iata": ap_id,
                            "type": "airport"
                        })

        return jsonify({"suggestions": suggestions, "error": None})
    except Exception as exc:
        return jsonify({"suggestions": [], "error": str(exc)})


@app.route("/api/search", methods=["POST"])
def api_search():
    """
    POST /api/search
    Body (JSON):
      {
        "origin_id":       "<IATA, kgmid, or place name>",
        "origin_label":    "<Human-readable>",
        "dest_id":         "<IATA, kgmid, or place name>",
        "dest_label":      "<Human-readable>",
        "date":            "YYYY-MM-DD",
        "return_date":     "YYYY-MM-DD" | null,
        "passengers":      1,
        "currency":        "INR",
        "budget":          null | <number>
      }
    """
    body = request.get_json(silent=True) or {}

    origin_raw   = (body.get("origin_id")    or "").strip()
    dest_raw     = (body.get("dest_id")      or "").strip()
    origin_label = (body.get("origin_label") or origin_raw).strip()
    dest_label   = (body.get("dest_label")   or dest_raw).strip()
    date_str     = (body.get("date")         or "").strip()
    return_date  = (body.get("return_date")  or "").strip() or None
    passengers   = int(body.get("passengers") or 1)
    currency     = (body.get("currency")     or "INR").strip().upper()
    budget_raw   = body.get("budget")

    # ── Validation ──────────────────────────────────────────────────────
    errors = []
    if not origin_raw:
        errors.append("Origin is required.")
    if not dest_raw:
        errors.append("Destination is required.")
    if origin_raw and dest_raw and origin_raw.lower() == dest_raw.lower():
        errors.append("Origin and destination must be different.")
    if not date_str:
        errors.append("Departure date is required.")
    else:
        try:
            dep_dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dep_dt.date() < datetime.today().date():
                errors.append("Departure date must be today or in the future.")
        except ValueError:
            errors.append("Invalid date format; expected YYYY-MM-DD.")
    if return_date:
        try:
            ret_dt = datetime.strptime(return_date, "%Y-%m-%d")
            dep_dt = datetime.strptime(date_str, "%Y-%m-%d")
            if ret_dt <= dep_dt:
                errors.append("Return date must be after the departure date.")
        except ValueError:
            errors.append("Invalid return date format; expected YYYY-MM-DD.")
    if passengers < 1 or passengers > 9:
        errors.append("Passengers must be between 1 and 9.")
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    # ── Auto-resolve raw place names to valid Provider IDs ──────────────
    search_tool = FlightSearchTool()
    origin_id = _resolve_to_provider_id(search_tool, origin_raw)
    dest_id   = _resolve_to_provider_id(search_tool, dest_raw)

    if not origin_id:
        origin_id = origin_raw
    if not dest_id:
        dest_id = dest_raw

    # ── Budget: optional ────────────────────────────────────────────────
    budget = None
    if budget_raw not in (None, "", "null"):
        try:
            budget = Decimal(str(budget_raw))
            if budget <= 0:
                budget = None
        except InvalidOperation:
            budget = None

    budget_ceiling = budget if budget is not None else Decimal("9999999.00")
    mode = "live" if _has_live_credentials() else "offline"

    # ── Run outbound search ─────────────────────────────────────────────
    try:
        outbound_req = SearchRequest(
            origin=origin_id,
            destination=dest_id,
            departure_date=date_str,
            budget=budget_ceiling,
            passengers=passengers,
            currency=currency,
            route=f"{origin_label} → {dest_label}",
        )
        coordinator = RequestCoordinator()
        outbound_report = coordinator.execute_workflow(
            search_request=outbound_req,
            mode=mode,
        )
    except Exception as exc:
        return jsonify({"ok": False, "errors": [f"Search failed: {exc}"]}), 500

    # ── Run return search if requested ──────────────────────────────────
    return_report = None
    if return_date:
        try:
            return_req = SearchRequest(
                origin=dest_id,
                destination=origin_id,
                departure_date=return_date,
                budget=budget_ceiling,
                passengers=passengers,
                currency=currency,
                route=f"{dest_label} → {origin_label}",
            )
            return_report = coordinator.execute_workflow(
                search_request=return_req,
                mode=mode,
            )
        except Exception:
            return_report = None   # non-fatal; outbound results still returned

    # ── Annotate and sort offers ────────────────────────────────────────
    source_map = {
        "LIVE_GOOGLE_FLIGHTS": "Live — Google Flights via SerpApi",
        "LIVE_API":            "Live — Amadeus",
        "OFFLINE_DEMO":        "Demo data (not live prices)",
        "OFFLINE_CACHE":       "Cached demo data (not live prices)",
    }

    def annotate(offers, is_demo, leg_date, leg_origin, leg_dest):
        try:
            sorted_offers = sorted(offers, key=lambda x: float(x.get("total_fare_num", x.get("total_fare", 0))))
        except Exception:
            sorted_offers = offers

        if sorted_offers:
            cheapest_id  = sorted_offers[0].get("offer_id")
            fastest      = min(sorted_offers, key=lambda x: int(x.get("duration_minutes", 9999)))
            fastest_id   = fastest.get("offer_id")
            direct       = [o for o in sorted_offers if int(o.get("stops", 1)) == 0]
            best_val_id  = direct[0].get("offer_id") if direct else cheapest_id

            for o in sorted_offers:
                badges = []
                if o.get("offer_id") == cheapest_id:  badges.append("cheapest")
                if o.get("offer_id") == fastest_id:   badges.append("fastest")
                if o.get("offer_id") == best_val_id:  badges.append("best_value")
                o["badges"] = badges

        for o in sorted_offers:
            o["source_label"] = source_map.get(o.get("source", ""), o.get("source", ""))
            o["over_budget"]  = (
                budget is not None and
                Decimal(str(o.get("total_fare", "0"))) > budget
            )
            # Links use the searched date (demo offers carry fixed dates of their own).
            # Demo airlines may not fly the route, so filtering Google Flights by them can show nothing.
            o["airline_url"] = airline_site(o.get("airline_code", ""), o.get("airline", ""))
            o["price_check_url"] = price_check_url(
                o.get("origin") or leg_origin, o.get("destination") or leg_dest,
                leg_date, "" if is_demo else o.get("airline", ""), currency,
            )

        return sorted_offers

    outbound_all  = outbound_report.get("price_comparison", [])
    outbound_offers = annotate(outbound_all, mode == "offline", date_str, origin_id, dest_id)

    return_offers = []
    if return_report:
        return_all   = return_report.get("price_comparison", [])
        return_offers = annotate(return_all, mode == "offline", return_date, dest_id, origin_id)

    is_demo   = mode == "offline"
    demo_note = (
        "No live provider is configured. Results shown are demo data for the "
        "Pune → Singapore route only — not real fares for your search."
        if is_demo else None
    )

    return jsonify({
        "ok": True,
        "mode": mode,
        "is_demo": is_demo,
        "demo_note": demo_note,
        "currency": currency,
        "budget_applied": str(budget) if budget else None,
        "outbound": {
            "route": outbound_req.route,
            "date": date_str,
            "total_found": len(outbound_offers),
            "offers": outbound_offers,
        },
        "return": {
            "route": f"{dest_label} → {origin_label}" if return_date else None,
            "date": return_date,
            "total_found": len(return_offers),
            "offers": return_offers,
        } if return_date else None,
        "recovery_trace": outbound_report.get("recovery_trace", []),
    })
