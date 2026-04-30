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
from playwright.async_api import async_playwright

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
    log('OKPOS scraping:', yyyy_mm)
    y, m = yyyy_mm.split('-')
    days_in_month = (date(int(y), int(m) % 12 + 1, 1) - timedelta(days=1)).day if int(m) < 12 else 31
    today = date.today()
    last_day = today.day if today.year == int(y) and today.month == int(m) else days_in_month
    start = f'{y}-{m}-01'
    end   = f'{y}-{m}-{last_day:02d}'

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--disable-popup-blocking'])
        try:
            page = await browser.new_page()
            await page.goto('https://asp.netusys.com/login/login_form.jsp', wait_until='networkidle', timeout=30000)
            await page.fill('#user_id', OKPOS_ID)
            await page.fill('#user_pwd', OKPOS_PW)
            await page.press('#user_pwd', 'Enter')
            await asyncio.sleep(3)
            # 패스워드 변경 팝업 닫기
            try:
                pf = next((f for f in page.frames if 'passwd' in f.url), None)
                if pf:
                    await pf.evaluate("""() => {
                        const b = [...document.querySelectorAll('button,input,a,td,span')]
                            .find(e => /닫기|취소|나중/i.test(e.textContent + (e.value||'')));
                        if (b) b.click();
                    }""")
                    await asyncio.sleep(0.5)
            except: pass

            # day_jump010으로 이동
            mf = next((f for f in page.frames if 'top_page' in f.url or f.name == 'MainFrm'), None)
            if mf:
                await mf.goto('https://okasp.okpos.co.kr/sale/day/day_jump010.jsp', wait_until='load', timeout=20000)
                await asyncio.sleep(2)
            df = next((f for f in page.frames if 'day_total010' in f.url), None)
            if not df:
                raise RuntimeError('day_total 프레임 못 찾음')

            raw_data = []
            async def on_route(route):
                u = route.request.url
                if any(k in u for k in ('day','sale','list','Search')):
                    resp = await route.fetch()
                    text = await resp.text()
                    if 'SHOP_CD' in text and 'SALE_DATE' in text and 'DCM_SALE_AMT' in text:
                        raw_data.append(text)
                    await route.fulfill(response=resp)
                else:
                    await route.continue_()
            await page.route('**/*', on_route)

            await df.evaluate(f"""({{s, e}}) => {{
                document.querySelector('#date1_1').value = s;
                document.querySelector('#date1_2').value = e;
                document.querySelector('#ss_SHOP_CD').value = '';
                document.querySelector('#ss_SHOP_NM').value = '전체';
                if (document.querySelector('#ss_SHOP_INFO')) document.querySelector('#ss_SHOP_INFO').value = '[]';
                const chk = document.querySelector('#chkRowShow');
                if (chk && !chk.checked) chk.click();
                fnSearch();
            }}""", {'s': start, 'e': end})
            await asyncio.sleep(5)
            await page.unroute('**/*', on_route)

            if not raw_data:
                raise RuntimeError('OKPOS AJAX 응답 없음')
            data = json.loads(raw_data[-1])
            log(f'  records: {len(data["Data"])}')
            return data['Data']
        finally:
            await browser.close()


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
                entry['sales']    = ds['sales']
                entry['receipts'] = ds['receipts']
                entry['per_receipt'] = (ds['sales'] // ds['receipts']) if ds['receipts'] else None
                if entry.get('staff') and entry['staff'] > 0:
                    entry['productivity'] = ds['sales'] // entry['staff']
                updated += 1
    log(f'  OKPOS updated: {updated}건')
    return by_date_store


# ── TOSS 운정 ─────────────────────────────────────
async def scrape_toss(yyyy_mm):
    log('TOSS scraping:', yyyy_mm)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            captured = {}
            async def on_req(req):
                if 'api-public.tossplace.com' in req.url:
                    h = await req.all_headers()
                    auth = h.get('authorization')
                    wpid = h.get('toss-workplace-id')
                    if auth and 'Bearer' in auth and wpid:
                        captured['headers'] = {
                            'Authorization': auth if auth.startswith('Bearer') else 'Bearer '+auth,
                            'toss-workplace-id': wpid,
                            'toss-place-user-id': h.get('toss-place-user-id', ''),
                            'Content-Type': 'application/json',
                            'User-Agent': h.get('user-agent', 'Mozilla/5.0'),
                        }
            page.on('request', on_req)
            await page.goto('https://dashboard.tossplace.com/login', wait_until='networkidle', timeout=30000)
            await page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
            await page.fill('input[autocomplete="username"]', TOSS_ID)
            await page.fill('input[autocomplete="current-password"]', TOSS_PW)
            await page.click('button[type="submit"]')
            for _ in range(30):
                await asyncio.sleep(1)
                if 'headers' in captured: break
            if 'headers' not in captured:
                try:
                    await page.goto('https://dashboard.tossplace.com/sales-detail/period', wait_until='networkidle', timeout=15000)
                    await asyncio.sleep(3)
                except: pass
            if 'headers' not in captured:
                raise RuntimeError('TOSS 헤더 캡쳐 실패')
            headers = captured['headers']

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
                sales = r.get('content', {}).get('sales', {}).get('netSalesAmount', 0) or 0
                receipts = r.get('content', {}).get('sales', {}).get('paymentCount', 0) or 0
                if sales > 0:
                    records.append({'date': r['date'], 'sales': sales, 'receipts': receipts})
            log(f'  TOSS records: {len(records)}')
            return records
        finally:
            await browser.close()


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

    # 일자별 시트 데이터
    sheet_by_date = {}
    seen = set()
    for r in rows:
        if not r or not r[0].strip().isdigit(): continue
        d = int(r[0])
        if d < 1 or d > 31 or str(d) != r[0].strip() or d in seen: continue
        seen.add(d)
        dt = f'{y}-{m}-{d:02d}'
        sheet_by_date[dt] = {
            'sales':    parse_num(r[sales_col])    if sales_col    is not None and sales_col    < len(r) else None,
            'receipts': parse_num(r[receipts_col]) if receipts_col is not None and receipts_col < len(r) else None,
            'staff':    parse_num(r[staff_col])    if staff_col    is not None and staff_col    < len(r) else None,
            'target':   parse_num(r[target_col])   if target_col   is not None and target_col   < len(r) else None,
        }

    updated = 0
    for entry in existing.get(store, []):
        sd = sheet_by_date.get(entry['date'], {})
        # 매장별 우선순위
        if store == '수원':
            if sd.get('sales'): entry['sales'] = int(sd['sales'])
            elif okpos_by_date.get(entry['date'], {}).get('수원'):
                entry['sales'] = okpos_by_date[entry['date']]['수원']['sales']
            if sd.get('receipts') is not None: entry['receipts'] = int(sd['receipts'])
        elif store == '운정':
            # TOSS가 우선이지만 시트 매출이 있으면 시트 사용 (사람 검증 우선)
            if sd.get('sales'): entry['sales'] = int(sd['sales'])
            if sd.get('receipts') is not None: entry['receipts'] = int(sd['receipts'])
        # 기타 매장(하남/가산/다산/광주): 매출/영수는 OKPOS 유지

        if sd.get('target') is not None: entry['target'] = int(sd['target'])
        if sd.get('staff')  is not None: entry['staff']  = int(sd['staff'])
        if entry.get('sales') and entry.get('receipts'):
            entry['per_receipt'] = entry['sales'] // entry['receipts']
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
    if not os.path.exists(json_path):
        log(f'ERROR: {json_path} 없음')
        sys.exit(1)
    with open(json_path, 'r', encoding='utf-8') as f:
        existing = json.load(f)

    # 1) OKPOS
    okpos_by_date = {}
    try:
        records = await scrape_okpos(yyyy_mm)
        okpos_by_date = apply_okpos(records, existing)
    except Exception as e:
        log(f'OKPOS 실패: {e}')

    # 2) TOSS 운정
    try:
        toss_records = await scrape_toss(yyyy_mm)
        apply_toss(toss_records, existing)
    except Exception as e:
        log(f'TOSS 실패: {e}')

    # 3) 6개 시트
    for store in SHEET_IDS:
        try:
            patch_store_from_sheet(store, yyyy_mm, existing, okpos_by_date)
        except Exception as e:
            log(f'[{store}] 시트 실패: {e}')

    # 저장
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    log(f'저장: {json_path}')

    log('=== 완료 (build.js + commit은 워크플로우 다음 step) ===')


if __name__ == '__main__':
    asyncio.run(main())
