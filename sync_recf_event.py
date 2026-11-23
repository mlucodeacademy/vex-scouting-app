#!/usr/bin/env python3
"""
33111C RECF Events Importer (recfevents.org)
Fetches public event details and registered teams from recfevents.org/Events/Details/<id>
and pushes them cleanly to Firebase RTDB without overwriting any existing scouting notes.
"""
import argparse, datetime, html as html_lib, json, re, urllib.request

RTDB_URL = "https://my-project-1524591195518-default-rtdb.firebaseio.com/vex_33111c"

def rtdb_put(sub_path, data):
    url = f"{RTDB_URL}/{sub_path}.json"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req) as r:
        return r.status

def rtdb_get(sub_path):
    url = f"{RTDB_URL}/{sub_path}.json"
    try:
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

def import_recf_event(event_id=645):
    url = f"https://recfevents.org/Events/Details/{event_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "VexScout-RECF-Import/1.0"})
    raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")

    # Extract title
    title_m = re.search(r"<title>(.*?)</title>", raw, re.S | re.I)
    ev_name = html_lib.unescape(title_m.group(1)).split("|")[0].strip() if title_m else f"RECF Event {event_id}"

    # Extract SKU (e.g. ACH20266718)
    sku_m = re.search(r"\b(ACH\d+|ENG\d+|INS\d+|ADC\d+)\b", raw)
    sku = sku_m.group(1) if sku_m else f"RECF-{event_id}"

    # Extract registered teams table
    table_m = re.search(r'<table[^>]*class="[^"]*app-grid-cards[^"]*"[^>]*>(.*?)</table>', raw, re.S | re.I)
    teams_list = []
    team_profiles = {}

    if table_m:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_m.group(1), re.S | re.I)
        for idx, r in enumerate(rows[1:], start=1):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S | re.I)
            if len(tds) >= 3:
                c0_text = html_lib.unescape(re.sub(r"<[^>]+>", "|", tds[0]))
                c0_parts = [p.strip() for p in c0_text.split("|") if p.strip()]
                raw_num = c0_parts[0] if c0_parts else ""
                clean_num = re.sub(r"^(?:Achieve|Engage|Inspire)_", "", raw_num, flags=re.I).strip().upper()
                name = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", tds[1]))).strip()
                org = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", tds[2]))).strip()
                if not clean_num:
                    continue
                teams_list.append({
                    "id": idx,
                    "number": clean_num,
                    "raw_number": raw_num,
                    "team_name": name,
                    "organization": org,
                    "grade": "High School",
                })
                team_profiles[clean_num] = {
                    "id": idx,
                    "name": name,
                    "robot": "",
                    "org": org,
                    "city": "",
                    "grade": "High School",
                    "bestDriver": 0,
                    "bestProg": 0,
                    "bestSkills": 0,
                }

    now_str = datetime.datetime.now().strftime("%I:%M:%S %p")
    metadata = {
        "id": event_id,
        "sku": sku,
        "name": ev_name,
        "source": "recfevents",
        "url": url,
        "start": "2026-11-23",
        "end": "2026-11-24",
        "location": {
            "venue": "CCISD Learner Support Center",
            "address": "2903 Falcon Pass Drive",
            "city": "Houston",
            "region": "Texas",
            "postcode": "77062",
        },
    }

    # Preserve existing matches/scores/rankings/scouting if already present
    existing = rtdb_get(f"events/{event_id}") or {}

    rtdb_put(f"events/{event_id}/metadata", metadata)
    rtdb_put(f"events/{event_id}/teams", teams_list)
    rtdb_put(f"events/{event_id}/team_profiles", team_profiles)
    rtdb_put(f"events/{event_id}/last_sync", now_str)
    if "matches" not in existing:
        rtdb_put(f"events/{event_id}/matches", [])
    if "scores" not in existing:
        rtdb_put(f"events/{event_id}/scores", {})
    if "rankings" not in existing:
        rtdb_put(f"events/{event_id}/rankings", [])
    if "official_rankings" not in existing:
        rtdb_put(f"events/{event_id}/official_rankings", [])
    if "rankings_official" not in existing:
        rtdb_put(f"events/{event_id}/rankings_official", False)

    # Update events_list in Firebase RTDB
    events_list = [
        {
            "id": 645,
            "sku": sku,
            "name": f"{ev_name} (Houston TX)",
            "short_name": "Space City Achieve",
            "date": "Nov 23–24, 2026",
            "status": "active",
            "location": "Houston, TX",
            "source": "recfevents",
            "url": url,
        },
        {
            "id": 65031,
            "sku": "RE-V5RC-26-5031",
            "name": "Texan Standoff (Houston TX)",
            "short_name": "Texan Standoff",
            "date": "Nov 7, 2026",
            "status": "completed",
            "location": "Houston, TX",
        },
        {
            "id": 61615,
            "sku": "RE-V5RC-25-1615",
            "name": "Texas Halloween Madness (Houston TX)",
            "short_name": "Halloween Madness",
            "date": "Oct 24, 2026",
            "status": "completed",
            "location": "Houston, TX",
        },
        {
            "id": 64952,
            "sku": "RE-V5RC-26-4952",
            "name": "Sunshine Showdown Signature Event (Orlando FL)",
            "short_name": "Sunshine Showdown",
            "date": "Dec 27–29, 2026",
            "status": "upcoming",
            "location": "Orlando, FL",
        },
        {
            "id": 64639,
            "sku": "RE-V5RC-26-4639",
            "name": "Moody Mania (Galveston TX)",
            "short_name": "Moody Mania",
            "date": "Jan 2, 2027",
            "status": "upcoming",
            "location": "Galveston, TX",
        },
    ]
    rtdb_put("events_list", events_list)
    rtdb_put("active_event_id", event_id)
    print(f"Imported RECF Event {event_id} ({ev_name}, SKU {sku}) with {len(teams_list)} teams to Firebase RTDB!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=int, default=645, help="RECF Events numeric ID (default: 645)")
    args = parser.parse_args()
    import_recf_event(args.event)
