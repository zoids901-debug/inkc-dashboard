# -*- coding: utf-8 -*-
"""inkc-dashboard 운영 데이터 GH Actions 자동 동기화
- OKPOS day-total 스크래핑 (5개 매장 매출+영수)
- TOSS 운정 스크래핑 (백업)
- 6개 매장 Google Sheets fetch (staff, target, sales/receipts 일부)
- ops_data/{YYYY-MM}.json 갱신
- node build.js 실행 (docs/index.html 생성)
- commit & push (workflow의 git steps이 처리)

환경변수: GH_TOKEN, GH_REPO(zoids901-debug/inkc-dashboard), OKPOS_ID, OKPOS_PW, TOSS_ID, TOSS_PW
"""
import os, sys, io, json, base64, asyncio, urllib.request, urllib.error, urllib.parse, csv, re, time
from datetime import date, timedelta, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests

GH_TOKEN = os.environ['GH_TOKEN']
GH_REPO  = os.environ.get('GH_REPO', 'zoids901-debug/inkc-dashboard')
GH_HEADERS = {'Authorization': f'token {GH_TOKEN}', 'User-Agent': 'gh-actions-ops/1.0'}
OKPOS_ID = os.environ['OKPOS_ID']
OKPOS_PW = os.environ['OKPOS_PW']
TOSS_ID  = os.environ['TOSS_ID']
TOSS_PW  = os.environ['TOSS_PW']

# OKPOS SHOP_CD → 매장키 (수원은 시트에서 처리)
SHOP_MAP = {
    'V00555': '하남', 'V09651': '가산',
    'V67293': '다산', 'V67295': '다산',
    'V68581': '수원',
    'V70577': '광주', 'V70585': '광주',
}

# 매장별 Google Sheets 정보
SHEET_IDS = {
    '하남': '1elj1WazP29hobZ6l1sLTy77eo2kNCnMr2tEdoRCxaC0',
    '가산': '1lVkO-6PzbegxlRqPwNRMeFt_5dsLuSztzhevpqv650k',
    '다산': '1jQemSMvxiWi9eVonqQdxJh542EBftt-tsI4VNegvISw',
    '광주': '1xC0fKGOGiK2ABw4G6zkjFl7vMpmSIq5BCH1bVVpdCuQ',
    '수원': '1niXSDHhFgz9KLrnrv8pDkE5Uf1CiZERlnSnLRSbNT8w',
    '운정': '1GgfvL9kRjU9OACDZYr3jKdDEXpX32ebzdeZIqIBsZYw',
}

# 매장별 매출탭 staff 컬럼 (0-indexed) — 데이터 매칭으로 검증된 값
STAFF_COL = {
    '가산': 24,  # Y
    '하남': 24,  # Y
    '수원': 22,  # W
    '광주': 34,  # AI
    '다산': 31,  # AF
    '운정': 27,  # AB
}

# 토스플레이스
TOSS_MERCHANT = 304265
TOSS_BASE = 'https://api-public.tossplace.com'


def log(*args):
    line = '[' + datetime.utcnow().strftime('%H:%M:%S') + 'Z] ' + ' '.join(str(a) for a in args)
    print(line, flush=True)


def parse_num(v):
    if not v: return None
    s = v.replace(',', '').replace('%', '').strip()
    try:
        return float(s)
    except:
        return None


# ── OKPOS day-total 스크래핑 ──────────────────────
async def scrape_okpos(yyyy_mm):
    """월 단위 fetch (기존 호환). 내부적으로 scrape_okpos_range 호출."""
    y, m = yyyy_mm.split('-')
    days_in_month = (date(int(y), int(m) % 12 + 1, 1) - timedelta(days=1)).day if int(m) < 12 else 31
    today = date.today()
    last_day = today.day if today.year == int(y) and today.month == int(m) else days_in_month
    start = f'{y}-{m}-01'
    end   = f'{y}-{m}-{last_day:02d}'
    return await scrape_okpos_range(start, end, label=yyyy_mm)


