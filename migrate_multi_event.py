import urllib.request, urllib.parse, json, os, datetime, zoneinfo, re, time

TOKEN = ""
with open("/Users/mlu/github/vex-scouting-app/.env") as f:
    for line in f:
        if line.startswith("ROBOTEVENTS_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip()

RTDB_URL = "https://my-project-1524591195518-default-rtdb.firebaseio.com/vex_33111c"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdwNt6qgAiVjDCJENCsS-nvZEpEM_lE00ivLVH9KuKMEnDtsw/formResponse"

def api_get(endpoint):
    url = f"https://events.vex.com/api/v2{endpoint}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": "VexScout-Sync/1.0"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def rtdb_put(path, data):
    url = f"{RTDB_URL}/{path}.json"
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req) as r:
        return r.status

def rtdb_get(path):
    url = f"{RTDB_URL}/{path}.json"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"rtdb_get({path}) failed:", e)
        return None

# Oct 24 Scouting Data from RECF 10/24 Scouting Form (Responses)
OCT24_DATA = [
    ["10/24/2026 9:00:45","Andrew","63310G    Valkyrie","","2","1","2","0","3",""],
    ["10/24/2026 9:18:43","Andrew","1412J    BANSHEE!","","4","5","5","5","5",""],
    ["10/24/2026 9:58:24","Andrew","77360Z    Come and Take It","","3","4","3","3","2",""],
    ["10/24/2026 9:58:57","Andrew","77786H    CyberKings","","2","3","4","3","5",""],
    ["10/24/2026 9:59:31","Other","77360Z    Come and Take It","","3","2","3","2","3",""],
    ["10/24/2026 10:05:25","Other","16329E    Wraith","","0","3","1","0","1","Tipped over"],
    ["10/24/2026 10:09:41","Other","77786C    Bears C","","1","1","2","0","2",""],
    ["10/24/2026 10:09:44","Andrew","77786C    Bears C","","1","3","3","2","2",""],
    ["10/24/2026 10:14:45","Andrew","1412J    BANSHEE!","","4","5","5","5","5",""],
    ["10/24/2026 10:14:57","Other","1412J    BANSHEE!","","3","5","5","4","4","Can stack 6 levels"],
    ["10/24/2026 10:21:01","Other","19713N    Robotics II","","0","3","3","3","4",""],
    ["10/24/2026 10:29:54","Other","1412E    Hypercharged!","","0","0","0","0","2",""],
    ["10/24/2026 10:35:04","Roger","22603B    Black","","2","4","4","3","3","Missed auton, good at scoring from matchload"],
    ["10/24/2026 10:41:10","Other","54600A    Team Dynamite","","0","2","3","0","4",""],
    ["10/24/2026 10:42:15","Roger","77038V","","0","3","3","2","2","Didn’t try to toggle during match, decent match loading and scoring "],
    ["10/24/2026 10:45:26","Other","3162H    HHS GearHeads","","1","0","1","3","3",""],
    ["10/24/2026 11:06:25","Other","83280Y    Lobos Rojos","","4","4","3","3","4",""],
    ["10/24/2026 11:15:55","Other","22603B    Black","","4","3","4","3","4",""],
    ["10/24/2026 11:16:29","Andrew","98250E","","1","1","2","1","2",""],
    ["10/24/2026 11:17:11","Andrew","43485K    The Falconeers","","0","3","3","2","2",""],
    ["10/24/2026 11:18:16","Andrew","19713C    Robotics II","","0","2","2","1","1",""],
    ["10/24/2026 11:21:37","Andrew","77786S    Skunkworks","","0","2","3","1","1",""],
    ["10/24/2026 11:22:39","Andrew","63310A    Event Horizon","","4","4","5","3","4",""],
    ["10/24/2026 13:39:26","Other","1412J    BANSHEE!","Q47","3","5","5","4","4","Stack 7 levels"]
]

EVENTS_CONFIG = [
    {
        "id": 65031,
        "sku": "RE-V5RC-26-5031",
        "name": "Texan Standoff (Houston TX)",
        "short_name": "Texan Standoff",
        "date": "2026-11-07",
        "status": "completed",
        "location": "Houston, TX"
    },
    {
        "id": 61615,
        "sku": "RE-V5RC-25-1615",
        "name": "Texas Halloween Madness (Houston TX)",
        "short_name": "Halloween Madness",
        "date": "2026-10-24",
        "status": "completed",
        "location": "Houston, TX"
    },
    {
        "id": 64952,
        "sku": "RE-V5RC-26-4952",
        "name": "Sunshine Showdown Signature Event (Orlando FL)",
        "short_name": "Sunshine Showdown",
        "date": "2026-12-27",
        "status": "upcoming",
        "location": "Orlando, FL"
    },
    {
        "id": 64639,
        "sku": "RE-V5RC-26-4639",
        "name": "Moody Mania (Galveston TX)",
        "short_name": "Moody Mania",
        "date": "2027-01-02",
        "status": "upcoming",
        "location": "Galveston, TX"
    }
]

print("1. Updating events list in Firebase...")
rtdb_put("events_list", EVENTS_CONFIG)
rtdb_put("active_event_id", 65031)

