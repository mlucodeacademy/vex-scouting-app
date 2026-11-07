#!/usr/bin/env python3
"""
33111C VEX Tournament Live API Sync Worker
Runs locally or as a scheduled background cron/action.
Pulls live matches, scores, and rankings from events.vex.com API and pushes to Firebase RTDB.
Token is kept secure in this environment and NEVER exposed to client browsers.
"""
import sys, json, os, urllib.request, datetime

def load_token():
    tok = os.environ.get("ROBOTEVENTS_TOKEN", "").strip()
    if tok:
        return tok
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("ROBOTEVENTS_TOKEN="):
                    return line.split("=", 1)[1].strip()
    raise RuntimeError("Missing ROBOTEVENTS_TOKEN in environment or .env")

TOKEN = load_token()
RTDB_URL = "https://my-project-1524591195518-default-rtdb.firebaseio.com/vex_33111c"
EVENT_ID = 65031 # Texan Standoff Nov 7, 2026

def api_get(endpoint):
    url = f"https://events.vex.com/api/v2{endpoint}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": "VexScout-Sync/1.0"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def fmt_iso_time(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
        return dt.strftime("%-I:%M %p")
    except Exception:
        return ""

def format_match_id(m):
    rnd = m.get("round")
    num = m.get("matchnum", 1)
    inst = m.get("instance", 1)
    if rnd == 2:
        return f"Q{num}"
    elif rnd == 1:
        return f"P{num}"
    elif rnd == 6:
        return f"R16 {inst}-{num}"
    elif rnd == 3:
        return f"QF {inst}-{num}"
    elif rnd == 4:
        return f"SF {inst}-{num}"
    elif rnd == 5:
        return f"F{num}"
    name = m.get("name", "")
    return name.replace("Qualifier #", "Q").replace("#", "") or f"M{num}"

def round_sort_key(m):
    rnd_order = {1: 0, 2: 1, 6: 2, 3: 3, 4: 4, 5: 5}.get(m.get("round", 2), 9)
    return (rnd_order, m.get("instance", 1), m.get("matchnum", 0))

def sync():
    now_str = datetime.datetime.now().strftime("%I:%M:%S %p")
    print(f"[{now_str}] Syncing from RobotEvents API for Event {EVENT_ID}...")
    
    # 1. Fetch all matches (Quals + Elims)
    matches = []
    page = 1
    while True:
        data = api_get(f"/events/{EVENT_ID}/divisions/1/matches?page={page}&per_page=100")
        page_items = data.get("data", [])
        matches.extend(page_items)
        meta = data.get("meta", {})
        if not meta.get("next_page_url") or page >= meta.get("last_page", 1):
            break
        page += 1
    
    # 2. Fetch rankings
    rank_data = api_get(f"/events/{EVENT_ID}/divisions/1/rankings?per_page=100")
    rankings = rank_data.get("data", [])

    # 3. Fetch live event skills runs
    skills_data = api_get(f"/events/{EVENT_ID}/skills?per_page=100").get("data", [])
    live_skills = {}
    for s in skills_data:
        tnum = (s.get("team") or {}).get("name")
        if not tnum:
            continue
        if tnum not in live_skills:
            live_skills[tnum] = {"driver": 0, "programming": 0}
        stype = s.get("type")
        if stype in ("driver", "programming"):
            live_skills[tnum][stype] = max(live_skills[tnum][stype], s.get("score", 0))
    
    # 4. Build live_matches list, detect current on-field match, scores, and scheduled/actual times
    latest_started_num = 1
    scores_dict = {}
    live_matches = []
    
    sorted_matches = sorted(matches, key=round_sort_key)
    for seq_idx, m in enumerate(sorted_matches, start=1):
        mid = format_match_id(m)
        started_iso = m.get("started")
        sched_iso = m.get("scheduled")
        started_str = fmt_iso_time(started_iso)
        sched_str = fmt_iso_time(sched_iso)

        red_teams = []
        blue_teams = []
        r_score = 0
        b_score = 0
        for a in m.get("alliances", []):
            color = a.get("color")
            t_names = [(t.get("team") or {}).get("name", "TBD") for t in a.get("teams", [])]
            while len(t_names) < 2:
                t_names.append("TBD")
            if color == "red":
                red_teams = t_names
                r_score = a.get("score", 0)
            elif color == "blue":
                blue_teams = t_names
                b_score = a.get("score", 0)

        live_matches.append({
            "id": mid,
            "num": seq_idx,
            "time": sched_str or "TBD",
            "started": started_str,
            "field": m.get("field") or "TBD",
            "red1": red_teams[0] if len(red_teams) > 0 else "TBD",
            "red2": red_teams[1] if len(red_teams) > 1 else "TBD",
            "blue1": blue_teams[0] if len(blue_teams) > 0 else "TBD",
            "blue2": blue_teams[1] if len(blue_teams) > 1 else "TBD"
        })

        is_scored = bool(m.get("scored") or started_iso or r_score > 0 or b_score > 0)
        if is_scored:
            latest_started_num = max(latest_started_num, seq_idx)
            scores_dict[mid] = {
                "red": r_score,
                "blue": b_score,
                "scheduled": sched_str,
                "started": started_str,
                "done": bool(m.get("scored") or r_score > 0 or b_score > 0)
            }

    # Push to Firebase RTDB
    payload = {
        "last_sync": now_str,
        "event_id": EVENT_ID,
        "onFieldMatchNum": latest_started_num,
        "matches": live_matches,
        "scores": scores_dict,
        "rankings": rankings,
        "live_skills": live_skills
    }
    
    data_bytes = json.dumps(payload).encode("utf-8")
    put_req = urllib.request.Request(f"{RTDB_URL}/live_event.json", data=data_bytes, method="PUT", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(put_req) as r:
        print(f"Synced {len(live_matches)} matches, {len(scores_dict)} scored & {len(rankings)} rankings to Firebase! Status: {r.status}")

if __name__ == "__main__":
    sync()