# ── 순수 HTTP 로그인 (실시간 함수 ops-live.js 와 동일 시퀀스) ──
OK_BASE = 'https://okasp.okpos.co.kr'
_CSRF_U = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _find_csrf(html):
    m = re.search(rf"name=['\"]({_CSRF_U})['\"]\s+value=['\"]({_CSRF_U})['\"]", html, re.I)
    if m: return m.group(1), m.group(2)
    m = re.search(rf"value=['\"]({_CSRF_U})['\"]\s+name=['\"]({_CSRF_U})['\"]", html, re.I)
    if m: return m.group(2), m.group(1)
    return None, None


def _okpos_http_login():
    """브라우저 없이 순수 HTTP 로그인 + 일별총매출(day_total010) 폼 워밍업.
    반환: (requests.Session, (csrf_key, csrf_val))."""
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Trident/7.0; rv:11.0) like Gecko',
                      'Accept-Language': 'ko-KR'})
    ref = {'Referer': OK_BASE + '/login/login_form.jsp'}
    ck, cv = _find_csrf(s.get(OK_BASE + '/login/login_form.jsp', timeout=30).text)
    if not ck: raise RuntimeError('OKPOS 로그인 폼 CSRF 파싱 실패')
    cred = [('AutoFg', 'W'), ('user_id', OKPOS_ID), ('user_pwd', OKPOS_PW)]
    s.post(OK_BASE + '/login/login_check.jsp', data=[(ck, cv)] + cred, headers=ref, timeout=30)
    s.post(OK_BASE + '/login/login_check_action.jsp', data=[(ck, cv), (ck, cv)] + cred, headers=ref, timeout=30)
    sk = sv = None
    for p in ['/login/top_frame.jsp', '/login/top_page.jsp', '/login/history.jsp', '/login/showitem.jsp']:
        a, b = _find_csrf(s.get(OK_BASE + p, timeout=30).text)
        if a and not sk: sk, sv = a, b
    if not sk: raise RuntimeError('OKPOS 세션 CSRF 파싱 실패 (로그인 실패 가능)')
    s.get(OK_BASE + '/sale/day/day_jump010.jsp', timeout=30)
    s.get(OK_BASE + '/sale/day/day_total010.jsp',
          headers={'Referer': OK_BASE + '/sale/day/day_jump010.jsp'}, timeout=30)
    return s, (sk, sv)


