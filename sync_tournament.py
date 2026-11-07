#!/usr/bin/env python3
"""
33111C VEX Tournament Live API Sync Worker
Runs locally or as a scheduled background cron/action.
Pulls live matches, scores, and rankings from events.vex.com API and pushes to Firebase RTDB.
Token is kept secure in this environment and NEVER exposed to client browsers.
"""
import sys, json, os, urllib.request, datetime

TOKEN = os.environ.get("ROBOTEVENTS_TOKEN", "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIzIiwianRpIjoiMWQxMGNhYTlhMmM4MjJlZTNiZDEwOTBkY2MxZGEzZjdkMGZhYzY0M2FmMGY1ZGU4Yjc3NGI2MmJhZGY4ZDIwYWI5YmRmYjhhNGQ3MDYzOGIiLCJpYXQiOjE3OTQwMjU3MzUuNDYyOTE0LCJuYmYiOjE3OTQwMjU3MzUuNDYyOTE1OSwiZXhwIjoyNzQwNzk2OTM1LjQ1NDIyMDgsInN1YiI6IjExNzUzNiIsInNjb3BlcyI6W119.hQUdbDOLoaFuFgAL9T8j3au8CN3gvgX0LUzzbxc5TUG_Io65D0t8eppEzd4jttgBrywX2203lRU81ubYuIUc0C63oqSboFXteuR-Br2npqjqGRt1JaLYdNvbA1u3m8c9a959BU8KkH5cQA2-TPX0trgZ1mH37mstSvzmiAlHHgWYNw4rcU7nX0q6nwp66F5V3cHBUZ6otF-K4mWSsMTwi7Yt-5_iNkLEHxEURbjrJ4Lo7DgL_yUSyK_whMd9IYX_mLiDcah3_dTy3JDYoFakhsIQzboWdbx67eMWnGPKowPlkjZFN4fC_yYFNID6UgOfTmmeMcIvW52v3zCKGTWtFCYBLtnT9juxjytbU95et8sfVh8HYyisKQBLB7offvggIrYnXLhw0t6iyvWE9Lua3Gib2pJkBQ1Rq6W36nql861yNRtnJd4oCLuR_S-0XRYZnXtG1QciYmcXYvvd9hQ_x02SAkUjQL7Ww1-TGPv5eKNK0p4b5vsQ6rxzAhZAI_zeXncr3UAxahT5aDU1BsVTZ81e6J0UcIYoMN6qvggpzF_pUVccgOd9jtzlQ3HVg1s76SloYzVH1PP1k3olETVUMBTIcklYx7c07vEXBmdkrqg8fdFo5BnDuiSJFMzdINWA2MROvc1S6wWElUgnPdq3ZlPc1-GvYkinZZ68k4Egy50")
RTDB_URL = "https://my-project-1524591195518-default-rtdb.firebaseio.com/vex_33111c"
EVENT_ID = 65031 # Texan Standoff Nov 7, 2026

def api_get(endpoint):
    url = f"https://events.vex.com/api/v2{endpoint}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": "VexScout-Sync/1.0"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def sync():
    now_str = datetime.datetime.now().strftime("%I:%M:%S %p")
    print(f"[{now_str}] Syncing from RobotEvents API for Event {EVENT_ID}...")
    
    # 1. Fetch matches
    matches = []
    for p in [1, 2]:
        data = api_get(f"/events/{EVENT_ID}/divisions/1/matches?page={p}")
        matches.extend(data.get("data", []))
    
    # 2. Fetch rankings
    rank_data = api_get(f"/events/{EVENT_ID}/divisions/1/rankings")
    rankings = rank_data.get("data", [])
    
    # 3. Detect current on-field match & delay from API timestamps
    latest_started_num = 1
    detected_delay = 0
    scores_dict = {}
    
    for m in sorted(matches, key=lambda x: x.get("matchnum", 0)):
        num = m.get("matchnum")
        started = m.get("started")
        sched = m.get("scheduled")
        alliances = {a["color"]: a.get("score", 0) for a in m.get("alliances", [])}
        r_score = alliances.get("red", 0)
        b_score = alliances.get("blue", 0)
        
        if started or r_score > 0 or b_score > 0:
            latest_started_num = max(latest_started_num, num)
            scores_dict[f"Q{num}"] = {
                "red": r_score,
                "blue": b_score,
                "done": True
            }
            if started and sched:
                try:
                    t_started = datetime.datetime.fromisoformat(started)
                    t_sched = datetime.datetime.fromisoformat(sched)
                    diff_mins = int((t_started - t_sched).total_seconds() / 60)
                    detected_delay = diff_mins
                except Exception:
                    pass

    # Push to Firebase RTDB
    payload = {
        "last_sync": now_str,
        "event_id": EVENT_ID,
        "onFieldMatchNum": latest_started_num,
        "detectedDelay": detected_delay,
        "scores": scores_dict,
        "rankings": rankings
    }
    
    data_bytes = json.dumps(payload).encode("utf-8")
    put_req = urllib.request.Request(f"{RTDB_URL}/live_event.json", data=data_bytes, method="PUT", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(put_req) as r:
        print(f"Synced {len(scores_dict)} scored matches & {len(rankings)} rankings to Firebase! Status: {r.status}")

if __name__ == "__main__":
    sync()
