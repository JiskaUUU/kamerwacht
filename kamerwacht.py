#!/usr/bin/env python3
"""Kamerwacht: stuurt een melding als er een nieuwe Direct offer-kamer in Delft online komt op roommatch.nl.

Gebruik:
  python3 kamerwacht.py --once      # eenmalig draaien en tonen wat het ziet (eerste keer: dit doen)
  python3 kamerwacht.py --test      # stuurt een testmelding
  python3 kamerwacht.py             # blijft draaien en controleert elke paar minuten

Alleen standaardbibliotheek, geen installatie nodig.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ---- Instellingen: pas deze aan -------------------------------------------
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "KIES-HIER-EEN-LANGE-ONRADEBARE-NAAM")  # lokaal: vul hier in. Op GitHub: als secret NTFY_TOPIC. Wie de naam kent kan meelezen.
CITY = "delft"                    # stad zoals in de data (hoofdletters maken niet uit)
MODEL = "reactiedatum"            # = Direct offer (reactiemoment bepaalt de volgorde)
INTERVAL_SECONDS = 180            # elke 3 minuten; niet lager, dat is onbeleefd voor de site
FAILS_BEFORE_ALERT = 5            # na zoveel mislukte pogingen achter elkaar krijg je een waarschuwing
LINK = "https://www.roommatch.nl/aanbod/studentenwoningen"  # tot we het directe pad van een advertentie weten
# ---------------------------------------------------------------------------

API = ("https://roommatching-aanbodapi.zig365.nl/api/v1/actueel-aanbod"
       "?limit=30&locale=nl_NL&page=0&sort=-publicationDate")
STATE = Path(__file__).with_name("gezien.json")


def fetch():
    req = urllib.request.Request(API, headers={"User-Agent": "kamerwacht (privegebruik)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        payload = json.load(r)
    rooms = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(rooms, list):
        raise ValueError("onverwachte structuur van het antwoord")
    return rooms


def is_match(room):
    return (str(room.get("city", "")).lower() == CITY.lower()
            and str(room.get("toewijzingModelCategorie", "")).lower() == MODEL.lower())


def describe(room):
    straat = f'{room.get("street", "?")} {room.get("houseNumber", "")}'.strip()
    huur = room.get("totalRent")
    huur_txt = f" - EUR {huur:.0f} p/m" if isinstance(huur, (int, float)) else ""
    sluit = room.get("closingDate")
    sluit_txt = f" - sluit {sluit}" if sluit else ""
    return f"{straat}, {room.get('city', '')}{huur_txt}{sluit_txt}"


def notify(title, message, priority="high", click=LINK):
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": priority, "Click": click, "Tags": "house"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=20).read()


def load_seen():
    if STATE.exists():
        return set(json.loads(STATE.read_text()))
    return None  # None = eerste keer draaien


def save_seen(seen):
    STATE.write_text(json.dumps(sorted(seen)))


def check(first_run_quiet=True):
    """Haalt de lijst op, meldt nieuwe matches. Geeft (aantal_nieuw, rooms) terug."""
    rooms = fetch()
    seen = load_seen()
    ids = {str(r.get("ID")) for r in rooms}
    if seen is None:
        # Eerste keer: alles wat er nu staat is 'oud', anders krijg je 30 meldingen tegelijk.
        save_seen(ids)
        return 0, rooms
    nieuw = [r for r in rooms if str(r.get("ID")) not in seen and is_match(r)]
    for r in nieuw:
        notify("Nieuwe kamer in " + str(r.get("city", CITY)), describe(r))
        print(f"MELDING: {describe(r)}", flush=True)
    save_seen(seen | ids)
    return len(nieuw), rooms


def show_overview(rooms):
    print(f"{len(rooms)} kamers opgehaald.")
    cats = sorted({str(r.get("toewijzingModelCategorie")) for r in rooms})
    print("Modellen in deze lijst:", ", ".join(cats))
    dates = [str(r.get("publicationDate")) for r in rooms]
    print("Nieuwste-eerst gesorteerd:", dates == sorted(dates, reverse=True))
    matches = [r for r in rooms if is_match(r)]
    print(f"Kamers die nu aan het filter ({CITY}, {MODEL}) voldoen: {len(matches)}")
    for r in matches:
        print("  -", describe(r), "| urlKey:", r.get("urlKey"))


def main():
    if NTFY_TOPIC.startswith("KIES-HIER"):
        sys.exit("Vul eerst NTFY_TOPIC in bovenin het script.")
    if "--test" in sys.argv:
        notify("Kamerwacht test", "Als je dit ziet, werkt de melding.", priority="default")
        print("Testmelding verstuurd.")
        return
    if "--once" in sys.argv:
        _, rooms = check()
        show_overview(rooms)
        return
    fails, alerted = 0, False
    print(f"Kamerwacht draait: {CITY}, {MODEL}, elke {INTERVAL_SECONDS} s. Stop met Ctrl+C.", flush=True)
    while True:
        try:
            check()
            fails, alerted = 0, False
        except (urllib.error.URLError, ValueError, OSError) as e:
            fails += 1
            print(f"Fout ({fails}x): {e}", flush=True)
            if fails >= FAILS_BEFORE_ALERT and not alerted:
                try:
                    notify("Kamerwacht werkt niet meer",
                           "De site geeft geen bruikbare data meer. Misschien is het adres veranderd.",
                           priority="default")
                    alerted = True
                except OSError:
                    pass
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