async def scrape_okpos_range(start, end, label=''):
    """일자 범위로 OK포스 fetch (순수 HTTP). start='YYYY-MM-DD', end='YYYY-MM-DD'.
    day_total010 + chkRowShow=Y → 날짜별×매장별 행. 1년치 한 번에 받을 때도 사용(backfill)."""
    log(f'OKPOS scraping(HTTP) {label or start+"~"+end}: {start} ~ {end}')
    s, (sk, sv) = _okpos_http_login()
    body = [
        (sk, sv),
        ('S_CONTROLLER', 'sale.day.day_total010'), ('S_METHOD', 'search'), ('SHEETSEQ', '1'),
        ('date1_1', start), ('date1_2', end), ('date_period1', '1'),
        ('ss_SHOP_CD', ''), ('ss_SHOP_NM', '전체'), ('ss_SHOP_INFO', '[]'),
        ('ss_PAGE_NO1', '1'), ('chkRowShow', 'Y'),
    ]
    r = s.post(OK_BASE + '/sale/day/ddd.htmlSheetAction', data=body,
               headers={'Referer': OK_BASE + '/sale/day/day_total010.jsp',
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
               timeout=120).json()
    if (r.get('Result', {}) or {}).get('Code', 0) < 0:
        raise RuntimeError((r.get('Result', {}) or {}).get('Message', 'OKPOS day_total 오류'))
    data = r.get('Data', [])
    log(f'  records: {len(data)}')
    return data


def apply_okpos(records, existing):
    by_date_store = {}
    for row in records:
        store = SHOP_MAP.get(row['SHOP_CD'])
        if not store: continue  # 모든 매장 적재 (수원은 시트 fallback용으로 by_date_store에 보존)
        raw = row['SALE_DATE']
        dt = f'{raw[:4]}-{raw[4:6]}-{raw[6:8]}'
        gross = int(row.get('DCM_SALE_AMT', 0) or 0)
        point = int(row.get('CST_POINT_AMT', 0) or 0)
        sales = gross - point
        receipts = int(row.get('TOT_SALE_CNT', 0) or 0)
        by_date_store.setdefault(dt, {}).setdefault(store, {'sales':0, 'receipts':0})
        by_date_store[dt][store]['sales']    += sales
        by_date_store[dt][store]['receipts'] += receipts

    updated = 0
    for store, entries in existing.items():
        if store in ('수원', '운정'): continue
        for entry in entries:
            ds = by_date_store.get(entry['date'], {}).get(store)
            if not ds: continue
            if ds['sales'] > 0:
                # invalid receipts 가드: =1 + 매출>20만은 영수증 시스템 미작동 시기
                rec = ds['receipts']
                if rec == 1 and ds['sales'] > 200_000:
                    rec = None
                entry['sales']    = ds['sales']
                entry['receipts'] = rec
                entry['per_receipt'] = (ds['sales'] // rec) if rec else None
                if entry.get('staff') and entry['staff'] > 0:
                    entry['productivity'] = ds['sales'] // entry['staff']
                updated += 1
    log(f'  OKPOS updated: {updated}건')
    return by_date_store


# ── TOSS 운정 ─────────────────────────────────────
def scrape_toss(yyyy_mm):
    """HTTP API 직접 호출 — 본사(DASHBOARD_USER) email 로그인 + dashboard-workspace-id 헤더.
    옛 playwright 방식은 매장(PLACE_USER) phone ID 폐기로 작동 안 함.
    """
    log('TOSS scraping:', yyyy_mm)
    # 1) 로그인
    body = {'id': TOSS_ID, 'password': TOSS_PW, 'loginType': 'DASHBOARD_USER'}
    req = urllib.request.Request(
        f'{TOSS_BASE}/api-public/dashboard/v2/auth/login',
        data=json.dumps(body).encode(),
        headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0',
                 'Origin':'https://dashboard.tossplace.com','Accept':'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    if data.get('resultType') != 'SUCCESS':
        raise RuntimeError(f"TOSS 로그인 실패: {data.get('error')}")
    token = data['success']['accessToken']
    # 2) workspace id
    req = urllib.request.Request(
        f'{TOSS_BASE}/api-public/dashboard/v1/workspaces?type=BRAND',
        headers={'Authorization':f'Bearer {token}','User-Agent':'Mozilla/5.0',
                 'Origin':'https://dashboard.tossplace.com','Accept':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        items = ((json.loads(r.read()).get('success') or {}).get('items') or [])
    if not items:
        raise RuntimeError("TOSS workspace(type=BRAND) 없음")
    wsid = items[0]['id']
    headers = {
        'Authorization': f'Bearer {token}',
        'dashboard-workspace-id': str(wsid),
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0',
        'Origin': 'https://dashboard.tossplace.com',
        'Accept': 'application/json',
    }
    # 3) period/daily
    y, m = yyyy_mm.split('-')
    days_in_month = (date(int(y), int(m) % 12 + 1, 1) - timedelta(days=1)).day if int(m) < 12 else 31
    today = date.today()
    last_day = today.day if today.year == int(y) and today.month == int(m) else days_in_month
    body = {
        'merchantIds': [TOSS_MERCHANT],
        'startDate': f'{y}-{m}-01',
        'endDate': f'{y}-{m}-{last_day:02d}',
        'includeMerchantAsColumn': False,
    }
    req = urllib.request.Request(
        f'{TOSS_BASE}/dashboard/v1/reports/period/daily',
        data=json.dumps(body).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    if result.get('resultType') != 'SUCCESS':
        raise RuntimeError(f'TOSS API 오류: {result.get("error")}')
    records = []
    for r in result.get('success', {}).get('report', []):
        net = r.get('content', {}).get('sales', {}).get('netSalesAmount', 0) or 0
        receipts = r.get('content', {}).get('sales', {}).get('paymentCount', 0) or 0
        # 운영 대시보드 기준: OK포스 5매장 raw가 "VAT 포함 + 할인 제외"이므로
        # 운정도 토스 netSalesAmount(VAT 포함, 할인 제외) 그대로 저장해 통일.
        # 대시보드의 VAT 토글로 표시 단계에서 ÷1.1 가능.
        sales = int(net)
        if sales > 0:
            records.append({'date': r['date'], 'sales': sales, 'receipts': receipts})
    log(f'  TOSS records: {len(records)}')
    return records


def apply_toss(records, existing):
    updated = 0
    by_date = {r['date']: r for r in records}
    for entry in existing.get('운정', []):
        rec = by_date.get(entry['date'])
        if not rec: continue
        entry['sales']    = rec['sales']
        entry['receipts'] = rec['receipts']
        entry['per_receipt'] = (rec['sales'] // rec['receipts']) if rec['receipts'] else None
        if entry.get('staff') and entry['staff'] > 0:
            entry['productivity'] = rec['sales'] // entry['staff']
        updated += 1
    log(f'  TOSS updated: {updated}건')


# ── Google Sheets ─────────────────────────────────
def fetch_sheet_csv(sheet_id, tab):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(tab)}'
    return urllib.request.urlopen(url, timeout=30).read().decode('utf-8', 'replace')


def find_col(rows, kws, scan_rows=15):
    """헤더 행에서 키워드 찾기"""
    if isinstance(kws, str): kws = [kws]
    for r in range(min(scan_rows, len(rows))):
        for c in range(len(rows[r])):
            cell = rows[r][c].replace(' ', '').replace('　','')
            for kw in kws:
                k = kw.replace(' ', '')
                if k in cell:
                    return c
    return None


def patch_store_from_sheet(store, yyyy_mm, existing, okpos_by_date):
    """매장별 시트에서 staff/target/(수원·운정의 경우 sales/receipts) 패치"""
    sid = SHEET_IDS[store]
    y, m = yyyy_mm.split('-')
    tab = f'{y[2:]}.{int(m)}'  # 26.4

    try:
        csv_text = fetch_sheet_csv(sid, tab)
    except Exception as e:
        log(f'  [{store}] 시트 fetch 실패: {e}')
        return

    rows = list(csv.reader(csv_text.splitlines()))
    sales_col    = find_col(rows, ['매출현황', '*POS+KIOSK', 'POS+KIOSK'])
    receipts_col = find_col(rows, ['영수건수'])
    target_col   = find_col(rows, ['목표매출'])
    staff_col    = STAFF_COL.get(store)  # 매장별 하드코딩 (gviz 컬럼 인덱스)

    # 수원 시트는 영역 B (일자 1~31 두 번째 영역)에 영수건수 있음 — col 3
    suwon_receipts_by_day = {}
    if store == '수원':
        seen_one = 0
        for r in rows:
            if not r or not r[0].strip().isdigit(): continue
            d = int(r[0])
            if d < 1 or d > 31 or str(d) != r[0].strip(): continue
            if d == 1: seen_one += 1
            if seen_one < 2: continue  # 첫 영역(영역 A) 통과
            if len(r) > 3:
                v = parse_num(r[3])
                if v is not None: suwon_receipts_by_day[d] = v

    # 일자별 시트 데이터
    sheet_by_date = {}
    seen = set()
    for r in rows:
        if not r or not r[0].strip().isdigit(): continue
        d = int(r[0])
        if d < 1 or d > 31 or str(d) != r[0].strip() or d in seen: continue
        seen.add(d)
        dt = f'{y}-{m}-{d:02d}'
        # 수원: 영수는 영역 B에서, 그 외 기본 로직
        if store == '수원':
            rec_val = suwon_receipts_by_day.get(d)
        else:
            rec_val = parse_num(r[receipts_col]) if receipts_col is not None and receipts_col < len(r) else None
        sheet_by_date[dt] = {
            'sales':    parse_num(r[sales_col])    if sales_col    is not None and sales_col    < len(r) else None,
            'receipts': rec_val,
            'staff':    parse_num(r[staff_col])    if staff_col    is not None and staff_col    < len(r) else None,
            'target':   parse_num(r[target_col])   if target_col   is not None and target_col   < len(r) else None,
        }

    # 근무인원: 스케줄 탭에서 직접 카운트(팀별 합산, 매장별 STAFF_COL보다 정확).
    # 파싱 실패/해당일 없으면 기존 시트 STAFF_COL로 폴백 — 안전.
    sched_staff = {}
    try:
        from schedule_parser import fetch_schedule
        sched = fetch_schedule(store, int(y), int(m))
        sched_staff = {d: v['count'] for d, v in sched.items() if v.get('count')}
        if sched_staff:
            log(f'  [{store}] 스케줄 근무인원 {len(sched_staff)}일 ({min(sched_staff.values())}~{max(sched_staff.values())}명)')
    except Exception as e:
        log(f'  [{store}] 스케줄 파싱 실패(시트 STAFF_COL 폴백): {e}')

    updated = 0
    for entry in existing.get(store, []):
        sd = sheet_by_date.get(entry['date'], {})
        # 매장별 우선순위
        if store == '수원':
            # 매출은 OK POS 우선 (시트와 source 차이 회피)
            okp = okpos_by_date.get(entry['date'], {}).get('수원')
            if okp and okp['sales'] > 0:
                entry['sales'] = okp['sales']
            elif sd.get('sales'):
                entry['sales'] = int(sd['sales'])
            # 영수건수는 시트 우선 (OK POS 수원은 백화점 일괄 결제로 영수가 0/1)
            if sd.get('receipts') is not None: entry['receipts'] = int(sd['receipts'])
        elif store == '운정':
            # TOSS가 우선이지만 시트 매출이 있으면 시트 사용 (사람 검증 우선)
            if sd.get('sales'): entry['sales'] = int(sd['sales'])
            if sd.get('receipts') is not None: entry['receipts'] = int(sd['receipts'])
        # 기타 매장(하남/가산/다산/광주): 매출/영수는 OKPOS 유지

        # invalid receipts 가드: =1 + 매출>20만 → None (영수증 시스템 미작동 시기)
        if entry.get('receipts') == 1 and (entry.get('sales') or 0) > 200_000:
            entry['receipts'] = None

        # 목표(target)는 compute_targets.py가 자동계산 — 시트값 미사용
        # 근무인원: 스케줄 카운트 우선, 없으면 시트 STAFF_COL 폴백
        day = int(entry['date'].split('-')[2])
        if day in sched_staff:
            entry['staff'] = sched_staff[day]
        elif sd.get('staff') is not None:
            entry['staff'] = int(sd['staff'])
        if entry.get('sales') and entry.get('receipts'):
            entry['per_receipt'] = entry['sales'] // entry['receipts']
        else:
            entry['per_receipt'] = None
        if entry.get('sales') and entry.get('staff'):
            entry['productivity'] = entry['sales'] // entry['staff']
        if entry.get('sales'): updated += 1

    log(f'  [{store}] 시트 패치: {updated}일 (시트={len(sheet_by_date)}일)')


# ── 메인 ──────────────────────────────────────────
async def main():
    today = date.today()
    yyyy_mm = today.strftime('%Y-%m')
    log('=== 운영 데이터 동기화 시작 ===', yyyy_mm)

    # 기존 ops_data 로드 (워크플로우의 checkout이 이미 받아옴 — 로컬 파일에서)
    json_path = f'ops_data/{yyyy_mm}.json'
    EXPECTED_STORES = ['가산','다산','수원','하남','광주','운정']
    needs_init = not os.path.exists(json_path)
    if not needs_init:
        with open(json_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        if all(len(existing.get(s, [])) == 0 for s in EXPECTED_STORES):
            needs_init = True
            log(f'{json_path} 모든 매장 entry 비어있음 — 재초기화')
    if needs_init:
        import calendar as _cal
        _y, _m = map(int, yyyy_mm.split('-'))
        _last = _cal.monthrange(_y, _m)[1]
        log(f'{json_path} 새 월 파일 초기화 (1~{_last}일 빈 entry)')
        existing = {s: [{'date': f'{_y:04d}-{_m:02d}-{d:02d}'} for d in range(1, _last + 1)]
                    for s in EXPECTED_STORES}

    # raw 저장 버킷 — OK포스 5매장 + 운정(TOSS) 모두 교차검증용으로 저장
    raw_by_store = {s: [] for s in EXPECTED_STORES}

    # 1) OKPOS
    okpos_by_date = {}
    try:
        records = await scrape_okpos(yyyy_mm)
        okpos_by_date = apply_okpos(records, existing)
        for dt in sorted(okpos_by_date.keys()):
            for store in EXPECTED_STORES:
                rec = okpos_by_date.get(dt, {}).get(store)
                if rec:
                    raw_by_store[store].append({
                        'date': dt,
                        'sales': rec.get('sales', 0),
                        'receipts': rec.get('receipts', 0),
                    })
    except Exception as e:
        log(f'OKPOS 실패: {e}')

    # 2) TOSS 운정
    try:
        toss_records = scrape_toss(yyyy_mm)
        apply_toss(toss_records, existing)
        # 운정 토스 raw도 교차검증용으로 저장 (VAT 포함 + 할인 제외 — OK포스 raw와 동일 기준)
        raw_by_store['운정'] = [
            {'date': r['date'], 'sales': r['sales'], 'receipts': r['receipts']}
            for r in toss_records
        ]
    except Exception as e:
        log(f'TOSS 실패: {e}')

    # OK포스 + 운정 raw 저장 (교차 검증용 — 보정 전 원본)
    try:
        raw_dir = 'ops_data/raw_okpos'
        os.makedirs(raw_dir, exist_ok=True)
        raw_path = f'{raw_dir}/{yyyy_mm}.json'
        with open(raw_path, 'w', encoding='utf-8') as f:
            json.dump(raw_by_store, f, ensure_ascii=False, indent=2)
        log(f'  raw 저장: {raw_path} ({sum(len(v) for v in raw_by_store.values())}건)')
    except Exception as e:
        log(f'raw 저장 실패: {e}')

    # 3) 6개 시트
    for store in SHEET_IDS:
        try:
            patch_store_from_sheet(store, yyyy_mm, existing, okpos_by_date)
        except Exception as e:
            log(f'[{store}] 시트 실패: {e}')

    # 누락 감지 — 모든 매장 매장의 최근 7일 sales 체크
    EXPECTED_STORES = {'가산','다산','수원','하남','광주','운정'}
    today_str = today.isoformat()
    week_ago = (today - timedelta(days=7)).isoformat()
    missing = []
    for store in EXPECTED_STORES:
        for entry in existing.get(store, []):
            if not (week_ago <= entry['date'] <= today_str): continue
            if not entry.get('sales'):
                missing.append((store, entry['date']))
    if missing:
        log(f'[누락 경고] {len(missing)}건 — 다음 cron에서 재수집됨')
        for s, d in missing[:10]: log(f'  - {s} {d}')

    # 저장
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    log(f'저장: {json_path}')

    log('=== 완료 (build.js + commit은 워크플로우 다음 step) ===')


if __name__ == '__main__':
    asyncio.run(main())
