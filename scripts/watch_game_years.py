#!/usr/bin/env python3
"""Watch the locally-pulled Cicero game JSON and emit one line per completed
year (and at game end), so an agent monitor can summarize each year.

A year Y is "complete" once the next spring phase S(Y+1)M appears in the game
(its builds are resolved), or, for the final year, once the final game file is
written. Emits `YEAR_COMPLETE <Y>` and finally `GAME_COMPLETE`.
"""
import json
import os
import time

PARTIAL = "modal_cicero_game_TURKEY.partial.json"
FINAL = "modal_cicero_game_TURKEY.json"
reported = set()
game_done = False

while not game_done:
    src = FINAL if os.path.exists(FINAL) else (PARTIAL if os.path.exists(PARTIAL) else None)
    if src:
        try:
            d = json.load(open(src))
            phases = [p.get("name", "") for p in d.get("phases", [])]
            years = sorted({n[1:5] for n in phases if len(n) >= 5 and n[1:5].isdigit()})
            complete = set()
            for y in years:
                if f"S{int(y) + 1:04d}M" in phases:
                    complete.add(y)
            if src == FINAL and years:
                complete.add(max(years))  # game ended -> last year is done
            for y in sorted(complete):
                if y not in reported:
                    reported.add(y)
                    print(f"YEAR_COMPLETE {y}", flush=True)
            if src == FINAL and years and max(years) in reported:
                print("GAME_COMPLETE", flush=True)
                game_done = True
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
    time.sleep(30)
