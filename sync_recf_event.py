#!/usr/bin/env python3
"""
33111C RECF Events + Red Shirt Synergy (Competition Control C2) Live Sync Worker
- Pulls team names/orgs from recfevents.org/Events/Details/<id>
- Pulls live match schedule, scores, rankings, and Solo Match (Skills) from Red Shirt Synergy C2 feed
- Pushes cleanly to Firebase RTDB under /vex_33111c/events/<id>/ without touching /scouting
"""
import argparse, datetime, html as html_lib, json, re, time, urllib.request, zoneinfo

RTDB_URL = "https://my-project-1524591195518-default-rtdb.firebaseio.com/vex_33111c"
DEFAULT_RECF_EVENT_ID = 645
DEFAULT_RSS_EVENT_UUID = "8377958b-2c6e-4c04-a972-772248ddd148"

def rtdb_put(sub_path, data):
    url = f"{RTDB_URL}/{sub_path}.json"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status

def rtdb_get(sub_path):
    url = f"{RTDB_URL}/{sub_path}.json"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

def fetch_recf_teams(event_id):
    """Fetch team names and organizations from recfevents.org."""
    url = f"https://recfevents.org/Events/Details/{event_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "VexScout-RECF-Sync/1.0"})
    raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")

    title_m = re.search(r"<title>(.*?)</title>", raw, re.S | re.I)
    ev_name = html_lib.unescape(title_m.group(1)).split("|")[0].strip() if title_m else f"RECF Event {event_id}"
    sku_m = re.search(r"\b(ACH\d+|ENG\d+|INS\d+|ADC\d+)\b", raw)
    sku = sku_m.group(1) if sku_m else f"RECF-{event_id}"

    profiles = {}
    table_m = re.search(r'<table[^>]*class="[^"]*app-grid-cards[^"]*"[^>]*>(.*?)</table>', raw, re.S | re.I)
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
                if clean_num:
                    profiles[clean_num] = {
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
    return ev_name, sku, url, profiles

def parse_match_score(score_obj):
    """Flexibly parse C2 score formats (dict, string, or None)."""
    if score_obj is None:
        return 0, 0, False
    if isinstance(score_obj, dict):
        r = score_obj.get("red")
        if r is None:
            r = score_obj.get("redScore")
        b = score_obj.get("blue")
        if b is None:
            b = score_obj.get("blueScore")
        if r is not None or b is not None:
            return int(r or 0), int(b or 0), True
        return 0, 0, False
    if isinstance(score_obj, str):
        m = re.search(r"(\d+)\s*[-–:]\s*(\d+)", score_obj)
        if m:
            return int(m.group(1)), int(m.group(2)), True
    return 0, 0, False

def sync_recf_live(event_id=DEFAULT_RECF_EVENT_ID, rss_uuid=DEFAULT_RSS_EVENT_UUID, refresh_recf_teams=False):
    now_str = datetime.datetime.now().strftime("%I:%M:%S %p")
    rss_url = f"https://redshirtsynergy.com/api/community/event-guide?event={rss_uuid}"
    req = urllib.request.Request(rss_url, headers={"User-Agent": "VexScout-RECF-Sync/1.0"})
    guide = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))

    ev_info = guide.get("event") or {}
    comp = guide.get("competition") or {}
    tz_name = comp.get("timeZone") or "America/Chicago"
    ev_tz = zoneinfo.ZoneInfo(tz_name)

    # Load existing team_profiles from RTDB (or refresh from recfevents.org)
    team_profiles = rtdb_get(f"events/{event_id}/team_profiles") or {}
    ev_name = ev_info.get("name") or f"RECF Event {event_id}"
    sku = "ACH20266718"
    recf_url = ev_info.get("detailsUrl") or f"https://recfevents.org/Events/Details/{event_id}"

    if refresh_recf_teams or not team_profiles:
        try:
            r_name, r_sku, r_url, recf_profiles = fetch_recf_teams(event_id)
            ev_name = r_name or ev_name
            sku = r_sku or sku
            recf_url = r_url or recf_url
            for k, v in recf_profiles.items():
                if k not in team_profiles:
                    team_profiles[k] = v
                else:
                    team_profiles[k]["name"] = v["name"] or team_profiles[k].get("name", "")
                    team_profiles[k]["org"] = v["org"] or team_profiles[k].get("org", "")
        except Exception as e:
            print(f"[WARN] Could not refresh recfevents.org teams: {e}", flush=True)

    # 1. Solo Matches (Skills)
    live_skills = {}
    for s in comp.get("solos") or []:
        tnum = (s.get("team") or "").strip().upper()
        if not tnum:
            continue
        drv = int(s.get("driving") or 0)
        cod = int(s.get("coding") or 0)
        tot = drv + cod
        live_skills[tnum] = {"driver": drv, "programming": cod}
        if tnum not in team_profiles:
            team_profiles[tnum] = {
                "id": len(team_profiles) + 1,
                "name": "",
                "robot": "",
                "org": "",
                "city": "",
                "grade": "High School",
                "bestDriver": drv,
                "bestProg": cod,
                "bestSkills": tot,
            }
        else:
            team_profiles[tnum]["bestDriver"] = drv
            team_profiles[tnum]["bestProg"] = cod
            team_profiles[tnum]["bestSkills"] = tot

    # 2. Matches & Scores
    def fmt_local_time(iso_str):
        if not iso_str:
            return ""
        try:
            dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            dt = dt.astimezone(ev_tz)
            return dt.strftime("%a %-I:%M %p")
        except Exception:
            return ""

    raw_matches = comp.get("matches") or []
    live_matches = []
    scores_dict = {}
    latest_started_num = 1

    # Load persistent DQ overrides from RTDB (never overwritten by sync)
    # Format: { "Q49": { "33111C": true }, ... }
    raw_dq = rtdb_get(f"events/{event_id}/dq_overrides") or {}
    dq_overrides = {}
    if isinstance(raw_dq, dict):
        for mid_k, teams_map in raw_dq.items():
            if isinstance(teams_map, dict):
                flagged = {t.strip().upper() for t, v in teams_map.items() if v}
                if flagged:
                    dq_overrides[mid_k.strip().upper()] = flagged

    # Stats from C2 rankings (official rank; W/L/T/WP/AP/SP if provided by C2)
    raw_rankings = comp.get("rankings") or []
    has_official_wlt = any(
        isinstance(r, dict) and any(k in r for k in ("wins", "losses", "ties", "record"))
        for r in raw_rankings
    )
    team_stats = {}
    for r in raw_rankings:
        tnum = (r.get("team") or "").strip().upper()
        if tnum:
            if tnum not in team_profiles:
                team_profiles[tnum] = {
                    "id": len(team_profiles) + 1,
                    "name": "",
                    "robot": "",
                    "org": "",
                    "city": "",
                    "grade": "High School",
                    "bestDriver": 0,
                    "bestProg": 0,
                    "bestSkills": 0,
                }
            wins = int(r.get("wins") or 0)
            losses = int(r.get("losses") or 0)
            ties = int(r.get("ties") or 0)
            if isinstance(r.get("record"), str):
                rec_m = re.match(r"(\d+)\s*-\s*(\d+)\s*-\s*(\d+)", r["record"].strip())
                if rec_m:
                    wins, losses, ties = int(rec_m.group(1)), int(rec_m.group(2)), int(rec_m.group(3))
            rp_val = r.get("rp") if r.get("rp") is not None else r.get("avgRp")
            ap_val = r.get("ap") if r.get("ap") is not None else r.get("avgAp")
            ep_val = r.get("ep") if r.get("ep") is not None else r.get("avgEp")
            team_stats[tnum] = {
                "team": {"name": tnum},
                "rank": r.get("rank", 999),
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "wp": int(r.get("wp") or 0),
                "rp": float(rp_val) if rp_val is not None else None,
                "ap": float(ap_val) if ap_val is not None else None,
                "ep": float(ep_val) if ep_val is not None else None,
                "sp": int(r.get("sp") or 0),
                "high_score": int(r.get("highScore") or r.get("high_score") or 0),
                "total_points": int(r.get("totalPoints") or r.get("total_points") or 0),
                "played": wins + losses + ties if has_official_wlt else 0,
                "dq_count": 0,
                "is_official": True,
                "wlt_is_official": has_official_wlt,
            }

    for seq_idx, m in enumerate(raw_matches, start=1):
        mid = (m.get("match") or f"M{seq_idx}").strip()
        sched_str = fmt_local_time(m.get("scheduledAt"))
        started_str = fmt_local_time(m.get("startedAt"))
        red_teams = [(t or "TBD").strip().upper() for t in (m.get("redTeams") or [])]
        blue_teams = [(t or "TBD").strip().upper() for t in (m.get("blueTeams") or [])]
        while len(red_teams) < 2:
            red_teams.append("TBD")
        while len(blue_teams) < 2:
            blue_teams.append("TBD")

        live_matches.append({
            "id": mid,
            "num": seq_idx,
            "time": sched_str or "TBD",
            "started": started_str,
            "field": (m.get("field") or "TBD").strip(),
            "red1": red_teams[0],
            "red2": red_teams[1],
            "blue1": blue_teams[0],
            "blue2": blue_teams[1],
        })

        r_score, b_score, has_score = parse_match_score(m.get("allianceScores") or m.get("score"))
        status_low = (m.get("status") or "").lower()
        is_done = has_score or status_low in ("scored", "completed", "finished")
        if is_done or started_str or status_low in ("in progress", "live", "active"):
            latest_started_num = max(latest_started_num, seq_idx)
            scores_dict[mid] = {
                "red": r_score,
                "blue": b_score,
                "scheduled": sched_str,
                "started": started_str,
                "done": is_done,
            }

        # Aggregate Qual stats (Q*) ONLY when C2 rankings do not include official W/L/T yet,
        # honoring any persistent per-team DQ overrides in Firebase RTDB (/dq_overrides).
        if is_done and mid.upper().startswith("Q") and not has_official_wlt:
            lose_score = min(r_score, b_score)
            dq_set = dq_overrides.get(mid.upper(), set())
            for side, teams_list, my_score, opp_score in (
                ("red", red_teams, r_score, b_score),
                ("blue", blue_teams, b_score, r_score),
            ):
                for t_name in teams_list:
                    if t_name == "TBD":
                        continue
                    st = team_stats.setdefault(t_name, {
                        "team": {"name": t_name}, "rank": 999, "wins": 0, "losses": 0, "ties": 0,
                        "wp": 0, "rp": None, "ap": None, "ep": None, "sp": 0, "high_score": 0,
                        "total_points": 0, "played": 0, "dq_count": 0, "is_official": True,
                        "wlt_is_official": False,
                    })
                    st["played"] += 1
                    if t_name in dq_set:
                        # Per RECF Achieve rules: single-team DQ gives ONLY that team a loss and 0 RP/AP/EP;
                        # their alliance partner still keeps the alliance match result!
                        st["losses"] += 1
                        st["dq_count"] += 1
                        continue
                    st["sp"] += lose_score
                    st["total_points"] += my_score
                    st["high_score"] = max(st["high_score"], my_score)
                    if my_score > opp_score:
                        st["wins"] += 1; st["wp"] += 2
                    elif my_score < opp_score:
                        st["losses"] += 1
                    else:
                        st["ties"] += 1; st["wp"] += 1

    # 3. Rankings sorted ascending #1 -> #N (official C2 rank order; leave rp/ap/ep as None if C2 omits them)
    rankings = sorted(team_stats.values(), key=lambda x: (x.get("rank", 999), -x.get("wp", 0)))

    # 4. Push to Firebase RTDB (individual keys so /scouting is NEVER overwritten)
    metadata = {
        "id": event_id,
        "sku": sku,
        "name": ev_name,
        "source": "recfevents+redshirtsynergy",
        "scoring_system": "recf",
        "url": recf_url,
        "schedule_url": f"https://redshirtsynergy.com/events/{rss_uuid}#schedule",
        "livestream_url": (guide.get("livestream") or {}).get("url", ""),
        "start": ev_info.get("date") or "2026-11-23",
        "end": ev_info.get("endDate") or "2026-11-24",
        "location": {
            "venue": ev_info.get("venue") or "CCISD Learner Support Center",
            "address": "2903 Falcon Pass Drive",
            "city": "Houston",
            "region": "Texas",
            "postcode": "77062",
        },
    }

    rtdb_put(f"events/{event_id}/metadata", metadata)
    rtdb_put(f"events/{event_id}/matches", live_matches)
    rtdb_put(f"events/{event_id}/scores", scores_dict)
    rtdb_put(f"events/{event_id}/rankings", rankings)
    rtdb_put(f"events/{event_id}/official_rankings", rankings)
    rtdb_put(f"events/{event_id}/rankings_official", True)
    rtdb_put(f"events/{event_id}/wlt_official", has_official_wlt)
    rtdb_put(f"events/{event_id}/live_skills", live_skills)
    rtdb_put(f"events/{event_id}/team_profiles", team_profiles)
    rtdb_put(f"events/{event_id}/onFieldMatchNum", latest_started_num)
    rtdb_put(f"events/{event_id}/last_sync", now_str)

    dq_total = sum(len(s) for s in dq_overrides.values())
    print(
        f"[{now_str}] [RECF {event_id}] Synced {len(live_matches)} matches, "
        f"{len(scores_dict)} scored, {len(rankings)} rankings "
        f"(wlt_official={has_official_wlt}, dq_overrides={dq_total}) & {len(live_skills)} solo skills to Firebase!",
        flush=True,
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=int, default=DEFAULT_RECF_EVENT_ID)
    parser.add_argument("--rss-uuid", type=str, default=DEFAULT_RSS_EVENT_UUID)
    parser.add_argument("--refresh-teams", action="store_true")
    parser.add_argument("--loop", type=int, default=0, help="Poll interval in seconds (0 = run once)")
    parser.add_argument("--duration", type=int, default=0, help="Max total run duration in seconds when looping (0 = unlimited)")
    parser.add_argument("--force", action="store_true", help="Run even outside game-day hours")
    parser.add_argument("--dq", action="append", default=[], help="Flag a team DQ as MATCH:TEAM (e.g. Q49:33111C)")
    parser.add_argument("--undq", action="append", default=[], help="Clear a team DQ as MATCH:TEAM (e.g. Q49:33111C)")
    args = parser.parse_args()

    for spec in args.dq:
        if ":" in spec:
            mid_s, team_s = [p.strip().upper() for p in spec.split(":", 1)]
            if mid_s and team_s:
                rtdb_put(f"events/{args.event}/dq_overrides/{mid_s}/{team_s}", True)
                print(f"[DQ] Flagged {team_s} in {mid_s}", flush=True)
    for spec in args.undq:
        if ":" in spec:
            mid_s, team_s = [p.strip().upper() for p in spec.split(":", 1)]
            if mid_s and team_s:
                rtdb_put(f"events/{args.event}/dq_overrides/{mid_s}/{team_s}", None)
                print(f"[DQ] Cleared {team_s} in {mid_s}", flush=True)

    def is_game_day_hours():
        now = datetime.datetime.now()
        if now.date() not in (datetime.date(2026, 11, 23), datetime.date(2026, 11, 24)):
            return False
        hm = (now.hour, now.minute)
        return (7, 30) <= hm <= (19, 30)

    if args.loop > 0:
        start_ts = time.time()
        while True:
            if not args.force and not is_game_day_hours():
                print(f"[{datetime.datetime.now().strftime('%I:%M:%S %p')}] Outside Space City Achieve hours. Stopping sync.", flush=True)
                break
            try:
                sync_recf_live(args.event, args.rss_uuid, refresh_recf_teams=False)
            except Exception as e:
                print(f"[WARN] RECF live sync error: {e}", flush=True)
            if args.duration > 0 and (time.time() - start_ts + args.loop) >= args.duration:
                break
            time.sleep(args.loop)
    else:
        sync_recf_live(args.event, args.rss_uuid, refresh_recf_teams=args.refresh_teams)
