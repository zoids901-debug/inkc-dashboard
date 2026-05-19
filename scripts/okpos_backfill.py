# -*- coding: utf-8 -*-
"""OK포스 과거 데이터 backfill — 연 단위로 한 번에 fetch (실패 시 분기/월 fallback).

사용:
  python okpos_backfill.py 2024              # 2024년 1년치
  python okpos_backfill.py 2021 2024         # 2021~2024 4년치
  python okpos_backfill.py 2024-01 2024-12   # 월 범위 (이전 호환)

결과:
  - ops_data/raw_okpos_yearly/{YYYY}.json — 연 단위 일자별 raw (매장×일자×매출)
  - ops_data/raw_okpos/{YYYY-MM}.json     — 월 단위로 split 저장 (cross_checker용)
"""
import sys, os, json, asyncio, calendar, time
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ops_actions_sync import scrape_okpos_range, apply_okpos

STORES = ['가산', '다산', '수원', '하남', '광주', '운정']


def save_raw_by_month(okpos_by_date):
    """okpos_by_date를 월별로 split해서 ops_data/raw_okpos/{YYYY-MM}.json 저장."""
    from collections import defaultdict
    by_month = defaultdict(lambda: {s: [] for s in STORES})
    for dt in sorted(okpos_by_date.keys()):
        ym = dt[:7]  # YYYY-MM
        for store in STORES:
            rec = okpos_by_date.get(dt, {}).get(store)
            if rec:
                by_month[ym][store].append({
                    'date': dt,
                    'sales': rec.get('sales', 0),
                    'receipts': rec.get('receipts', 0),
                })
    raw_dir = Path('ops_data/raw_okpos')
    raw_dir.mkdir(parents=True, exist_ok=True)
    months_saved = []
    for ym, data in by_month.items():
        out_path = raw_dir / f'{ym}.json'
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        months_saved.append(ym)
    return months_saved


async def fetch_range_with_fallback(start_iso, end_iso, label=''):
    """일자 범위 fetch. 실패하면 분기 → 월 단위로 분할 재시도."""
    try:
        records = await scrape_okpos_range(start_iso, end_iso, label=label)
        existing = {s: [] for s in STORES}
        okpos_by_date = apply_okpos(records, existing)
        return okpos_by_date
    except Exception as e:
        print(f'  [{label}] 실패: {e}')
        return None


async def backfill_year(year):
    """1년치 시도 → 실패 시 분기 4개 → 실패 시 월 12개."""
    print(f'\n=== {year}년 backfill ===')
    today = date.today()

    # 미래 잘라냄
    year_end = date(year, 12, 31)
    if year_end > today: year_end = today
    start_iso = f'{year}-01-01'
    end_iso = year_end.isoformat()

    # 1) 1년치 한 번에
    print(f'\n[1단계] 1년치 한 번에 시도: {start_iso} ~ {end_iso}')
    result = await fetch_range_with_fallback(start_iso, end_iso, label=f'{year} (1년)')
    if result and len(result) > 60:  # 최소 2개월치 이상 받았으면 성공
        months = save_raw_by_month(result)
        total = sum(sum((r.get('sales') or 0) for r in result.get(d, {}).values() if isinstance(r, dict)) for d in result)
        print(f'  ✓ 성공 — {len(result)}일치, {len(months)}월 저장')
        return True

    # 2) 분기 단위 4개
    print(f'\n[2단계] 1년 실패 — 분기 4개로 분할')
    quarters = [
        (f'{year}-01-01', f'{year}-03-31'),
        (f'{year}-04-01', f'{year}-06-30'),
        (f'{year}-07-01', f'{year}-09-30'),
        (f'{year}-10-01', f'{year}-12-31'),
    ]
    all_data = {}
    for qs, qe in quarters:
        if qs > end_iso: break
        if qe > end_iso: qe = end_iso
        result = await fetch_range_with_fallback(qs, qe, label=f'{year} {qs}~{qe}')
        if result:
            all_data.update(result)
        time.sleep(5)
    if all_data:
        months = save_raw_by_month(all_data)
        print(f'  ✓ 분기 단위 성공 — {len(all_data)}일치, {len(months)}월 저장')
        return True

    # 3) 월 단위 12개 (마지막 수단)
    print(f'\n[3단계] 분기도 실패 — 월 12개로 분할')
    all_data = {}
    for m in range(1, 13):
        last_day = calendar.monthrange(year, m)[1]
        ms = f'{year}-{m:02d}-01'
        me = f'{year}-{m:02d}-{last_day:02d}'
        if ms > end_iso: break
        if me > end_iso: me = end_iso
        result = await fetch_range_with_fallback(ms, me, label=f'{year}-{m:02d}')
        if result:
            all_data.update(result)
        time.sleep(3)
    if all_data:
        months = save_raw_by_month(all_data)
        print(f'  ✓ 월 단위 성공 — {len(all_data)}일치, {len(months)}월 저장')
        return True

    print(f'  ✗ {year}년 backfill 완전 실패')
    return False


async def backfill_single_month(yyyy_mm):
    """단일 월 fetch — 직전 월 누락 보완용."""
    print(f'\n=== {yyyy_mm} 단일 월 backfill ===')
    y, m = map(int, yyyy_mm.split('-'))
    last_day = calendar.monthrange(y, m)[1]
    today = date.today()
    if y == today.year and m == today.month:
        last_day = today.day
    start = f'{y:04d}-{m:02d}-01'
    end = f'{y:04d}-{m:02d}-{last_day:02d}'
    result = await fetch_range_with_fallback(start, end, label=yyyy_mm)
    if result:
        months = save_raw_by_month(result)
        print(f'  ✓ 성공 — {len(result)}일치, {len(months)}월 저장')
        return True
    print(f'  ✗ 실패')
    return False


def parse_args(args):
    """인자 파싱 — 단일 월(YYYY-MM) 또는 연도 단위."""
    if len(args) == 1 and '-' in args[0] and len(args[0]) == 7:
        # YYYY-MM 단일 월
        return [('month', args[0])]
    # 연도 단위
    years = []
    if len(args) == 1:
        years = [int(args[0])]
    elif len(args) == 2:
        a, b = args
        if '-' in a or '-' in b:
            y1 = int(a.split('-')[0])
            y2 = int(b.split('-')[0])
        else:
            y1, y2 = int(a), int(b)
        years = list(range(min(y1, y2), max(y1, y2) + 1))
    return [('year', y) for y in years]


async def main():
    if len(sys.argv) < 2:
        print('Usage:\n  python okpos_backfill.py YYYY          # 연도 전체\n  python okpos_backfill.py YYYY YYYY     # 연도 범위\n  python okpos_backfill.py YYYY-MM       # 단일 월 (매월 1일 보완용)')
        sys.exit(1)
    targets = parse_args(sys.argv[1:])
    if not targets:
        print('인자 파싱 실패')
        sys.exit(1)
    print(f'=== OK포스 backfill: {targets} ===')

    succ = []
    fail = []
    for kind, val in targets:
        if kind == 'month':
            ok = await backfill_single_month(val)
        else:
            ok = await backfill_year(val)
        if ok: succ.append(val)
        else:  fail.append(val)
        if (kind, val) != targets[-1]:
            print('  (다음 대상 전 5초 대기)')
            time.sleep(5)
    print(f'\n=== 최종: 성공 {succ} / 실패 {fail} ===')


if __name__ == '__main__':
    asyncio.run(main())
