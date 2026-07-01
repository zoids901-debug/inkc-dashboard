# -*- coding: utf-8 -*-
"""OK포스 raw vs 운영 대시보드 최종값(ops_data) 교차 검증.

비교 대상:
- A: ops_data/raw_okpos/{YYYY-MM}.json  — OK포스에서 받은 보정 전 원본
- B: ops_data/{YYYY-MM}.json            — 보정·시트 patch 후 최종 저장값 (대시보드 표시)

매장별 월 합산 + 일별 차이로 동기화 누락/오류 검출.
"""
import json, os
from datetime import date
from pathlib import Path

REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
OPS_DIR = REPO_ROOT / "ops_data"
RAW_DIR = OPS_DIR / "raw_okpos"
OUT_PATH = OPS_DIR / "cross_check.json"

# 차이 임계값 (월 합산 기준)
PCT_WARN = 1.0   # ≥ 1% → 의심
PCT_BAD  = 5.0   # ≥ 5% → 강한 이상
ABS_MIN  = 50_000  # 절대 차이 5만원 미만은 noise 무시

# raw와 직접 비교 가능한 매장 — 전 매장 정상 검증
# (수원: raw_okpos와 100% 일치 확인됨 / 운정: 토스 raw도 raw_okpos에 저장되어 비교 가능)
EXPECTED_DIFF_STORES = set()

# 큐브포스(CubePOS) 전환 매장 — 2026-07-01부터 OK포스 raw엔 데이터가 없고(피드 끊김)
# 대시보드(ops)는 큐브포스로 채워지므로 raw 대비 차이가 정상. 큐브포스 raw 교차검증이
# 붙기 전까지 info 로 처리해 오경보를 막는다. 연동 후 큐브포스 raw로 비교 전환 예정.
MIGRATING_STORES = {"하남", "가산", "다산"}


def load_month(path):
    if not path.exists(): return None
    return json.loads(path.read_text(encoding="utf-8"))


def sum_records(records):
    if not records: return 0
    return sum((r.get("sales") or 0) for r in records)


def main():
    today = date.today()
    yyyy_mm = today.strftime("%Y-%m")
    today_iso = today.isoformat()
    print(f"=== 교차 검증: {yyyy_mm} ===")

    raw = load_month(RAW_DIR / f"{yyyy_mm}.json")
    ops = load_month(OPS_DIR / f"{yyyy_mm}.json")

    if not raw:
        out = {
            "checked_at": today.isoformat(),
            "yyyy_mm": yyyy_mm,
            "status": "no_raw",
            "message": f"raw_okpos/{yyyy_mm}.json 없음 — 다음 동기화 후 가능",
            "stores": [],
        }
        OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print("raw_okpos 없음 — 다음 동기화 후 가능")
        return

    if not ops:
        print("ops_data 없음")
        return

    results = []
    for store in sorted(set(list(raw.keys()) + list(ops.keys()))):
        raw_records = raw.get(store, [])
        ops_records = ops.get(store, [])

        # 미래 날짜 제외
        raw_filt = [r for r in raw_records if r.get("date", "") < today_iso]
        ops_filt = [r for r in ops_records if r.get("date", "") < today_iso]

        raw_total = sum_records(raw_filt)
        ops_total = sum_records(ops_filt)

        diff = ops_total - raw_total
        base = ops_total if ops_total > 0 else raw_total
        pct = abs(diff) / base * 100 if base else 0

        # 의도된 fallback 매장은 차이가 정상 — info 처리
        if store in EXPECTED_DIFF_STORES:
            level = "info"
            message = f"시트/TOSS fallback 매장 — raw와 차이는 정상"
        elif store in MIGRATING_STORES:
            level = "info"
            message = f"큐브포스 전환 매장 — OK포스 raw와 차이는 정상(연동 대기)"
        elif abs(diff) < ABS_MIN:
            level = "ok"
            message = f"OK포스 raw와 운영 대시보드 일치"
        elif pct >= PCT_BAD:
            level = "bad"
            message = f"강한 이상 — 동기화 누락 또는 보정 오류 의심"
        elif pct >= PCT_WARN:
            level = "warn"
            message = f"의심 — 동기화 부분 누락 가능"
        else:
            level = "ok"
            message = f"미세한 차이 (영수 보정 등)"

        # 일별 차이 (info 매장은 건너뜀 — fallback 차이가 정상)
        daily_diffs = []
        if level not in ("info", "ok"):
            raw_by_date = {r["date"]: r for r in raw_filt}
            ops_by_date = {r["date"]: r for r in ops_filt}
            for dt in sorted(set(list(raw_by_date.keys()) + list(ops_by_date.keys()))):
                rs = (raw_by_date.get(dt, {}).get("sales") or 0)
                os_ = (ops_by_date.get(dt, {}).get("sales") or 0)
                d = os_ - rs
                if abs(d) < ABS_MIN: continue
                bs = max(rs, os_) or 1
                p = abs(d) / bs * 100
                if p >= PCT_WARN:
                    daily_diffs.append({
                        "date": dt, "raw": rs, "ops": os_, "diff": d, "pct": round(p, 1),
                    })

        results.append({
            "store": store,
            "level": level,
            "raw_total": raw_total,
            "ops_total": ops_total,
            "diff": diff,
            "pct": round(pct, 1),
            "message": message,
            "daily_diffs": daily_diffs[:5],
            "daily_diffs_count": len(daily_diffs),
        })

    # 전체 상태
    has_bad = any(r["level"] == "bad" for r in results)
    has_warn = any(r["level"] == "warn" for r in results)
    overall = "bad" if has_bad else ("warn" if has_warn else "ok")

    out = {
        "checked_at": today.isoformat(),
        "yyyy_mm": yyyy_mm,
        "overall": overall,
        "stores": results,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== 결과 (전체: {overall.upper()}) ===")
    for r in results:
        icon = {"ok":"✓", "warn":"⚠", "bad":"✗", "info":"ⓘ"}[r["level"]]
        print(f"  {icon} {r['store']}: raw {r['raw_total']:,}원 vs 대시보드 {r['ops_total']:,}원 ({r['diff']:+,}, {r['pct']:.1f}%) — {r['message']}")
        if r["daily_diffs"]:
            for dd in r["daily_diffs"]:
                print(f"      └ {dd['date']}: raw {dd['raw']:,} vs 대시보드 {dd['ops']:,} ({dd['diff']:+,}, {dd['pct']:.1f}%)")
    print(f"\n→ 저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
