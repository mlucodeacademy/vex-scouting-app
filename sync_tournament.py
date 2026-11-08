#!/usr/bin/env python3
"""
33111C VEX Tournament Live API Sync Worker
Runs locally or as a scheduled background cron/action.
Pulls live matches, scores, and rankings from events.vex.com API and pushes to Firebase RTDB.
Token is kept secure in this environment and NEVER exposed to client browsers.
"""
import sys, json, os, urllib.request, datetime, zoneinfo

# US State / Region to Timezone mapping
US_REGION_TZ = {
    # Eastern (UTC-5 in standard time)
    "Connecticut": "America/New_York", "Delaware": "America/New_York", "Florida": "America/New_York",
    "Georgia": "America/New_York", "Maine": "America/New_York", "Maryland": "America/New_York",
    "Massachusetts": "America/New_York", "Michigan": "America/Detroit", "New Hampshire": "America/New_York",
    "New Jersey": "America/New_York", "New York": "America/New_York", "North Carolina": "America/New_York",
    "Ohio": "America/New_York", "Pennsylvania": "America/New_York", "Rhode Island": "America/New_York",
    "South Carolina": "America/New_York", "Vermont": "America/New_York", "Virginia": "America/New_York",
    "West Virginia": "America/New_York", "District of Columbia": "America/New_York",
    # Central (UTC-6 in standard time)
    "Alabama": "America/Chicago", "Arkansas": "America/Chicago", "Illinois": "America/Chicago",
    "Iowa": "America/Chicago", "Kansas": "America/Chicago", "Louisiana": "America/Chicago",
    "Minnesota": "America/Chicago", "Mississippi": "America/Chicago", "Missouri": "America/Chicago",
    "Nebraska": "America/Chicago", "North Dakota": "America/Chicago", "Oklahoma": "America/Chicago",
    "South Dakota": "America/Chicago", "Tennessee": "America/Chicago", "Texas": "America/Chicago",
    "Wisconsin": "America/Chicago",
    # Mountain (UTC-7 in standard time)
    "Arizona": "America/Phoenix", "Colorado": "America/Denver", "Idaho": "America/Boise",
    "Montana": "America/Denver", "New Mexico": "America/Denver", "Utah": "America/Denver",
    "Wyoming": "America/Denver",
    # Pacific & Hawaii / Alaska
    "California": "America/Los_Angeles", "Nevada": "America/Los_Angeles", "Oregon": "America/Los_Angeles",
    "Washington": "America/Los_Angeles", "Alaska": "America/Anchorage", "Hawaii": "America/Pacific/Honolulu"
}

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

def derive_event_timezone(event_id):
    """Derive event local timezone dynamically from event location or coordinates."""
    try:
        ev = api_get(f"/events/{event_id}")
        loc = ev.get("location", {})
        region = (loc.get("region") or "").strip()
        if region in US_REGION_TZ:
            tz_name = US_REGION_TZ[region]
            print(f"[Timezone] Derived {tz_name} from event region: {region} ({loc.get('city', '')})")
            return zoneinfo.ZoneInfo(tz_name)
        coords = loc.get("coordinates") or {}
        lon = coords.get("lon")
        if lon is not None:
            if lon > -85: tz_name = "America/New_York"
            elif lon > -100: tz_name = "America/Chicago"
            elif lon > -114: tz_name = "America/Denver"
            else: tz_name = "America/Los_Angeles"
            print(f"[Timezone] Derived {tz_name} from event longitude: {lon}")
            return zoneinfo.ZoneInfo(tz_name)
    except Exception as e:
        print(f"[WARN] Could not derive timezone from event metadata: {e}")
    return zoneinfo.ZoneInfo("America/Chicago")

EVENT_TZ = derive_event_timezone(EVENT_ID)

