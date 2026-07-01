# -*- coding: utf-8 -*-
"""어제 매출/영수 데이터 vs 베이스라인 → 이상 감지 + 교차 검증 결과 통합.
- 한글 메시지로 보고
- 수원점: 1일 딜레이 → 이틀 전 데이터 검사
- cross_check.json (raw_okpos vs ops_data 월 합산 비교) 결과를 health.json에 합침
- 새벽 5시 KST 정기 실행

출력: ops_data/health.json
"""
import json, os, statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
OPS_DIR = REPO_ROOT / "ops_data"
BASELINE_PATH = OPS_DIR / "baseline.json"
HEALTH_PATH = OPS_DIR / "health.json"
CROSS_CHECK_PATH = OPS_DIR / "cross_check.json"
PRODUCT_HEALTH_PATH = OPS_DIR / "product_health.json"

DOW_NAMES = ["월", "화", "수", "목", "금", "토", "일"]
Z_WARN = 2.0
Z_BAD  = 3.0
DELAYED_STORES = {"수원": 2}

# 큐브포스(CubePOS) 전환 매장 — 2026-07-01부터 구 POS(OK포스/토스) 피드가 끊김.
# 큐브포스 연동이 붙기 전까지 '데이터 없음'은 오경보이므로 missing 이 아닌
# 무해한 'migrating' 으로 분류(깃허브 이슈·이상 집계 제외). 큐브포스로 데이터가
# 다시 들어오기 시작하면 해당 매장을 이 목록에서 제거할 것.
MIGRATING_STORES = {"하남", "가산", "다산"}


def load_baseline():
    if not BASELINE_PATH.exists(): return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def load_for_date(d):
    fname = OPS_DIR / f"{d.year}-{d.month:02d}.json"
    if not fname.exists(): return {}
    data = json.loads(fname.read_text(encoding="utf-8"))
    iso = d.isoformat()
    result = {}
    for store, records in data.items():
        if not isinstance(records, list): continue
        for r in records:
            if r.get("date") == iso:
                result[store] = {"sales": r.get("sales"), "receipts": r.get("receipts")}
                break
    return result


def load_cross_check():
    if not CROSS_CHECK_PATH.exists(): return None
    return json.loads(CROSS_CHECK_PATH.read_text(encoding="utf-8"))


def load_product_health():
    if not PRODUCT_HEALTH_PATH.exists(): return None
    return json.loads(PRODUCT_HEALTH_PATH.read_text(encoding="utf-8"))


def z_score(actual, mean, std):
    if std is None or std <= 0: return None
    return (actual - mean) / std


def pct_diff(actual, mean):
    if not mean: return 0
    return (actual / mean - 1) * 100


def korean_msg(sales, mean, std, z, dow_name, kind="매출"):
    if z is None:
        return f"{kind} {sales:,}원 (베이스라인 표준편차 부족)"
    pct = pct_diff(sales, mean)
    sign = "높음" if pct >= 0 else "낮음"
    pct_abs = abs(pct)
    if abs(z) >= Z_BAD: level = "강한 이상"
    elif abs(z) >= Z_WARN: level = "의심"
    else: level = "정상 범위"
    if abs(z) < Z_WARN:
        return f"{kind} {sales:,}원 — 평소 {dow_name}요일 평균({int(mean):,}원)과 비슷 ({level})"
    return f"{kind} {sales:,}원 — 평소 {dow_name}요일보다 {pct_abs:.0f}% {sign} ({level})"


def assess_store(store, day_data, baseline_block, dow, target_date_used, delayed=False):
    sales = day_data.get("sales")
    receipts = day_data.get("receipts")
    by_dow = baseline_block.get("by_dow", {}).get(str(dow))
    overall = baseline_block.get("overall", {})

    result = {
        "store": store, "status": "ok", "messages": [],
        "target_date": target_date_used.isoformat(), "delayed": delayed,
    }

    if sales is None or sales <= 0:
        if store in MIGRATING_STORES:
            result["status"] = "migrating"
            result["messages"].append("큐브포스 전환 매장 — 구 POS 피드 없음(정상, 큐브포스 연동 대기중)")
            return result
        result["status"] = "missing"
        if delayed:
            result["messages"].append("이틀 전 데이터도 비어있음 — 동기화 누락 의심")
        else:
            result["messages"].append("어제 데이터 없음 — 동기화 누락 의심")
        return result

    ref = by_dow if by_dow else overall
    dow_name = DOW_NAMES[dow] if by_dow else "전체 평균"

    if ref and ref.get("sales_mean"):
        z = z_score(sales, ref["sales_mean"], ref["sales_std"])
        if z is not None:
            msg = korean_msg(sales, ref["sales_mean"], ref["sales_std"], z, dow_name, "매출")
            if abs(z) >= Z_BAD:
                result["status"] = "bad"; result["messages"].append(msg)
            elif abs(z) >= Z_WARN:
                if result["status"] == "ok": result["status"] = "warn"
                result["messages"].append(msg)

    if receipts is not None and receipts > 0 and ref and ref.get("receipts_mean"):
        zr = z_score(receipts, ref["receipts_mean"], ref["receipts_std"])
        if zr is not None and abs(zr) >= Z_WARN:
            pct = pct_diff(receipts, ref["receipts_mean"])
            sign = "많음" if pct >= 0 else "적음"
            level = "강한 이상" if abs(zr) >= Z_BAD else "의심"
            result["messages"].append(f"영수건수 {receipts:,}건 — 평소 {dow_name}요일보다 {abs(pct):.0f}% {sign} ({level})")
            if abs(zr) >= Z_BAD: result["status"] = "bad"
            elif result["status"] == "ok": result["status"] = "warn"

    if not result["messages"]:
        result["messages"].append(f"매출·영수 모두 평소 {dow_name}요일 패턴 (정상)")

    result["sales"] = sales
    result["receipts"] = receipts
    return result


