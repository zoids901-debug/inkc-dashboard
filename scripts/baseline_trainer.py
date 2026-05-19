# -*- coding: utf-8 -*-
"""인크커피 매장별 매출 베이스라인 학습.
매장 × 요일별 평균/표준편차. 시즈널/이벤트 학습 제외 (매년 변동 심해).

데이터 소스: inkc-dashboard repo의 ops_data/{YYYY-MM}.json (2021-05 ~ 현재)
출력: ops_data/baseline.json
"""
import sys, io, json, base64, urllib.request, statistics, math
from datetime import datetime, date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r"C:\Users\zoids\Scripts\creds")
from creds import get_cred

PAT = get_cred("github_pat")
REPO = "zoids901-debug/inkc-dashboard"
HDRS = {"Authorization": f"token {PAT}", "User-Agent": "baseline",
        "Accept": "application/vnd.github+json"}
RAW_HDRS = {"Authorization": f"token {PAT}", "User-Agent": "baseline"}

DOW_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


def list_ops_files():
    api = f"https://api.github.com/repos/{REPO}/contents/ops_data"
    with urllib.request.urlopen(urllib.request.Request(api, headers=HDRS), timeout=20) as r:
        items = json.loads(r.read())
    files = [it["name"] for it in items if it["type"] == "file"
             and it["name"].endswith(".json")
             and it["name"][0].isdigit()]  # YYYY-MM.json만
    return sorted(files)


def fetch_raw(path):
    url = f"https://raw.githubusercontent.com/{REPO}/main/{path}"
    req = urllib.request.Request(url, headers=RAW_HDRS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# 학습 — 최근 3년만 (가격 인상/메뉴 리뉴얼 영향 최소화)
def main():
    today = date.today()
    cutoff = date(today.year - 3, today.month, 1)

    files = list_ops_files()
    print(f"ops_data 파일: {len(files)}개")

    # samples[store][dow] = [sales, sales, ...]
    samples = {}
    rec_samples = {}  # 영수건수도 같이
    first_date = {}
    last_date = {}

    for fname in files:
        # 파일명: 2024-05.json
        try:
            ym = fname.replace(".json", "")
            fdate = datetime.strptime(ym + "-01", "%Y-%m-%d").date()
        except ValueError:
            continue
        if fdate < cutoff:
            continue
        try:
            data = fetch_raw(f"ops_data/{fname}")
        except Exception as e:
            print(f"  [{fname}] fetch 실패: {e}")
            continue
        for store, records in data.items():
            if not isinstance(records, list):
                continue
            for r in records:
                dt = r.get("date")
                sales = r.get("sales")
                rec = r.get("receipts")
                if not dt or sales is None or sales <= 0:
                    continue
                d = datetime.strptime(dt, "%Y-%m-%d").date()
                dow = d.weekday()  # 0=월
                samples.setdefault(store, {}).setdefault(dow, []).append(sales)
                if rec is not None and rec > 0:
                    rec_samples.setdefault(store, {}).setdefault(dow, []).append(rec)
                first_date.setdefault(store, dt)
                if dt < first_date[store]: first_date[store] = dt
                last_date[store] = max(last_date.get(store, dt), dt)

    # 통계 계산
    baseline = {
        "trained_at": today.isoformat(),
        "cutoff_from": cutoff.isoformat(),
        "stores": {},
    }
    for store in sorted(samples.keys()):
        store_block = {"by_dow": {}, "overall": {}, "data_range": [first_date.get(store), last_date.get(store)]}
        # 매장 전체 통계 (백업)
        all_sales = [v for dow_list in samples[store].values() for v in dow_list]
        all_rec = [v for dow_list in rec_samples.get(store, {}).values() for v in dow_list]
        if all_sales:
            store_block["overall"] = {
                "n": len(all_sales),
                "sales_mean": int(statistics.mean(all_sales)),
                "sales_std": int(statistics.stdev(all_sales)) if len(all_sales) >= 2 else 0,
                "receipts_mean": int(statistics.mean(all_rec)) if all_rec else 0,
                "receipts_std": int(statistics.stdev(all_rec)) if len(all_rec) >= 2 else 0,
            }
        # 요일별 통계
        for dow in range(7):
            sv = samples[store].get(dow, [])
            rv = rec_samples.get(store, {}).get(dow, [])
            if len(sv) < 5:  # 표본 부족 시 스킵 (overall 사용)
                continue
            store_block["by_dow"][str(dow)] = {
                "dow_name": DOW_NAMES[dow],
                "n": len(sv),
                "sales_mean": int(statistics.mean(sv)),
                "sales_std": int(statistics.stdev(sv)),
                "sales_min": min(sv),
                "sales_max": max(sv),
                "receipts_mean": int(statistics.mean(rv)) if rv else 0,
                "receipts_std": int(statistics.stdev(rv)) if len(rv) >= 2 else 0,
            }
        baseline["stores"][store] = store_block
        # 출력
        ov = store_block["overall"]
        print(f"\n[{store}] {first_date.get(store)} ~ {last_date.get(store)}, 총 {ov['n']}일")
        print(f"  전체 매출 평균: {ov['sales_mean']:>13,} ± {ov['sales_std']:,}")
        for dow in range(7):
            d = store_block["by_dow"].get(str(dow))
            if not d:
                print(f"  {DOW_NAMES[dow]}: 표본 부족")
                continue
            print(f"  {DOW_NAMES[dow]} ({d['n']}일): {d['sales_mean']:>13,} ± {d['sales_std']:,}")

    # 저장 (로컬)
    out = r"C:\Users\zoids\baseline.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
    print(f"\n→ 저장: {out} ({len(json.dumps(baseline))//1024} KB)")


if __name__ == "__main__":
    main()
