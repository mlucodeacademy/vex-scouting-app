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
    
    # 2. Fetch rankings (sort ascending #1 -> #N since RobotEvents API returns descending)
    rank_data = api_get(f"/events/{EVENT_ID}/divisions/1/rankings?per_page=100")
    official_rankings = sorted(rank_data.get("data", []), key=lambda r: r.get("rank", 999))
    for r in official_rankings:
        r["is_official"] = True
    rankings = list(official_rankings)

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

    # 5. If RobotEvents /rankings lags behind live scored matches (e.g. all 0-0-0), compute live Meet Rankings from scored Qual matches
    api_total_played = sum((r.get("wins", 0) + r.get("losses", 0) + r.get("ties", 0)) for r in rankings)
    team_stats = {}
    for r in rankings:
        t_obj = r.get("team") or {}
        t_name = t_obj.get("name")
        if t_name:
            team_stats[t_name] = {
                "team": t_obj,
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "wp": 0,
                "ap": r.get("ap", 0),
                "sp": 0,
                "high_score": 0,
                "total_points": 0,
                "played": 0
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
            if rs > bs:
                st["wins"] += 1
                st["wp"] += 2
            elif rs < bs:
                st["losses"] += 1
            else:
                st["ties"] += 1
                st["wp"] += 1

        for t_name in b_teams:
            st = team_stats.setdefault(t_name, {"team": {"name": t_name}, "wins": 0, "losses": 0, "ties": 0, "wp": 0, "ap": 0, "sp": 0, "high_score": 0, "total_points": 0, "played": 0})
            st["played"] += 1
            st["sp"] += lose_score
            st["total_points"] += bs
            st["high_score"] = max(st["high_score"], bs)
            if bs > rs:
                st["wins"] += 1
                st["wp"] += 2
            elif bs < rs:
                st["losses"] += 1
            else:
                st["ties"] += 1
                st["wp"] += 1

    computed_total_played = sum(st["played"] for st in team_stats.values())
    rankings_official = bool(api_total_played >= computed_total_played and api_total_played > 0)
    if computed_total_played > api_total_played:
        sorted_computed = sorted(
            team_stats.values(),
            key=lambda x: (
                x["wp"] / x["played"] if x["played"] else -1,
                x["wp"],
                x["ap"],
                x["sp"] / x["played"] if x["played"] else -1,
                x["sp"],
                x["high_score"],
                x["total_points"]
            ),
            reverse=True
        )
        rankings = []
        for idx, item in enumerate(sorted_computed, start=1):
            item["rank"] = idx
            item["is_official"] = False
            rankings.append(item)

    # Push to Firebase RTDB
    payload = {
        "last_sync": now_str,
        "event_id": EVENT_ID,
        "onFieldMatchNum": latest_started_num,
        "matches": live_matches,
        "scores": scores_dict,
        "rankings": rankings,
        "official_rankings": official_rankings,
        "rankings_official": rankings_official,
        "live_skills": live_skills
    }
    
    data_bytes = json.dumps(payload).encode("utf-8")
    put_req = urllib.request.Request(f"{RTDB_URL}/live_event.json", data=data_bytes, method="PUT", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(put_req) as r:
        print(f"Synced {len(live_matches)} matches, {len(scores_dict)} scored & {len(rankings)} rankings to Firebase! Status: {r.status}", flush=True)

if __name__ == "__main__":
    import time, argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", type=int, default=0, help="Poll interval in seconds (0 = run once)")
    parser.add_argument("--duration", type=int, default=0, help="Max total duration in seconds when looping (0 = infinite)")
    args = parser.parse_args()

    if args.loop > 0:
        start_ts = time.time()
        while True:
            try:
                sync()
            except Exception as e:
                print(f"[WARN] Sync error: {e}", flush=True)
            if args.duration > 0 and (time.time() - start_ts + args.loop) >= args.duration:
                break
            time.sleep(args.loop)
    else:
        sync()
