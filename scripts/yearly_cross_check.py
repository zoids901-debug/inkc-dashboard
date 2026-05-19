# -*- coding: utf-8 -*-
"""연간 합산 교차 검증 — OK포스 raw (raw_okpos/) vs 운영 대시보드 (ops_data/).

매장 × 연도별로 합산해서 비교 → 1년 단위 큰 차이로 누락/오류 추적.

출력: ops_data/yearly_cross_check.json
"""
import json, os
from datetime import date
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
OPS_DIR = REPO_ROOT / "ops_data"
RAW_DIR = OPS_DIR / "raw_okpos"
OUT_PATH = OPS_DIR / "yearly_cross_check.json"

STORES = ['가산', '다산', '수원', '하남', '광주', '운정']
EXPECTED_DIFF_STORES = {"수원", "운정"}

PCT_WARN = 1.0
PCT_BAD  = 5.0


def list_month_files(d):
    return sorted([f for f in os.listdir(d)
                   if f.endswith(".json") and f[0].isdigit() and len(f) == 12])


def sum_records(records, today_iso):
    if not records: return 0
    return sum((r.get("sales") or 0) for r in records
               if r.get("date", "") < today_iso)


def main():
    today = date.today()
    today_iso = today.isoformat()

    # ops_data 매장×연도별 합
    ops_yearly = defaultdict(lambda: defaultdict(int))
    for fname in list_month_files(OPS_DIR):
        year = fname[:4]
        data = json.loads((OPS_DIR / fname).read_text(encoding="utf-8"))
        for store, records in data.items():
            if not isinstance(records, list): continue
            ops_yearly[year][store] += sum_records(records, today_iso)

    # raw_okpos 매장×연도별 합
    raw_yearly = defaultdict(lambda: defaultdict(int))
    if RAW_DIR.exists():
        for fname in list_month_files(RAW_DIR):
            year = fname[:4]
            try:
                data = json.loads((RAW_DIR / fname).read_text(encoding="utf-8"))
                for store, records in data.items():
                    if not isinstance(records, list): continue
                    raw_yearly[year][store] += sum_records(records, today_iso)
            except Exception as e:
                print(f'  raw {fname} 로드 실패: {e}')

    # 결과 정리
    results = []
    all_years = sorted(set(list(ops_yearly.keys()) + list(raw_yearly.keys())))
    for year in all_years:
        for store in STORES:
            ops_v = ops_yearly[year].get(store, 0)
            raw_v = raw_yearly[year].get(store, 0)
            if ops_v == 0 and raw_v == 0: continue
            diff = ops_v - raw_v
            base = max(ops_v, raw_v) or 1
            pct = abs(diff) / base * 100

            if raw_v == 0 and ops_v > 0:
                level = "no_raw"
                msg = "OK포스 raw 없음 (backfill 안 됨 또는 매장 오픈 전)"
            elif store in EXPECTED_DIFF_STORES:
                level = "info"
                msg = "시트/TOSS fallback 매장 — 차이는 정상"
            elif abs(diff) < 100_000:
                level = "ok"
                msg = "raw와 대시보드 합계 일치"
            elif pct >= PCT_BAD:
                level = "bad"
                msg = "큰 차이 — 동기화 누락 또는 보정 오류 의심"
            elif pct >= PCT_WARN:
                level = "warn"
                msg = "1% 이상 차이 — 부분 누락 가능"
            else:
                level = "ok"
                msg = "미세한 차이"

            results.append({
                "year": year, "store": store,
                "raw_total": raw_v, "ops_total": ops_v,
                "diff": diff, "pct": round(pct, 2),
                "level": level, "message": msg,
            })

    out = {
        "checked_at": today.isoformat(),
        "results": results,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 콘솔 표 출력
    print(f"\n=== 매장 × 연도 합계 비교 ===")
    print(f"{'연도':<6}{'매장':<6}{'OK포스 raw':>16}{'운영 대시보드':>16}{'차이':>16}{'%':>7}  판정")
    for r in results:
        icon = {"ok":"✓","warn":"⚠","bad":"✗","info":"ⓘ","no_raw":"?"}[r["level"]]
        print(f"{r['year']:<6}{r['store']:<6}{r['raw_total']:>16,}{r['ops_total']:>16,}{r['diff']:>+16,}{r['pct']:>6.2f}%  {icon} {r['message']}")
    print(f"\n→ 저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