def fmt_iso_time(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone(EVENT_TZ)
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

def sync(event_id=None, is_active=True):
    eid = event_id or EVENT_ID
    ev_tz = derive_event_timezone(eid)
    now_str = datetime.datetime.now().strftime("%I:%M:%S %p")
    print(f"[{now_str}] Syncing from RobotEvents API for Event {eid}...")

    # Fetch event metadata to get divisions
    try:
        ev_meta = api_get(f"/events/{eid}")
    except Exception as e:
        print(f"[ERROR] Could not fetch metadata for event {eid}: {e}")
        return

    divisions = ev_meta.get("divisions", [])
    div_id = divisions[0].get("id", 1) if divisions else 1

    # 1. Fetch all matches (Quals + Elims)
    matches = []
    page = 1
    while True:
        try:
            data = api_get(f"/events/{eid}/divisions/{div_id}/matches?page={page}&per_page=100")
            page_items = data.get("data", [])
            matches.extend(page_items)
            meta = data.get("meta", {})
            if not meta.get("next_page_url") or page >= meta.get("last_page", 1):
                break
            page += 1
        except Exception as e:
            print(f"[WARN] Error fetching matches page {page} for event {eid}: {e}")
            break

    # 2. Fetch rankings
    rankings = []
    official_rankings = []
    try:
        rank_data = api_get(f"/events/{eid}/divisions/{div_id}/rankings?per_page=100")
        official_rankings = sorted(rank_data.get("data", []), key=lambda r: r.get("rank", 999))
        for r in official_rankings:
            r["is_official"] = True
        rankings = list(official_rankings)
    except Exception as e:
        print(f"[WARN] Error fetching rankings for event {eid}: {e}")

    # 3. Fetch skills runs
    live_skills = {}
    try:
        skills_data = api_get(f"/events/{eid}/skills?per_page=100").get("data", [])
        for s in skills_data:
            tnum = (s.get("team") or {}).get("name")
            if not tnum:
                continue
            if tnum not in live_skills:
                live_skills[tnum] = {"driver": 0, "programming": 0}
            stype = s.get("type")
            if stype in ("driver", "programming"):
                live_skills[tnum][stype] = max(live_skills[tnum][stype], s.get("score", 0))
    except Exception as e:
        print(f"[WARN] Error fetching skills for event {eid}: {e}")

    # 4. Fetch teams list
    teams_list = []
    team_profiles = {}
    try:
        teams_data = api_get(f"/events/{eid}/teams?per_page=100").get("data", [])
        teams_list = teams_data
        for t in teams_data:
            num = (t.get("number") or "").upper()
            if num:
                sk = live_skills.get(num, {})
                drv = sk.get("driver", 0)
                prg = sk.get("programming", 0)
                tot = drv + prg
                team_profiles[num] = {
                    "id": t.get("id"),
                    "name": t.get("team_name", ""),
                    "robot": t.get("robot_name", ""),
                    "org": t.get("organization", ""),
                    "city": (t.get("location") or {}).get("city", ""),
                    "grade": t.get("grade", ""),
                    "bestDriver": drv,
                    "bestProg": prg,
                    "bestSkills": tot
                }
    except Exception as e:
        print(f"[WARN] Error fetching teams for event {eid}: {e}")

    # 5. Build live_matches list, detect current on-field match, scores
    latest_started_num = 1
    scores_dict = {}
    live_matches = []

    def fmt_match_time(iso_str):
        if not iso_str:
            return ""
        try:
            dt = datetime.datetime.fromisoformat(iso_str)
            if dt.tzinfo is not None:
                dt = dt.astimezone(ev_tz)
            return dt.strftime("%-I:%M %p")
        except Exception:
            return ""

    sorted_matches = sorted(matches, key=round_sort_key)
    for seq_idx, m in enumerate(sorted_matches, start=1):
        mid = format_match_id(m)
        started_iso = m.get("started")
        sched_iso = m.get("scheduled")
        started_str = fmt_match_time(started_iso)
        sched_str = fmt_match_time(sched_iso)

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

        is_scored = bool(m.get("scored") or r_score > 0 or b_score > 0)
        if is_scored or started_iso:
            latest_started_num = max(latest_started_num, seq_idx)
            scores_dict[mid] = {
                "red": r_score,
                "blue": b_score,
                "scheduled": sched_str,
                "started": started_str,
                "done": is_scored
            }

    # 6. Rank computation fallback
    api_total_played = sum((r.get("wins", 0) + r.get("losses", 0) + r.get("ties", 0)) for r in rankings)
    team_stats = {}
    for r in rankings:
        t_obj = r.get("team") or {}
        t_name = t_obj.get("name")
        if t_name:
            team_stats[t_name] = {
                "team": t_obj,
                "wins": 0, "losses": 0, "ties": 0, "wp": 0, "ap": r.get("ap", 0), "sp": 0,
                "high_score": 0, "total_points": 0, "played": 0
            }

    scored_qual_count = 0
    for m in sorted_matches:
        if m.get("round") != 2:
            continue
        r_al = next((a for a in m.get("alliances", []) if a.get("color") == "red"), {})
        b_al = next((a for a in m.get("alliances", []) if a.get("color") == "blue"), {})
        rs = r_al.get("score", 0) or 0
        bs = b_al.get("score", 0) or 0
        if not (m.get("scored") or rs > 0 or bs > 0):
            continue
        scored_qual_count += 1
        lose_score = min(rs, bs)
        r_teams = [(t.get("team") or {}).get("name") for t in r_al.get("teams", []) if (t.get("team") or {}).get("name")]
        b_teams = [(t.get("team") or {}).get("name") for t in b_al.get("teams", []) if (t.get("team") or {}).get("name")]

        for t_name in r_teams:
            st = team_stats.setdefault(t_name, {"team": {"name": t_name}, "wins": 0, "losses": 0, "ties": 0, "wp": 0, "ap": 0, "sp": 0, "high_score": 0, "total_points": 0, "played": 0})
            st["played"] += 1
            st["sp"] += lose_score
            st["total_points"] += rs
            st["high_score"] = max(st["high_score"], rs)
            if rs > bs: st["wins"] += 1; st["wp"] += 2
            elif rs < bs: st["losses"] += 1
            else: st["ties"] += 1; st["wp"] += 1

        for t_name in b_teams:
            st = team_stats.setdefault(t_name, {"team": {"name": t_name}, "wins": 0, "losses": 0, "ties": 0, "wp": 0, "ap": 0, "sp": 0, "high_score": 0, "total_points": 0, "played": 0})
            st["played"] += 1
            st["sp"] += lose_score
            st["total_points"] += bs
            st["high_score"] = max(st["high_score"], bs)
            if bs > rs: st["wins"] += 1; st["wp"] += 2
            elif bs < rs: st["losses"] += 1
            else: st["ties"] += 1; st["wp"] += 1

    computed_total_played = sum(st["played"] for st in team_stats.values())
    rankings_official = bool(api_total_played >= computed_total_played and api_total_played > 0)
    if computed_total_played > api_total_played:
        sorted_computed = sorted(
            team_stats.values(),
            key=lambda x: (
                x["wp"] / x["played"] if x["played"] else -1,
                x["wp"], x["ap"],
                x["sp"] / x["played"] if x["played"] else -1,
                x["sp"], x["high_score"], x["total_points"]
            ),
            reverse=True
        )
        rankings = []
        for idx, item in enumerate(sorted_computed, start=1):
            item["rank"] = idx
            item["is_official"] = False
            rankings.append(item)

    # 7. Push tournament data to Firebase RTDB under /vex_33111c/events/{eid}/
    # Note: Use PATCH or individual PUTs so that user-submitted /events/{eid}/scouting is never overwritten!
    event_payload = {
        "metadata": {
            "id": eid,
            "name": ev_meta.get("name"),
            "sku": ev_meta.get("sku"),
            "start": ev_meta.get("start"),
            "end": ev_meta.get("end"),
            "location": ev_meta.get("location", {})
        },
        "last_sync": now_str,
        "event_id": eid,
        "onFieldMatchNum": latest_started_num,
        "matches": live_matches,
        "scores": scores_dict,
        "rankings": rankings,
        "official_rankings": official_rankings,
        "rankings_official": rankings_official,
        "live_skills": live_skills,
        "teams": teams_list,
        "team_profiles": team_profiles
    }

    data_bytes = json.dumps(event_payload).encode("utf-8")
    patch_req = urllib.request.Request(f"{RTDB_URL}/events/{eid}.json", data=data_bytes, method="PATCH", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(patch_req) as r:
        print(f"[{eid}] Synced {len(live_matches)} matches, {len(scores_dict)} scored & {len(rankings)} rankings to /events/{eid}! Status: {r.status}", flush=True)

    # If this is the active live tournament, also update /live_event
    if is_active:
        patch_live = urllib.request.Request(f"{RTDB_URL}/live_event.json", data=data_bytes, method="PATCH", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(patch_live) as r:
            print(f"[{eid}] Mirrored to /live_event. Status: {r.status}", flush=True)

if __name__ == "__main__":
    import time, argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=int, default=EVENT_ID, help=f"RobotEvents Event ID (default: {EVENT_ID})")
    parser.add_argument("--sync-all", action="store_true", help="Sync all known season events in events_list")
    parser.add_argument("--loop", type=int, default=0, help="Poll interval in seconds (0 = run once)")
    parser.add_argument("--duration", type=int, default=0, help="Max total duration in seconds when looping (0 = infinite)")
    parser.add_argument("--force", action="store_true", help="Run even outside game day hours")
    args = parser.parse_args()

    def is_game_day_hours():
        now = datetime.datetime.now()
        # Game day: Saturday, Nov 7, 2026 between 7:30 AM and 6:30 PM local time
        if now.date() != datetime.date(2026, 11, 7):
            return False
        hm = (now.hour, now.minute)
        return (7, 30) <= hm <= (18, 30)

    target_event = args.event or EVENT_ID

    if args.sync_all:
        print("Syncing all events from season list...")
        for eid in [65031, 61615, 64952, 64639]:
            try:
                sync(event_id=eid, is_active=(eid == EVENT_ID))
            except Exception as e:
                print(f"[ERROR] Failed syncing event {eid}: {e}")
        sys.exit(0)

    if args.loop > 0:
        start_ts = time.time()
        while True:
            if not args.force and not is_game_day_hours():
                print(f"[{datetime.datetime.now().strftime('%I:%M:%S %p')}] Outside game day hours (Nov 7, 2026 7:30 AM - 6:30 PM). Stopping sync.", flush=True)
                break
            try:
                sync(event_id=target_event, is_active=(target_event == EVENT_ID))
            except Exception as e:
                print(f"[WARN] Sync error: {e}", flush=True)
            if args.duration > 0 and (time.time() - start_ts + args.loop) >= args.duration:
                break
            time.sleep(args.loop)
    else:
        if not args.force and not is_game_day_hours():
            print("Outside game day hours (Nov 7, 2026 7:30 AM - 6:30 PM). Use --force to run manually.", flush=True)
        else:
            sync(event_id=target_event, is_active=(target_event == EVENT_ID))
