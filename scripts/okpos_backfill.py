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


def parse_years(args):
    """인자에서 연도 리스트 추출."""
    years = []
    if len(args) == 1:
        # 단일 인자: 연도 또는 YYYY-MM (이전 호환)
        a = args[0]
        if '-' in a:
            # YYYY-MM 단일 — 그 연도만
            years = [int(a.split('-')[0])]
        else:
            years = [int(a)]
    elif len(args) == 2:
        a, b = args
        if '-' in a or '-' in b:
            # YYYY-MM YYYY-MM — 범위 내 연도들
            y1 = int(a.split('-')[0])
            y2 = int(b.split('-')[0])
        else:
            y1, y2 = int(a), int(b)
        years = list(range(min(y1, y2), max(y1, y2) + 1))
    return years


async def main():
    if len(sys.argv) < 2:
        print('Usage: python okpos_backfill.py YYYY [YYYY]')
        sys.exit(1)
    years = parse_years(sys.argv[1:])
    if not years:
        print('연도 파싱 실패')
        sys.exit(1)
    print(f'=== OK포스 backfill (연 단위): {years} ===')

    succ = []
    fail = []
    for year in years:
        ok = await backfill_year(year)
        if ok: succ.append(year)
        else:  fail.append(year)
        if year != years[-1]:
            print('  (다음 연도 전 10초 대기)')
            time.sleep(10)
    print(f'\n=== 최종: 성공 {succ} / 실패 {fail} ===')


if __name__ == '__main__':
    asyncio.run(main())
