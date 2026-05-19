# -*- coding: utf-8 -*-
"""OK포스 과거 데이터 backfill — 월 범위 받아서 raw_okpos만 저장 (ops_data 건드리지 않음).

사용:
  python okpos_backfill.py 2024-01 2024-12       # 범위
  python okpos_backfill.py 2024-05               # 단일 월
"""
import sys, os, json, asyncio, calendar, time
from pathlib import Path

# ops_actions_sync 모듈 사용
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ops_actions_sync import scrape_okpos, apply_okpos

STORES = ['가산', '다산', '수원', '하남', '광주', '운정']


async def backfill_month(yyyy_mm):
    y, m = map(int, yyyy_mm.split('-'))
    last_day = calendar.monthrange(y, m)[1]
    existing = {
        s: [{'date': f'{y:04d}-{m:02d}-{d:02d}'} for d in range(1, last_day + 1)]
        for s in STORES
    }
    try:
        records = await scrape_okpos(yyyy_mm)
    except Exception as e:
        print(f'  [{yyyy_mm}] scrape 실패: {e}')
        return False

    okpos_by_date = apply_okpos(records, existing)

    raw_by_store = {s: [] for s in STORES}
    for dt in sorted(okpos_by_date.keys()):
        for store in STORES:
            rec = okpos_by_date.get(dt, {}).get(store)
            if rec:
                raw_by_store[store].append({
                    'date': dt,
                    'sales': rec.get('sales', 0),
                    'receipts': rec.get('receipts', 0),
                })
    raw_dir = Path('ops_data/raw_okpos')
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / f'{yyyy_mm}.json'
    out_path.write_text(json.dumps(raw_by_store, ensure_ascii=False, indent=2), encoding='utf-8')

    total = sum(len(v) for v in raw_by_store.values())
    by_store = {s: sum((r.get('sales') or 0) for r in raw_by_store[s]) for s in STORES}
    print(f'  [{yyyy_mm}] {total}건 저장')
    for s, v in by_store.items():
        if v > 0:
            print(f'      {s}: {v:,}')
    return True


def month_range(from_ym, to_ym):
    y1, m1 = map(int, from_ym.split('-'))
    y2, m2 = map(int, to_ym.split('-'))
    months = []
    y, m = y1, m1
    while (y, m) <= (y2, m2):
        months.append(f'{y:04d}-{m:02d}')
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


async def main():
    if len(sys.argv) < 2:
        print('Usage: python okpos_backfill.py YYYY-MM [YYYY-MM]')
        sys.exit(1)
    from_ym = sys.argv[1]
    to_ym = sys.argv[2] if len(sys.argv) >= 3 else from_ym
    months = month_range(from_ym, to_ym)
    print(f'=== OK포스 backfill: {from_ym} ~ {to_ym} ({len(months)}개월) ===')
    succ = 0
    fail = 0
    for ym in months:
        print(f'\n[{ym}] 시작')
        ok = await backfill_month(ym)
        if ok:
            succ += 1
        else:
            fail += 1
        # OK포스 부하 줄이기 — 월간 5초 대기
        if ym != months[-1]:
            time.sleep(5)
    print(f'\n=== 완료: 성공 {succ} / 실패 {fail} ===')


if __name__ == '__main__':
    asyncio.run(main())
