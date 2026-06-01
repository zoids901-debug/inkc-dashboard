# -*- coding: utf-8 -*-
"""과거 월 ops_data JSON의 근무인원(staff)을 스케줄 탭 기준으로 백필.

ops_actions_sync.py는 현재월만 패치하므로, 지난달 근무인원을 스케줄 기준으로
다시 채우고 생산성(매출÷근무인원)을 재계산한다. 매출/영수 등 다른 필드는 건드리지 않음.
스케줄에 해당일 데이터가 없으면 기존 staff 값을 유지(폴백).

사용:  py backfill_staff.py 2026-05 [2026-04 ...]
인자 없으면 최근 완료월(현재월 직전)만.
"""
import os
import sys
import json
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from schedule_parser import fetch_schedule, STORE_SHEETS  # noqa: E402


def backfill_month(yyyy_mm):
    path = os.path.join(REPO, "ops_data", f"{yyyy_mm}.json")
    if not os.path.exists(path):
        print(f"  {yyyy_mm}: 파일 없음 — skip")
        return
    y, m = (int(x) for x in yyyy_mm.split("-"))
    data = json.load(open(path, encoding="utf-8"))
    changed = 0
    for store in data:
        if store not in STORE_SHEETS:
            continue
        try:
            sched = fetch_schedule(store, y, m)
        except Exception as e:
            print(f"  [{store}] 스케줄 실패(기존 유지): {e}")
            sched = {}
        sched_staff = {d: v["count"] for d, v in sched.items() if v.get("count")}
        n = 0
        for entry in data[store]:
            day = int(entry["date"].split("-")[2])
            if day in sched_staff and entry.get("staff") != sched_staff[day]:
                entry["staff"] = sched_staff[day]
                n += 1
            # 생산성 재계산 (매출·근무인원 둘 다 있을 때만)
            if entry.get("sales") and entry.get("staff"):
                entry["productivity"] = entry["sales"] // entry["staff"]
            elif not entry.get("staff"):
                entry["productivity"] = None
        if sched_staff:
            rng = f"{min(sched_staff.values())}~{max(sched_staff.values())}명"
            print(f"  [{store}] 스케줄 {len(sched_staff)}일 {rng} → {n}일 갱신")
        else:
            print(f"  [{store}] 스케줄 없음 — 기존 staff 유지")
        changed += n
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{yyyy_mm}: 총 {changed}일 갱신, 저장 완료")


if __name__ == "__main__":
    months = sys.argv[1:]
    if not months:
        t = date.today()
        py, pm = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
        months = [f"{py}-{pm:02d}"]
    for mm in months:
        print(f"=== {mm} 백필 ===")
        backfill_month(mm)
