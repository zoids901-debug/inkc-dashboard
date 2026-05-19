# -*- coding: utf-8 -*-
"""어제 매출/영수 데이터 vs 베이스라인 → Z-score 이상 감지.
출력: ops_data/health.json (대시보드에서 fetch).
실행 환경: GitHub Actions (동기화 잡 끝난 직후) — repo 체크아웃 상태.
"""
import json, os, statistics
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
OPS_DIR = REPO_ROOT / "ops_data"
BASELINE_PATH = OPS_DIR / "baseline.json"
HEALTH_PATH = OPS_DIR / "health.json"

DOW_NAMES = ["월", "화", "수", "목", "금", "토", "일"]
Z_WARN = 2.0   # |Z| ≥ 2 → 의심
Z_BAD  = 3.0   # |Z| ≥ 3 → 강한 이상


def load_baseline():
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def load_yesterday(d):
    """ops_data/{YYYY-MM}.json에서 d일자 매장별 record 추출."""
    fname = OPS_DIR / f"{d.year}-{d.month:02d}.json"
    if not fname.exists():
        return {}
    data = json.loads(fname.read_text(encoding="utf-8"))
    iso = d.isoformat()
    result = {}
    for store, records in data.items():
        if not isinstance(records, list):
            continue
        for r in records:
            if r.get("date") == iso:
                result[store] = {
                    "sales": r.get("sales"),
                    "receipts": r.get("receipts"),
                }
                break
    return result


def z_score(actual, mean, std):
    if std is None or std <= 0:
        return None
    return (actual - mean) / std


def assess_store(store, day_data, baseline_block, dow):
    sales = day_data.get("sales")
    receipts = day_data.get("receipts")
    by_dow = baseline_block.get("by_dow", {}).get(str(dow))
    overall = baseline_block.get("overall", {})

    result = {
        "store": store,
        "status": "ok",  # ok / warn / bad / missing
        "messages": [],
        "z": {},
    }

    # 데이터 누락
    if sales is None or sales <= 0:
        result["status"] = "missing"
        result["messages"].append("매출 데이터 없음")
        return result

    # 매출 Z-score
    ref = by_dow if by_dow else overall
    if ref and ref.get("sales_mean"):
        z = z_score(sales, ref["sales_mean"], ref["sales_std"])
        if z is not None:
            result["z"]["sales"] = round(z, 2)
            actual_pct = (sales / ref["sales_mean"] - 1) * 100 if ref["sales_mean"] else 0
            dow_lbl = f"{DOW_NAMES[dow]}요일" if by_dow else "평균"
            base_label = f"평소 {dow_lbl} {int(ref['sales_mean']):,}원 ±{int(ref['sales_std']):,}"
            if abs(z) >= Z_BAD:
                result["status"] = "bad"
                result["messages"].append(f"매출 {sales:,}원 ({actual_pct:+.0f}%) — Z={z:+.1f} 강한 이상 ({base_label})")
            elif abs(z) >= Z_WARN:
                if result["status"] == "ok":
                    result["status"] = "warn"
                result["messages"].append(f"매출 {sales:,}원 ({actual_pct:+.0f}%) — Z={z:+.1f} 의심 ({base_label})")

    # 영수건수 Z-score (보조)
    if receipts is not None and receipts > 0 and ref and ref.get("receipts_mean"):
        zr = z_score(receipts, ref["receipts_mean"], ref["receipts_std"])
        if zr is not None:
            result["z"]["receipts"] = round(zr, 2)
            if abs(zr) >= Z_BAD:
                result["status"] = "bad" if result["status"] != "bad" else "bad"
                result["messages"].append(f"영수건수 {receipts:,}건 — Z={zr:+.1f} 강한 이상")
            elif abs(zr) >= Z_WARN:
                if result["status"] == "ok":
                    result["status"] = "warn"
                result["messages"].append(f"영수건수 {receipts:,}건 — Z={zr:+.1f} 의심")

    return result


def main():
    baseline = load_baseline()
    if not baseline:
        print("baseline.json 없음 — 학습 먼저")
        return

    # 어제 데이터 검사 (KST 기준)
    target = date.today() - timedelta(days=1)
    print(f"검사 대상: {target}")

    day = load_yesterday(target)
    stores_baseline = baseline.get("stores", {})
    dow = target.weekday()

    results = []
    for store in sorted(set(list(day.keys()) + list(stores_baseline.keys()))):
        bb = stores_baseline.get(store, {})
        dd = day.get(store, {})
        if not dd:
            results.append({
                "store": store, "status": "missing",
                "messages": ["매출 데이터 없음 (동기화 누락 가능)"],
                "z": {},
            })
            continue
        if not bb:
            # 베이스라인 없음 (신규 매장 등)
            results.append({
                "store": store, "status": "ok",
                "messages": ["베이스라인 학습 데이터 부족 — 검증 보류"],
                "z": {}, "sales": dd.get("sales"),
            })
            continue
        r = assess_store(store, dd, bb, dow)
        r["sales"] = dd.get("sales")
        r["receipts"] = dd.get("receipts")
        results.append(r)

    # 요약
    status_counts = {"ok": 0, "warn": 0, "bad": 0, "missing": 0}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    overall_status = "ok"
    if status_counts.get("bad", 0) or status_counts.get("missing", 0):
        overall_status = "bad"
    elif status_counts.get("warn", 0):
        overall_status = "warn"

    health = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target.isoformat(),
        "dow": DOW_NAMES[dow],
        "overall": overall_status,
        "summary": status_counts,
        "stores": results,
    }

    HEALTH_PATH.write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 검사 결과 ({target} {DOW_NAMES[dow]}요일) ===")
    print(f"전체: {overall_status.upper()}  |  ok:{status_counts['ok']}  warn:{status_counts['warn']}  bad:{status_counts['bad']}  missing:{status_counts['missing']}")
    for r in results:
        icon = {"ok":"✓", "warn":"⚠", "bad":"✗", "missing":"✗"}[r["status"]]
        print(f"  {icon} {r['store']}: {' / '.join(r['messages']) if r['messages'] else '정상'}")
    print(f"\n→ 저장: {HEALTH_PATH}")


if __name__ == "__main__":
    main()
