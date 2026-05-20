# -*- coding: utf-8 -*-
"""상품 대시보드 검증 — product-dashboard의 OK포스 raw(상품별 정가) vs 월별 합산.

product-dashboard repo의 데이터를 GitHub raw로 읽어 매장×연도 합 비교.
상품 대시보드는 할인·부가세 미적용 정가 → raw_okpos_yearly와 0원 일치가 목표.

출력: ops_data/product_cross_check.json
"""
import json, os, urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
OUT_PATH = REPO_ROOT / "ops_data" / "product_cross_check.json"

PROD_REPO = "zoids901-debug/product-dashboard"
RAW_BASE = f"https://raw.githubusercontent.com/{PROD_REPO}/main"
API_TREE = f"https://api.github.com/repos/{PROD_REPO}/git/trees/main?recursive=1"

PCT_WARN = 1.0
PCT_BAD = 5.0
ABS_MIN = 100_000


def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'cross-check/1.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    today = date.today()

    # 1) 월별 파일 목록 (Trees API)
    tree = fetch_json(API_TREE)
    month_files = [x['path'] for x in tree.get('tree', [])
                   if x['path'].startswith('data/') and len(x['path']) == len('data/YYMM.json')
                   and x['path'].endswith('.json') and x['path'][5:9].isdigit()]

    # 2) 월별 → 매장×연도 합산
    prod_sy = {}
    for p in sorted(month_files):
        yymm = p.split('/')[-1].replace('.json', '')
        year = str(2000 + int(yymm[:2]))
        try:
            j = fetch_json(f"{RAW_BASE}/{p}")
        except Exception as e:
            print(f"  ! {yymm} 실패: {e}")
            continue
        for it in j.get('items', []):
            store = it.get('store')
            if not store:
                continue
            prod_sy[(year, store)] = prod_sy.get((year, store), 0) + int(it.get('net', 0))

    # 3) raw_okpos_yearly와 비교
    results = []
    for year in ['2021', '2022', '2023', '2024', '2025', '2026']:
        try:
            raw_j = fetch_json(f"{RAW_BASE}/data/raw_okpos_yearly/{year}.json")
        except Exception:
            continue
        raw_store = {loc: sum(int(x.get('net', 0)) for x in items)
                     for loc, items in raw_j.get('stores', {}).items()}
        stores = sorted(set(raw_store) | {s for (y, s) in prod_sy if y == year})
        for store in stores:
            # 운정은 토스(TOSS) 매장 — OK포스 상품별 매출현황에 없음, 검증 대상 아님
            if store == '운정':
                continue
            rn = raw_store.get(store, 0)
            pn = prod_sy.get((year, store), 0)
            if rn == 0 and pn == 0:
                continue
            diff = pn - rn
            base = max(rn, pn) or 1
            pct = abs(diff) / base * 100
            if abs(diff) < ABS_MIN:
                level, msg = "ok", "OK포스 원본과 일치"
            elif pct >= PCT_BAD:
                level, msg = "bad", "큰 차이 — 상품 누락/오분류 의심"
            elif pct >= PCT_WARN:
                level, msg = "warn", "1% 이상 차이 — 부분 누락 가능"
            else:
                level, msg = "ok", "미세한 차이 (진행 중인 해 시차 등)"
            results.append({
                "year": year, "store": store,
                "raw_total": rn, "prod_total": pn,
                "diff": diff, "pct": round(pct, 2),
                "level": level, "message": msg,
            })

    out = {"checked_at": today.isoformat(), "results": results}
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 상품 대시보드 × OK포스 원본 (매장×연도) ===")
    for r in results:
        icon = {"ok": "✓", "warn": "⚠", "bad": "✗"}[r["level"]]
        print(f"{r['year']} {r['store']:<5} raw {r['raw_total']:>14,} / 상품 {r['prod_total']:>14,} "
              f"/ {r['diff']:>+12,} ({r['pct']:.2f}%) {icon}")
    print(f"\n→ 저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
