# -*- coding: utf-8 -*-
"""큐브포스(CubePOS, cube-tech WebCC) 매출 수집 공용 모듈 — 클라우드/로컬 공용.
환경변수 의존 없음(자격증명은 인자로 받음). 상세 스펙: 메모리 project_cubepos_http_api.

엔드포인트:
  로그인  POST /api/auth/login  {username, password}  → 세션 쿠키
  매출    GET  /api/business/bm-bg-bc-bd-day?h_id=INC&s_id=INC01&shop_id=<코드>&fm_dt&to_dt
          → 영수증단위 배열. 매출=b_rcb_amt 합, 영수=정상(b_st='N') 행수.
"""
import json
import calendar
import requests

CUBE_BASE = 'https://www.cube-tech.co.kr'
# 큐브포스 매장코드 → 매장키. 에스프레소바(INC03-1)는 다산에 합산.
CUBE_MAP = {'INC01': '하남', 'INC02': '가산', 'INC03': '다산', 'INC03-1': '다산'}


def login(uid, pw):
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0', 'Origin': CUBE_BASE, 'Accept': 'application/json'})
    r = s.post(CUBE_BASE + '/api/auth/login',
               data=json.dumps({'username': uid, 'password': pw}),
               headers={'Content-Type': 'application/json'}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'큐브포스 로그인 실패 {r.status_code}: {r.text[:120]}')
    return s


def scrape_range(uid, pw, start, end, log=print):
    """start/end = 'YYYY-MM-DD'. → {date: {store: {sales, receipts}}}"""
    s = login(uid, pw)
    by_date_store = {}
    for shop_id, store in CUBE_MAP.items():
        url = (f'{CUBE_BASE}/api/business/bm-bg-bc-bd-day'
               f'?h_id=INC&s_id=INC01&shop_id={shop_id}&fm_dt={start}&to_dt={end}')
        r = s.get(url, timeout=90)
        rows = r.json() if r.status_code == 200 else []
        if not isinstance(rows, list): rows = []
        cnt = 0
        for row in rows:
            dt = (row.get('bsn_dt') or '')[:10]
            if not dt: continue
            d = by_date_store.setdefault(dt, {}).setdefault(store, {'sales': 0, 'receipts': 0})
            d['sales'] += int(row.get('b_rcb_amt', 0) or 0)
            if row.get('b_st') == 'N': d['receipts'] += 1
            cnt += 1
        log(f'  [{store}/{shop_id}] rows: {cnt}')
    return by_date_store


def scrape_month(uid, pw, yyyy_mm, log=print):
    y, m = yyyy_mm.split('-')
    last = calendar.monthrange(int(y), int(m))[1]
    return scrape_range(uid, pw, f'{y}-{m}-01', f'{y}-{m}-{last:02d}', log)


def apply_to_existing(by_date_store, existing, log=print):
    """ops_data 구조(existing[store] = [{date, staff, ...}])에 매출/영수/객단가/생산성 반영.
    하남/가산/다산만 채움. staff는 건드리지 않고 있으면 생산성 재계산."""
    updated = 0
    for store in set(CUBE_MAP.values()):
        for entry in existing.get(store, []):
            ds = by_date_store.get(entry['date'], {}).get(store)
            if not ds or ds['sales'] <= 0: continue
            rec = ds['receipts'] or None
            if rec == 1 and ds['sales'] > 200_000: rec = None  # OK포스와 동일 가드
            entry['sales'] = ds['sales']
            entry['receipts'] = rec
            entry['per_receipt'] = (ds['sales'] // rec) if rec else None
            if entry.get('staff') and entry['staff'] > 0:
                entry['productivity'] = ds['sales'] // entry['staff']
            updated += 1
    log(f'  CubePOS updated: {updated}건')
    return updated
