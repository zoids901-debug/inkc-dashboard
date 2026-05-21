# -*- coding: utf-8 -*-
"""일자별 목표매출 자동계산 — 전년 동월 평일/주말 평균 × 배율.

규칙:
  - 일반 매장: 전년 동월의 평일평균·주말평균 × 1.2 (전년比 120% 목표)
  - 운정점:    전년 데이터 없으면 수원점 전년 동월 평일평균·주말평균 × 1.54.
               운정 자체 전년 데이터가 생기면 자동으로 일반 로직(×1.2)으로 전환.
  - 공휴일은 주말로 분류 (평일 중 공휴일도 주말평균 적용).
  - 전년 동월 데이터가 없는 기간(매장 오픈 첫 해 등)은 target=None.

ops_data/{YYYY-MM}.json 각 매장 일자 entry의 target 필드를 갱신.

사용:
  python compute_targets.py            # 당월
  python compute_targets.py 2026-05    # 특정 월
  python compute_targets.py --all      # ops_data 전체 월 재계산
"""
import os
import sys
import json
from datetime import date
from pathlib import Path

import holidays as _holidays

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
OPS_DIR = REPO_ROOT / "ops_data"

STORES = ['가산', '다산', '수원', '하남', '광주', '운정']
NORMAL_MULT = 1.2      # 일반 매장 — 전년 120% 목표
UNJEONG_MULT = 1.54    # 운정 — 수원 기준 154% 목표
UNJEONG_PROXY = '수원'  # 운정 전년 데이터 없을 때 기준 매장
ROUND_UNIT = 1000      # 목표값 천원 단위 반올림

_KR_HOL = _holidays.SouthKorea(years=range(2019, 2031))


def is_weekend_or_holiday(d):
    """토·일 또는 공휴일이면 True (주말 취급)."""
    return d.weekday() >= 5 or d in _KR_HOL


def load_month(year, month):
    p = OPS_DIR / f"{year:04d}-{month:02d}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def daytype_averages(records):
    """records → (평일평균, 주말평균). 매출>0 인 날만, 공휴일은 주말로."""
    wk, we = [], []
    for r in records or []:
        sales = r.get("sales") or 0
        if sales <= 0:
            continue
        try:
            d = date.fromisoformat(r["date"])
        except (ValueError, KeyError, TypeError):
            continue
        (we if is_weekend_or_holiday(d) else wk).append(sales)
    wk_avg = sum(wk) / len(wk) if wk else None
    we_avg = sum(we) / len(we) if we else None
    return wk_avg, we_avg


def _target(avg, mult):
    if not avg:
        return None
    return round(avg * mult / ROUND_UNIT) * ROUND_UNIT


def compute_month(year, month, dry=False):
    """해당 월 ops_data 파일의 모든 매장 target 필드를 갱신.
    반환: 갱신된 entry 수 (파일 없으면 None)."""
    cur = load_month(year, month)
    if not cur:
        return None

    prev = load_month(year - 1, month) or {}   # 전년 동월
    changed = 0

    for store in STORES:
        recs = cur.get(store)
        if not isinstance(recs, list):
            continue

        # 기준 매장·배율 결정
        if store == '운정':
            self_prev = prev.get('운정')
            if self_prev and any((r.get('sales') or 0) > 0 for r in self_prev):
                base_recs, mult = self_prev, NORMAL_MULT          # 운정 자체 전년 있음
            else:
                base_recs, mult = prev.get(UNJEONG_PROXY), UNJEONG_MULT  # 수원 대체
        else:
            base_recs, mult = prev.get(store), NORMAL_MULT

        wk_avg, we_avg = daytype_averages(base_recs)
        wk_t = _target(wk_avg, mult)
        we_t = _target(we_avg, mult)

        for entry in recs:
            try:
                d = date.fromisoformat(entry["date"])
            except (ValueError, KeyError, TypeError):
                continue
            t = we_t if is_weekend_or_holiday(d) else wk_t
            if entry.get("target") != t:
                changed += 1
            entry["target"] = t

    if not dry:
        p = OPS_DIR / f"{year:04d}-{month:02d}.json"
        # ops_actions_sync.py와 동일하게 indent=2로 기록 (형식 통일)
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return changed


def main():
    args = sys.argv[1:]

    if args and args[0] == '--all':
        months = sorted(p.stem for p in OPS_DIR.glob('20[0-9][0-9]-[0-9][0-9].json'))
        total, done = 0, 0
        for ym in months:
            y, m = int(ym[:4]), int(ym[5:7])
            c = compute_month(y, m)
            if c is not None:
                print(f'  {ym}: target {c}건 갱신')
                total += c
                done += 1
        print(f'전체 재계산 완료 — {done}개월 / target {total}건 갱신')
        return

    if len(args) == 1 and len(args[0]) == 7 and args[0][4] == '-':
        y, m = int(args[0][:4]), int(args[0][5:7])
    else:
        today = date.today()
        y, m = today.year, today.month

    c = compute_month(y, m)
    if c is None:
        print(f'{y:04d}-{m:02d}: ops_data 파일 없음 — 건너뜀')
    else:
        print(f'{y:04d}-{m:02d}: target {c}건 갱신')


if __name__ == "__main__":
    main()
