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

    # Stats computed from scored Qualification matches (Q*)
    team_stats = {}
    for r in comp.get("rankings") or []:
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
            team_stats[tnum] = {
                "team": {"name": tnum},
                "rank": r.get("rank", 999),
                "wins": int(r.get("wins") or 0),
                "losses": int(r.get("losses") or 0),
                "ties": int(r.get("ties") or 0),
                "wp": int(r.get("wp") or 0),
                "ap": int(r.get("ap") or 0),
                "sp": int(r.get("sp") or 0),
                "high_score": int(r.get("highScore") or r.get("high_score") or 0),
                "total_points": int(r.get("totalPoints") or r.get("total_points") or 0),
                "played": 0,
                "is_official": True,
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

        # Aggregate Qual stats (Q*) if C2 rankings don't include W/L/T yet
        if is_done and mid.upper().startswith("Q"):
            lose_score = min(r_score, b_score)
            for t_name in red_teams:
                if t_name == "TBD":
                    continue
                st = team_stats.setdefault(t_name, {
                    "team": {"name": t_name}, "rank": 999, "wins": 0, "losses": 0, "ties": 0,
                    "wp": 0, "ap": 0, "sp": 0, "high_score": 0, "total_points": 0, "played": 0, "is_official": True
                })
                st["played"] += 1
                st["sp"] += lose_score
                st["total_points"] += r_score
                st["high_score"] = max(st["high_score"], r_score)
                if r_score > b_score:
                    st["wins"] += 1; st["wp"] += 2
                elif r_score < b_score:
                    st["losses"] += 1
                else:
                    st["ties"] += 1; st["wp"] += 1

            for t_name in blue_teams:
                if t_name == "TBD":
                    continue
                st = team_stats.setdefault(t_name, {
                    "team": {"name": t_name}, "rank": 999, "wins": 0, "losses": 0, "ties": 0,
                    "wp": 0, "ap": 0, "sp": 0, "high_score": 0, "total_points": 0, "played": 0, "is_official": True
                })
                st["played"] += 1
                st["sp"] += lose_score
                st["total_points"] += b_score
                st["high_score"] = max(st["high_score"], b_score)
                if b_score > r_score:
                    st["wins"] += 1; st["wp"] += 2
                elif b_score < r_score:
                    st["losses"] += 1
                else:
                    st["ties"] += 1; st["wp"] += 1

    # 3. Rankings sorted ascending #1 -> #N
    rankings = sorted(team_stats.values(), key=lambda x: (x.get("rank", 999), -x.get("wp", 0)))

    # 4. Push to Firebase RTDB (individual keys so /scouting is NEVER overwritten)
    metadata = {
        "id": event_id,
        "sku": sku,
        "name": ev_name,
        "source": "recfevents+redshirtsynergy",
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
    rtdb_put(f"events/{event_id}/live_skills", live_skills)
    rtdb_put(f"events/{event_id}/team_profiles", team_profiles)
    rtdb_put(f"events/{event_id}/onFieldMatchNum", latest_started_num)
    rtdb_put(f"events/{event_id}/last_sync", now_str)

    print(
        f"[{now_str}] [RECF {event_id}] Synced {len(live_matches)} matches, "
        f"{len(scores_dict)} scored, {len(rankings)} rankings & {len(live_skills)} solo skills to Firebase!",
        flush=True,
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=int, default=DEFAULT_RECF_EVENT_ID)
    parser.add_argument("--rss-uuid", type=str, default=DEFAULT_RSS_EVENT_UUID)
    parser.add_argument("--refresh-teams", action="store_true")
    parser.add_argument("--loop", type=int, default=0, help="Poll interval in seconds (0 = run once)")
    parser.add_argument("--force", action="store_true", help="Run even outside game-day hours")
    args = parser.parse_args()

    def is_game_day_hours():
        now = datetime.datetime.now()
        if now.date() not in (datetime.date(2026, 11, 23), datetime.date(2026, 11, 24)):
            return False
        hm = (now.hour, now.minute)
        return (7, 30) <= hm <= (18, 45)

    if args.loop > 0:
        while True:
            if not args.force and not is_game_day_hours():
                print(f"[{datetime.datetime.now().strftime('%I:%M:%S %p')}] Outside Space City Achieve hours. Stopping sync.", flush=True)
                break
            try:
                sync_recf_live(args.event, args.rss_uuid, refresh_recf_teams=False)
            except Exception as e:
                print(f"[WARN] RECF live sync error: {e}", flush=True)
            time.sleep(args.loop)
    else:
        sync_recf_live(args.event, args.rss_uuid, refresh_recf_teams=args.refresh_teams)