print("2. Archiving Nov 7 Texan Standoff (65031) in Firebase...")
nov7_live = rtdb_get("live_event")
nov7_scouting = rtdb_get("scouting")
if nov7_live:
    rtdb_put("events/65031/metadata", nov7_live.get("metadata", {}))
    rtdb_put("events/65031/teams", nov7_live.get("teams", []))
    rtdb_put("events/65031/matches", nov7_live.get("matches", []))
    rtdb_put("events/65031/rankings", nov7_live.get("rankings", []))
if nov7_scouting:
    rtdb_put("events/65031/scouting", nov7_scouting)
print(f"Archived 65031 with {len(nov7_scouting) if nov7_scouting else 0} scouting reports.")

print("3. Fetching and syncing Oct 24 Halloween Madness (61615) data from API...")
try:
    ev_61615 = api_get("/events/61615")
    div_id = ev_61615.get("divisions", [{}])[0].get("id", 1)
    
    # Teams
    teams_res = api_get("/events/61615/teams")
    teams_61615 = teams_res.get("data", [])
    
    # Matches
    matches_res = api_get(f"/events/61615/divisions/{div_id}/matches")
    matches_61615 = matches_res.get("data", [])
    
    # Rankings
    rankings_res = api_get(f"/events/61615/divisions/{div_id}/rankings")
    rankings_61615 = rankings_res.get("data", [])
    
    rtdb_put("events/61615/metadata", {
        "id": 61615,
        "name": ev_61615.get("name"),
        "sku": ev_61615.get("sku"),
        "start": ev_61615.get("start"),
        "end": ev_61615.get("end"),
        "location": ev_61615.get("location", {})
    })
    rtdb_put("events/61615/teams", teams_61615)
    rtdb_put("events/61615/matches", matches_61615)
    rtdb_put("events/61615/rankings", rankings_61615)
    print(f"Synced 61615: {len(teams_61615)} teams, {len(matches_61615)} matches, {len(rankings_61615)} rankings.")
except Exception as e:
    print("Error syncing 61615 from API:", e)

print("4. Migrating Oct 24 scouting notes to Firebase RTDB (/vex_33111c/events/61615/scouting)...")
oct24_scouting_rtdb = {}
for i, row in enumerate(OCT24_DATA):
    ts, submitter, raw_team, match, auton, loading, scoring, toggle, driving, comment = row
    clean_team = raw_team.strip().split()[0].upper()
    entry_id = f"sc_oct24_{i:02d}_{clean_team.lower()}"
    oct24_scouting_rtdb[entry_id] = {
        "id": entry_id,
        "ts": ts,
        "submitter": submitter.strip(),
        "team": clean_team,
        "match": match.strip(),
        "auton": int(auton) if auton.isdigit() else 0,
        "loading": int(loading) if loading.isdigit() else 0,
        "scoring": int(scoring) if scoring.isdigit() else 0,
        "toggle": int(toggle) if toggle.isdigit() else 0,
        "driving": int(driving) if driving.isdigit() else 0,
        "comment": comment.strip()
    }
rtdb_put("events/61615/scouting", oct24_scouting_rtdb)
print(f"Saved {len(oct24_scouting_rtdb)} scouting reports into Firebase for event 61615.")

print("5. Submitting Oct 24 entries to Google Form so they appear in Unified Google Sheet...")
headers = {"Content-Type": "application/x-www-form-urlencoded"}
for i, row in enumerate(OCT24_DATA):
    ts, submitter, raw_team, match, auton, loading, scoring, toggle, driving, comment = row
    tagged_comment = f"[Halloween 10/24 | {ts}] {comment}".strip()
    form_data = {
        "entry.458463111": submitter.strip(),
        "entry.1603355979": raw_team.strip(),
        "entry.149974184": match.strip(),
        "entry.1562660712": auton,
        "entry.1665007477": loading,
        "entry.1623910075": scoring,
        "entry.153495163": toggle,
        "entry.1220642473": driving,
        "entry.51037885": tagged_comment
    }
    encoded = urllib.parse.urlencode(form_data).encode("utf-8")
    try:
        req = urllib.request.Request(FORM_URL, data=encoded, headers=headers, method="POST")
        with urllib.request.urlopen(req) as resp:
            pass
        print(f"  [{i+1}/{len(OCT24_DATA)}] Posted {raw_team.strip()[:10]} to Google Form")
        time.sleep(0.3)
    except Exception as e:
        print(f"  Failed posting row {i}: {e}")

print("6. Fetching initial metadata & teams for upcoming events 64952 and 64639...")
for eid in [64952, 64639]:
    try:
        ev = api_get(f"/events/{eid}")
        teams = api_get(f"/events/{eid}/teams").get("data", [])
        rtdb_put(f"events/{eid}/metadata", {
            "id": eid,
            "name": ev.get("name"),
            "sku": ev.get("sku"),
            "start": ev.get("start"),
            "end": ev.get("end"),
            "location": ev.get("location", {})
        })
        rtdb_put(f"events/{eid}/teams", teams)
        print(f"Saved upcoming event {eid}: {ev.get('name')} with {len(teams)} teams.")
    except Exception as e:
        print(f"Could not load upcoming event {eid}:", e)

print("\n--- MIGRATION COMPLETE ---")
