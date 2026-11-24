"""
FlyHND — outbound booking links.
Gives each offer a link to the airline's own site and a live price check on
Google Flights for the same route, date and airline, so the user can book there.
"""

from urllib.parse import quote_plus, urlencode

# shortcut: airline homepages only (airlines share no deep-link format); add per-airline deep links if one matters.
AIRLINE_SITES = {
    "6E": "https://www.goindigo.in/",
    "AI": "https://www.airindia.com/",
    "UK": "https://www.airindia.com/",          # Vistara merged into Air India in Nov 2024
    "IX": "https://www.airindiaexpress.com/",
    "QP": "https://www.akasaair.com/",
    "SG": "https://www.spicejet.com/",
    "TR": "https://www.flyscoot.com/",
    "SQ": "https://www.singaporeair.com/",
    "AK": "https://www.airasia.com/",
    "FD": "https://www.airasia.com/",
    "D7": "https://www.airasia.com/",
    "MH": "https://www.malaysiaairlines.com/",
    "TG": "https://www.thaiairways.com/",
    "CX": "https://www.cathaypacific.com/",
    "VN": "https://www.vietnamairlines.com/",
    "GA": "https://www.garuda-indonesia.com/",
    "EK": "https://www.emirates.com/",
    "QR": "https://www.qatarairways.com/",
    "EY": "https://www.etihad.com/",
    "TK": "https://www.turkishairlines.com/",
    "BA": "https://www.britishairways.com/",
    "LH": "https://www.lufthansa.com/",
    "AF": "https://www.airfrance.com/",
    "KL": "https://www.klm.com/",
    "UA": "https://www.united.com/",
    "AA": "https://www.aa.com/",
    "DL": "https://www.delta.com/",
    "NH": "https://www.ana.co.jp/",
    "JL": "https://www.jal.co.jp/",
    "QF": "https://www.qantas.com/",
}


def airline_site(airline_code: str, airline_name: str) -> str:
    """The airline's own website, or a web search for it when the code is unknown."""
    url = AIRLINE_SITES.get((airline_code or "").upper())
    if url:
        return url
    return "https://www.google.com/search?q=" + quote_plus(f"{airline_name} official website book flights")


def price_check_url(origin: str, destination: str, date: str, airline_name: str,
                    currency: str = "INR") -> str:
    """Google Flights for this route, date and airline: shows the live fare and the sites that sell it."""
    q = f"Flights from {origin} to {destination} on {date} one way"
    if airline_name:
        q += f" on {airline_name}"
    return "https://www.google.com/travel/flights?" + urlencode({"q": q, "curr": currency, "hl": "en"})


if __name__ == "__main__":
    assert airline_site("tr", "Scoot") == "https://www.flyscoot.com/"
    assert airline_site("ZZ", "Acme Air").startswith("https://www.google.com/search?q=Acme+Air")
    u = price_check_url("PNQ", "SIN", "2027-01-15", "Scoot", "SGD")
    assert "PNQ+to+SIN+on+2027-01-15" in u and "on+Scoot" in u and "curr=SGD" in u, u
    print("booking_links ok")
