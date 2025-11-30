import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import re

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# LISTE URLS
URLS = [
    "https://allofly.com/vols/dernieres-minutes/",
    "https://allofly.com/vol-pas-cher/paris-djerba/PAR-DJE/",
    "https://allofly.com/vol-pas-cher/djerba-paris/DJE-PAR/",
    "https://allofly.com/vol-pas-cher/tunis-paris/TUN-PAR/",
    "https://allofly.com/vol-pas-cher/paris-tunis/PAR-TUN/"
]

# MAP FUSEAUX HORAIRES
TZ_MAP = {
    "TUNIS": "Africa/Tunis",
    "DJERBA": "Africa/Tunis",
    "MONASTIR": "Africa/Tunis",
    "PARIS": "Europe/Paris",
    "LYON": "Europe/Paris",
    "NANTES": "Europe/Paris",
    "MARSEILLE": "Europe/Paris",
    "NICE": "Europe/Paris",
    "TOULOUSE": "Europe/Paris"
}

# MAP DES NOMS D'AÉROPORTS COMPLETS (Pour le GPS)
# Cela permet d'avoir une adresse précise dans le calendrier
AIRPORT_NAMES = {
    "TUN": "Aéroport Tunis-Carthage (TUN)",
    "DJE": "Aéroport Djerba-Zarzis (DJE)",
    "ORY": "Aéroport Paris-Orly (ORY)",
    "CDG": "Aéroport Paris-Charles de Gaulle (CDG)",
    "MIR": "Aéroport Monastir Habib-Bourguiba (MIR)",
    "LYS": "Aéroport Lyon-Saint Exupéry (LYS)",
    "MRS": "Aéroport Marseille-Provence (MRS)",
    "NTE": "Aéroport Nantes Atlantique (NTE)"
}


def get_timezone(city_name):
    if not city_name: return ZoneInfo("Europe/Paris")
    city_clean = city_name.strip().upper()
    for city_key, tz_str in TZ_MAP.items():
        if city_key in city_clean:
            return ZoneInfo(tz_str)
    return ZoneInfo("Europe/Paris")


def get_soup(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.content, 'html.parser')
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None


def extract_flights_to_dict(soup, events_dict):
    if not soup: return

    vols = soup.find_all("div", class_="product-item")

    for vol in vols:
        try:
            # --- INFO DE BASE ---
            infos = vol.find("div", class_="col-md-4")
            if not infos: continue
            blocs = infos.find_all("div", class_="item-duration")

            ville_dep = blocs[0].find_all("span", class_="d-block")[1].get_text(strip=True)
            heure_dep = blocs[0].find("span", class_="d-block").get_text(strip=True)
            ville_arr = blocs[2].find_all("span", class_="d-block")[1].get_text(strip=True)
            heure_arr = blocs[2].find("span", class_="d-block").get_text(strip=True)

            # --- FUSEAUX ---
            tz_depart = get_timezone(ville_dep)
            tz_arrivee = get_timezone(ville_arr)

            # --- DÉTAILS & AÉROPORTS ---
            details_div = vol.find("div", class_="item-detail")
            full_details_text = details_div.get_text() if details_div else ""

            code_dep = ""
            code_arr = ""
            if details_div:
                cols = details_div.find_all("div", class_="col-md-3")
                if len(cols) >= 2:
                    match_d = re.search(r"-\s*([A-Z]{3})\b", cols[0].get_text())
                    match_a = re.search(r"-\s*([A-Z]{3})\b", cols[1].get_text())
                    if match_d: code_dep = match_d.group(1)
                    if match_a: code_arr = match_a.group(1)

            # --- DATE ---
            col_date = vol.find("div", class_="col-md-2")
            txt_date = col_date.get_text() if col_date else ""
            match_date = re.search(r"(\d{2}/\d{2}/\d{4})", txt_date)
            if not match_date: continue
            date_str = match_date.group(1)

            # --- COMPAGNIE ---
            match_vol = re.search(r"\b([A-Z]{2}\d{3,4})\b", full_details_text)
            num_vol = match_vol.group(1) if match_vol else "Vol"

            compagnie = "Vol"
            if "TO" in num_vol or "TRANSAVIA" in full_details_text.upper():
                compagnie = "Transavia"
            elif "BJ" in num_vol or "NOUVELAIR" in full_details_text.upper():
                compagnie = "Nouvelair"
            elif "TU" in num_vol or "TUNISAIR" in full_details_text.upper():
                compagnie = "Tunisair"

            # --- PRIX ---
            col_prix = vol.find("div", class_="item-price")
            prix = "N/A"
            if col_prix:
                spans = col_prix.find_all("span")
                if len(spans) > 1: prix = spans[1].get_text(strip=True)

            # --- DATETIME ---
            format_dt = "%d/%m/%Y %HH%M"
            dt_start = datetime.strptime(f"{date_str} {heure_dep}", format_dt).replace(tzinfo=tz_depart)
            dt_end = datetime.strptime(f"{date_str} {heure_arr}", format_dt).replace(tzinfo=tz_arrivee)
            if dt_end < dt_start: dt_end += timedelta(days=1)

            # --- CONSTRUCTION DE L'ADRESSE (LOCATION) ---
            # Si on a le code aéroport (ex: ORY), on met le nom complet pour le GPS
            # Sinon, on met juste la ville de départ
            if code_dep in AIRPORT_NAMES:
                adresse_depart = AIRPORT_NAMES[code_dep]
            elif code_dep:
                adresse_depart = f"Aéroport {ville_dep} ({code_dep})"
            else:
                adresse_depart = f"Aéroport {ville_dep}"  # Fallback si pas de code

            # Pour le titre, on garde l'info trajet complet
            titre_dep = code_dep if code_dep else ville_dep
            titre_arr = code_arr if code_arr else ville_arr

            e = Event()
            icon = "🟢" if compagnie == "Transavia" else "✈️"
            e.name = f"{icon} {compagnie} : {titre_dep} > {titre_arr} ({prix})"
            e.begin = dt_start
            e.end = dt_end

            # ICI : L'adresse est uniquement l'aéroport de départ
            e.location = adresse_depart

            e.description = (
                f"Prix: {prix}\n"
                f"Compagnie: {compagnie} ({num_vol})\n"
                f"Trajet: {ville_dep} > {ville_arr}\n"
                f"Lien: https://allofly.com/vols/dernieres-minutes/"
            )
            e.uid = f"{num_vol}-{date_str}-{heure_dep}@allofly"

            # --- DÉDUPLICATION ---
            unique_key = f"{date_str}-{heure_dep}-{num_vol}"
            if unique_key in events_dict:
                existing = events_dict[unique_key]
                # Si le nouveau a un code aéroport précis (donc une adresse précise dans AIRPORT_NAMES)
                if "(" in e.location and "(" not in existing.location:
                    events_dict[unique_key] = e
            else:
                events_dict[unique_key] = e
                print(f"✅ Ajout: {e.name}")

        except Exception as err:
            continue


def main():
    cal = Calendar()
    unique_events = {}
    print("🚀 Démarrage (Adresse Départ GPS)...")
    for url in URLS:
        soup = get_soup(url)
        extract_flights_to_dict(soup, unique_events)

    for event in unique_events.values():
        cal.events.add(event)

    with open("allofly_vols.ics", "w", encoding="utf-8") as f:
        f.writelines(cal.serialize())
    print(f"\n🏁 Terminé ! {len(unique_events)} vols exportés.")


if __name__ == "__main__":
    main()
