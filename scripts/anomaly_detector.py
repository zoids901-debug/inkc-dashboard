# -*- coding: utf-8 -*-
"""어제 매출/영수 데이터 vs 베이스라인 → 이상 감지.
- 한글 메시지로 보고 (Z-score는 내부에서만 사용)
- 수원점: 1일 딜레이 → 이틀 전 데이터 검사
- 그 외 매장: 어제 데이터 검사
- 새벽 5시 KST 정기 실행 가정

출력: ops_data/health.json (대시보드 + 메일 알림에서 사용)
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

# 데이터 딜레이 매장 (target = today - 2)
DELAYED_STORES = {"수원": 2}  # store name → days delay


def load_baseline():
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def load_for_date(d):
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


def pct_diff(actual, mean):
    if not mean:
        return 0
    return (actual / mean - 1) * 100


def korean_msg(sales, mean, std, z, dow_name, kind="매출"):
    """Z-score 대신 한글로 표현."""
    if z is None:
        return f"{kind} {sales:,}원 (베이스라인 표준편차 부족)"
    pct = pct_diff(sales, mean)
    sign = "높음" if pct >= 0 else "낮음"
    pct_abs = abs(pct)
    if abs(z) >= Z_BAD:
        level = "강한 이상"
    elif abs(z) >= Z_WARN:
        level = "의심"
    else:
        level = "정상 범위"
    if abs(z) < Z_WARN:
        return (f"{kind} {sales:,}원 — 평소 {dow_name}요일 평균({int(mean):,}원)과 비슷 ({level})")
    return (f"{kind} {sales:,}원 — 평소 {dow_name}요일보다 {pct_abs:.0f}% {sign} ({level})")


def assess_store(store, day_data, baseline_block, dow, target_date_used, delayed=False):
    sales = day_data.get("sales")
    receipts = day_data.get("receipts")
    by_dow = baseline_block.get("by_dow", {}).get(str(dow))
    overall = baseline_block.get("overall", {})

    result = {
        "store": store,
        "status": "ok",   # ok / warn / bad / missing
        "messages": [],
        "target_date": target_date_used.isoformat(),
        "delayed": delayed,
    }

    # 데이터 누락
    if sales is None or sales <= 0:
        result["status"] = "missing"
        if delayed:
            result["messages"].append("이틀 전 데이터도 비어있음 — 동기화 누락 의심")
        else:
            result["messages"].append("어제 데이터 없음 — 동기화 누락 의심")
        return result

    # 매출 Z-score → 한글 메시지
    ref = by_dow if by_dow else overall
    dow_name = DOW_NAMES[dow] if by_dow else "전체 평균"
    if ref and ref.get("sales_mean"):
        z = z_score(sales, ref["sales_mean"], ref["sales_std"])
        if z is not None:
            result["_z_sales"] = round(z, 2)  # 내부용 (대시보드엔 안 보임)
            msg = korean_msg(sales, ref["sales_mean"], ref["sales_std"], z, dow_name, "매출")
            if abs(z) >= Z_BAD:
                result["status"] = "bad"
                result["messages"].append(msg)
            elif abs(z) >= Z_WARN:
                if result["status"] == "ok":
                    result["status"] = "warn"
                result["messages"].append(msg)
            # 정상 범위는 messages에 안 넣음 (깔끔하게)

    # 영수건수 (보조 — 매출 정상이어도 영수가 이상하면 표시)
    if receipts is not None and receipts > 0 and ref and ref.get("receipts_mean"):
        zr = z_score(receipts, ref["receipts_mean"], ref["receipts_std"])
        if zr is not None:
            result["_z_receipts"] = round(zr, 2)
            if abs(zr) >= Z_WARN:
                pct = pct_diff(receipts, ref["receipts_mean"])
                sign = "많음" if pct >= 0 else "적음"
                level = "강한 이상" if abs(zr) >= Z_BAD else "의심"
                rmsg = f"영수건수 {receipts:,}건 — 평소 {dow_name}요일보다 {abs(pct):.0f}% {sign} ({level})"
                result["messages"].append(rmsg)
                if abs(zr) >= Z_BAD:
                    result["status"] = "bad"
                elif result["status"] == "ok":
                    result["status"] = "warn"

    # 매출 + 영수 둘 다 정상 범위면 간결 메시지
    if not result["messages"]:
        result["messages"].append(f"매출·영수 모두 평소 {dow_name}요일 패턴 (정상)")

    result["sales"] = sales
    result["receipts"] = receipts
    return result


def main():
    baseline = load_baseline()
    if not baseline:
        print("baseline.json 없음 — 학습 먼저")
        return

    today = date.today()
    default_target = today - timedelta(days=1)

    stores_baseline = baseline.get("stores", {})

    results = []
    for store in sorted(stores_baseline.keys()):
        # 매장별 target_date 결정
        delay_days = DELAYED_STORES.get(store, 1)
        target = today - timedelta(days=delay_days)
        dow = target.weekday()
        delayed = (delay_days > 1)

        day = load_for_date(target)
        dd = day.get(store, {})
        bb = stores_baseline.get(store, {})

        if not dd:
            results.append({
                "store": store, "status": "missing",
                "messages": ["어제 데이터 없음 — 동기화 누락 의심"] if not delayed
                            else ["이틀 전 데이터도 비어있음 — 동기화 누락 의심"],
                "target_date": target.isoformat(), "delayed": delayed,
            })
            continue
        if not bb:
            results.append({
                "store": store, "status": "ok",
                "messages": ["베이스라인 학습 데이터 부족 — 검증 보류"],
                "target_date": target.isoformat(), "delayed": delayed,
                "sales": dd.get("sales"), "receipts": dd.get("receipts"),
            })
            continue

        r = assess_store(store, dd, bb, dow, target, delayed)
        results.append(r)

    # 요약
    status_counts = {"ok": 0, "warn": 0, "bad": 0, "missing": 0}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    if status_counts["bad"] or status_counts["missing"]:
        overall_status = "bad"
    elif status_counts["warn"]:
        overall_status = "warn"
    else:
        overall_status = "ok"

    health = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": default_target.isoformat(),  # 표시용 (대부분 매장 기준)
        "dow": DOW_NAMES[default_target.weekday()],
        "overall": overall_status,
        "summary": status_counts,
        "stores": results,
        "notes": {
            "수원": "1일 딜레이로 인해 이틀 전 데이터 검사",
        },
    }

    HEALTH_PATH.write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== 검사 결과 ({default_target} {DOW_NAMES[default_target.weekday()]}요일 기준) ===")
    print(f"전체: {overall_status.upper()}  |  ok:{status_counts['ok']}  warn:{status_counts['warn']}  bad:{status_counts['bad']}  missing:{status_counts['missing']}")
    for r in results:
        icon = {"ok":"✓", "warn":"⚠", "bad":"✗", "missing":"✗"}[r["status"]]
        suffix = f" ({r['target_date']} 데이터)" if r.get("delayed") else ""
        print(f"  {icon} {r['store']}{suffix}: {' / '.join(r['messages'])}")
    print(f"\n→ 저장: {HEALTH_PATH}")


if __name__ == "__main__":
    main()