def main():
    baseline = load_baseline()
    if not baseline:
        print("baseline.json 없음 — 학습 먼저"); return

    today = datetime.now(timezone(timedelta(hours=9))).date()  # KST (UTC 였던 버그 수정)
    default_target = today - timedelta(days=1)
    stores_baseline = baseline.get("stores", {})

    # ── 시계열 검사 (어제 데이터) ──
    results = []
    for store in sorted(stores_baseline.keys()):
        delay_days = DELAYED_STORES.get(store, 1)
        target = today - timedelta(days=delay_days)
        dow = target.weekday()
        delayed = (delay_days > 1)
        day = load_for_date(target)
        dd = day.get(store, {})
        bb = stores_baseline.get(store, {})

        if not dd:
            if store in MIGRATING_STORES:
                results.append({
                    "store": store, "status": "migrating",
                    "messages": ["큐브포스 전환 매장 — 구 POS 피드 없음(정상, 큐브포스 연동 대기중)"],
                    "target_date": target.isoformat(), "delayed": delayed,
                })
                continue
            results.append({
                "store": store, "status": "missing",
                "messages": ["이틀 전 데이터도 비어있음 — 동기화 누락 의심"] if delayed
                            else ["어제 데이터 없음 — 동기화 누락 의심"],
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

        results.append(assess_store(store, dd, bb, dow, target, delayed))

    status_counts = {"ok": 0, "warn": 0, "bad": 0, "missing": 0, "migrating": 0}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    if status_counts["bad"] or status_counts["missing"]: ts_status = "bad"
    elif status_counts["warn"]: ts_status = "warn"
    else: ts_status = "ok"

    # ── 교차 검증 결과 통합 ──
    cross = load_cross_check()
    cross_block = None
    if cross:
        cross_block = {
            "checked_at": cross.get("checked_at"),
            "yyyy_mm": cross.get("yyyy_mm"),
            "overall": cross.get("overall", cross.get("status", "ok")),
            "message": cross.get("message"),
            "stores": cross.get("stores", []),
        }
    else:
        cross_block = {"overall": "no_data", "message": "교차 검증 결과 없음"}

    # ── 상품 대시보드 일 점검 통합 ──
    product = load_product_health()
    if product:
        product_block = {
            "checked_at": product.get("checked_at"),
            "target_date": product.get("target_date"),
            "overall": product.get("overall", "ok"),
            "summary": product.get("summary", {}),
            "stores": product.get("stores", []),
        }
    else:
        product_block = {"overall": "no_data", "message": "상품 대시보드 점검 결과 없음"}

    # 전체 상태 — 시계열·교차 검증·상품 대시보드 중 가장 나쁜 쪽
    priority = {"ok": 0, "no_data": 0, "migrating": 0, "warn": 1, "bad": 2, "missing": 2}
    cross_overall = cross_block.get("overall", "ok")
    product_overall = product_block.get("overall", "ok")
    overall = ts_status
    for cand in (cross_overall, product_overall):
        if priority.get(cand, 0) > priority.get(overall, 0):
            overall = cand

    health = {
        "checked_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        "target_date": default_target.isoformat(),
        "dow": DOW_NAMES[default_target.weekday()],
        "overall": overall,
        "summary": status_counts,
        "stores": results,
        "cross_check": cross_block,
        "product_health": product_block,
        "notes": {
            "수원": "1일 딜레이로 인해 이틀 전 데이터 검사",
        },
    }

    HEALTH_PATH.write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== 시계열 검사 ({default_target} {DOW_NAMES[default_target.weekday()]}요일 기준) ===")
    print(f"전체: {ts_status.upper()}  |  ok:{status_counts['ok']}  warn:{status_counts['warn']}  bad:{status_counts['bad']}  missing:{status_counts['missing']}")
    for r in results:
        icon = {"ok":"✓", "warn":"⚠", "bad":"✗", "missing":"✗", "migrating":"→"}.get(r["status"], "·")
        suffix = f" ({r['target_date']} 데이터)" if r.get("delayed") else ""
        print(f"  {icon} {r['store']}{suffix}: {' / '.join(r['messages'])}")
    print(f"\n=== 교차 검증 (OK포스 raw vs 운영 대시보드 월 합산) ===")
    print(f"전체: {cross_overall.upper()}")
    for s in (cross_block.get("stores") or []):
        icon = {"ok":"✓", "warn":"⚠", "bad":"✗", "info":"ⓘ"}.get(s.get("level"), "·")
        print(f"  {icon} {s['store']}: {s.get('message','')} (차이 {s.get('diff',0):+,}, {s.get('pct',0):.1f}%)")
    print(f"\n=== 상품 대시보드 일 점검 ===")
    print(f"전체: {product_block.get('overall','no_data').upper()}")
    for s in (product_block.get("stores") or []):
        icon = {"ok":"✓", "warn":"⚠", "bad":"✗", "missing":"✗"}.get(s.get("status"), "·")
        print(f"  {icon} {s['store']}: {' / '.join(s.get('messages', []))}")
    print(f"\n→ 저장: {HEALTH_PATH} (전체 상태: {overall.upper()})")


if __name__ == "__main__":
    main()
