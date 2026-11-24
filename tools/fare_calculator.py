import re
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple, Dict, Any
from datetime import datetime

from models.flight import FlightOffer
from models.memory_models import ConflictArbitrationRecord


class FareCalculator:


    @staticmethod
    def compute_total(base_fare: Any, tax_fees: Any) -> Decimal:
        b = Decimal(str(base_fare)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        t = Decimal(str(tax_fees)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return (b + t).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def is_under_budget(total_fare: Decimal, budget: Decimal) -> bool:
        return total_fare <= budget

    @staticmethod
    def parse_duration_minutes(duration_str: str) -> int:
        if not duration_str:
            return 0

        clean = duration_str.upper().replace("PT", "").strip()
        hours = 0
        minutes = 0

        h_match = re.search(r"(\d+)\s*H", clean)
        if h_match:
            hours = int(h_match.group(1))

        m_match = re.search(r"(\d+)\s*M", clean)
        if m_match:
            minutes = int(m_match.group(1))

        return (hours * 60) + minutes

    @staticmethod
    def calculate_rank_score(flight: FlightOffer) -> float:

        price_num = float(flight.total_fare)
        stop_penalty = flight.stops * 1200.0
        duration_penalty = flight.duration_minutes * 1.5
        return price_num + stop_penalty + duration_penalty

    @classmethod
    def arbitrate_offers(
        cls, offers: List[FlightOffer]
    ) -> Tuple[List[FlightOffer], List[ConflictArbitrationRecord]]:

        grouped: Dict[str, List[FlightOffer]] = {}
        for offer in offers:
            # Same trip = same flights in order; connections that share only a first leg are different offers.
            legs = "+".join(s.get("flight_number", "") for s in offer.segments) or offer.flight_number
            key = f"{legs.strip().upper()}_{offer.origin}_{offer.destination}"
            grouped.setdefault(key, []).append(offer)

        arbitrated_offers: List[FlightOffer] = []
        conflicts_logged: List[ConflictArbitrationRecord] = []

        for key, offer_list in grouped.items():
            if len(offer_list) == 1:
                arbitrated_offers.append(offer_list[0])
                continue

            def parse_time(o: FlightOffer):
                ts = o.observation_timestamp
                try:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    return datetime.min

            # Newest quote wins; on a tie (one live response), the cheaper fare wins.
            sorted_offers = sorted(offer_list, key=lambda o: (parse_time(o), -o.total_fare), reverse=True)
            winner = sorted_offers[0]
            older = sorted_offers[1]

            diff = winner.total_fare - older.total_fare
            discrepancy_note = (
                f"Arbitration resolved: Newest quote from [{winner.source}] @ {winner.observation_timestamp} "
                f"(₹{winner.total_fare:,.2f}) selected over older [{older.source}] @ {older.observation_timestamp} "
                f"(₹{older.total_fare:,.2f}). Fare variance: ₹{diff:+,.2f} INR."
            )
            winner.discrepancy_note = discrepancy_note
            older.status = "STALE_SUPERSEDED"

            record = ConflictArbitrationRecord(
                flight_number=winner.flight_number,
                older_quote=older.total_fare,
                older_source=older.source,
                older_timestamp=older.observation_timestamp,
                newer_quote=winner.total_fare,
                newer_source=winner.source,
                newer_timestamp=winner.observation_timestamp,
                winner_source=winner.source,
                fare_difference=diff,
                rationale=discrepancy_note
            )
            conflicts_logged.append(record)
            arbitrated_offers.append(winner)

        return arbitrated_offers, conflicts_logged
