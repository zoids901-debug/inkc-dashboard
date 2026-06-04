# -*- coding: utf-8 -*-
"""상품 대시보드(product-dashboard) 일 점검 — 매일 새벽 data-health 워크플로우에서 실행.

검사 항목:
- 어제 일자별 데이터에 6개 매장(가산·다산·하남·광주·수원·운정)이 모두 수집됐는지
- 수원은 1일 딜레이 → 이틀 전 데이터로 검사
- 운정은 토스(TOSS) 매장 → 토스 API 원본 매출과 직접 대조

출력: ops_data/product_health.json — anomaly_detector가 health.json에 합치고,
      health_mail이 점검 메일에 상품 대시보드 섹션으로 표시.
필요 환경변수: TOSS_ID, TOSS_PW
"""
import os
import sys
import json
import urllib.request
from datetime import date, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toss_lib import toss_login, toss_day_net

REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
OUT_PATH = REPO_ROOT / "ops_data" / "product_health.json"

PROD_REPO = "zoids901-debug/product-dashboard"
def _gh_token():
    import os, sys
    t = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if t:
        return t
    try:
        sys.path.insert(0, r"C:\Users\zoids\Scripts\creds")
        from creds import get_cred
        return get_cred("github_pat") or ""
    except Exception:
        return ""
_GH_TOKEN = _gh_token()
# product-dashboard 비공개 전환 대비 — Contents API + 토큰 (공개일 때도 동작)
CONTENTS_BASE = f"https://api.github.com/repos/{PROD_REPO}/contents"

OKPOS_STORES = ['가산', '다산', '하남', '광주']  # 어제 데이터 기대
DELAYED = {'수원': 2}                            # 수원 1일 딜레이 → 이틀 전
TOSS_ABS_MIN = 50_000   # 운정 대조 — 절대 차이 5만원 미만은 noise
TOSS_PCT_WARN = 1.0
TOSS_PCT_BAD = 5.0


def fetch_daily(d):
    """product-dashboard data/daily/YYMMDD.json 가져오기 (없으면 None). 공개 repo."""
    fname = d.strftime('%y%m%d') + '.json'
    url = f"{CONTENTS_BASE}/data/daily/{fname}"
    try:
        headers = {'User-Agent': 'product-health/1.0', 'Accept': 'application/vnd.github.raw'}
        if _GH_TOKEN:
            headers['Authorization'] = 'token ' + _GH_TOKEN
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception:
        return None


def store_net(daily, store):
    items = (daily or {}).get('stores', {}).get(store) or []
    return sum(int(it.get('net', 0)) for it in items), len(items)


def main():
    today = datetime.now(timezone(timedelta(hours=9))).date()  # KST (UTC 였던 버그 수정)
    results = []
    cache = {}

    def daily_for(d):
        k = d.isoformat()
        if k not in cache:
            cache[k] = fetch_daily(d)
        return cache[k]

    # ── OK포스 매장 + 수원: 어제(수원은 이틀 전) 데이터 수집 여부 ──
    for store in OKPOS_STORES + ['수원']:
        delay = DELAYED.get(store, 1)
        target = today - timedelta(days=delay)
        delayed = delay > 1
        daily = daily_for(target)
        net, cnt = store_net(daily, store)
        r = {"store": store, "target_date": target.isoformat(), "delayed": delayed}
        if daily is None:
            r["status"] = "missing"
            r["messages"] = [f"{target} 일자별 파일 자체가 없음 — 동기화 누락 의심"]
        elif cnt == 0:
            r["status"] = "missing"
            r["messages"] = [("이틀 전" if delayed else "어제") + " 데이터 없음 — 동기화 누락 의심"]
        else:
            r["status"] = "ok"
            r["messages"] = [f"{cnt}종 / 정가매출 {net:,}원 — 정상 수집"]
        results.append(r)

    # ── 운정: 토스 API 원본과 직접 대조 ──
    target = today - timedelta(days=1)
    daily = daily_for(target)
    prod_net, cnt = store_net(daily, '운정')
    r = {"store": "운정", "target_date": target.isoformat(), "delayed": False}
    if daily is None or cnt == 0:
        r["status"] = "missing"
        r["messages"] = [f"{target} 운정 데이터 없음 — 토스 동기화 누락 의심"]
    else:
        try:
            hdr = toss_login()
            toss_net = toss_day_net(hdr, target.isoformat())['net']
            diff = prod_net - toss_net
            base = max(prod_net, toss_net) or 1
            pct = abs(diff) / base * 100
            if abs(diff) < TOSS_ABS_MIN:
                r["status"] = "ok"
                r["messages"] = [f"{cnt}종 / 정가매출 {prod_net:,}원 — 토스 원본과 일치"]
            elif pct >= TOSS_PCT_BAD:
                r["status"] = "bad"
                r["messages"] = [f"토스 원본 {toss_net:,}원 vs 대시보드 {prod_net:,}원 "
                                 f"({diff:+,}원, {pct:.1f}%) — 강한 불일치"]
            elif pct >= TOSS_PCT_WARN:
                r["status"] = "warn"
                r["messages"] = [f"토스 원본 {toss_net:,}원 vs 대시보드 {prod_net:,}원 "
                                 f"({diff:+,}원, {pct:.1f}%) — 의심"]
            else:
                r["status"] = "ok"
                r["messages"] = [f"{cnt}종 / 정가매출 {prod_net:,}원 — 토스 원본과 거의 일치 ({pct:.1f}%)"]
        except Exception as e:
            r["status"] = "warn"
            r["messages"] = [f"운정 {cnt}종 / {prod_net:,}원 — 토스 대조 실패({e}), 수집 자체는 정상"]
    results.append(r)

    summary = {"ok": 0, "warn": 0, "bad": 0, "missing": 0}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    overall = "bad" if (summary["bad"] or summary["missing"]) else ("warn" if summary["warn"] else "ok")

    out = {
        "checked_at": today.isoformat(),
        "target_date": (today - timedelta(days=1)).isoformat(),
        "overall": overall,
        "summary": summary,
        "stores": results,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== 상품 대시보드 일 점검 (전체: {overall.upper()}) ===")
    for r in results:
        icon = {"ok": "✓", "warn": "⚠", "bad": "✗", "missing": "✗"}[r["status"]]
        suffix = f" ({r['target_date']} 데이터)" if r.get("delayed") else ""
        print(f"  {icon} {r['store']}{suffix}: {' / '.join(r['messages'])}")
    print(f"→ 저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
