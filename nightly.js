/**
 * 인크커피 야간 자동 데이터 수집
 * 실행: node nightly.js [YYYY-MM]
 *
 * 수행 작업:
 *  1. OKPOS 일자별 매출 스크래핑
 *  2. 토스플레이스 스크래핑 (운정 백업)
 *  3. 전 지점 구글시트 패치 (당월 탭 → 매출/영수/근무인원)
 *  4. 빌드 + GitHub Pages 배포
 */

const { chromium } = require('C:/Users/zoids/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright-core');
const https = require('https');
const fs    = require('fs');
const path  = require('path');

const BASE     = 'https://okasp.okpos.co.kr';
const DATA_DIR = path.join(__dirname, 'ops_data');
const LOG_DIR  = path.join(__dirname, 'logs');
const GID_CACHE_PATH = path.join(DATA_DIR, 'sheet_gids.json');
const ID = 'hqrd';
const PW = '01526';

// OKPOS SHOP_CD → 매장키
const SHOP_MAP = {
  'V00555': '하남', 'V09651': '가산',
  'V67293': '다산', 'V67295': '다산',
  'V68581': '수원',
  'V70577': '광주', 'V70585': '광주',
};

// 지점별 구글 스프레드시트 ID
const SHEET_IDS = {
  '하남': '1elj1WazP29hobZ6l1sLTy77eo2kNCnMr2tEdoRCxaC0',
  '가산': '1lVkO-6PzbegxlRqPwNRMeFt_5dsLuSztzhevpqv650k',
  '다산': '1jQemSMvxiWi9eVonqQdxJh542EBftt-tsI4VNegvISw',
  '광주': '1xC0fKGOGiK2ABw4G6zkjFl7vMpmSIq5BCH1bVVpdCuQ',
  '수원': '1niXSDHhFgz9KLrnrv8pDkE5Uf1CiZERlnSnLRSbNT8w',
  '운정': '1GgfvL9kRjU9OACDZYr3jKdDEXpX32ebzdeZIqIBsZYw',
};

// 토스플레이스 (운정)
const TOSS_ID       = '010-5723-2858';
const TOSS_PW       = 'inkkorea1205!';
const TOSS_MERCHANT = 304265;
const TOSS_WORKPLACE= 296;
const TOSS_USER_ID  = 249704;

// ── 로그 ─────────────────────────────────────────────────────────────────────
if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR);
const logFile = path.join(LOG_DIR, new Date().toISOString().slice(0,10) + '.log');
function log(...args) {
  const line = '[' + new Date().toISOString().slice(11,19) + '] ' + args.join(' ');
  console.log(line);
  fs.appendFileSync(logFile, line + '\n');
}

// ── 날짜 유틸 ─────────────────────────────────────────────────────────────────
function getYYYYMM() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0');
}
function getDateRange(yyyyMM) {
  const [y, m] = yyyyMM.split('-');
  const daysInMonth = new Date(+y, +m, 0).getDate();
  const today = new Date();
  const lastDay = (today.getFullYear() === +y && today.getMonth()+1 === +m)
    ? String(today.getDate()).padStart(2,'0')
    : String(daysInMonth).padStart(2,'0');
  return { start: `${y}-${m}-01`, end: `${y}-${m}-${lastDay}` };
}

// ── CSV fetch / parse ────────────────────────────────────────────────────────
function fetchCsv(sheetId, gid) {
  return new Promise((resolve, reject) => {
    const url = `https://docs.google.com/spreadsheets/d/${sheetId}/export?format=csv&gid=${gid}`;
    const go = u => https.get(u, { headers: { 'User-Agent': 'Mozilla/5.0' } }, r => {
      if ([301,302,307,308].includes(r.statusCode) && r.headers.location) { go(r.headers.location); return; }
      let d = ''; r.on('data', c => d += c); r.on('end', () => resolve(d));
    }).on('error', reject);
    go(url);
  });
}

function parseCsv(text) {
  const rows = []; let lines = [], buf = '', inQ = false;
  for (const ch of text.replace(/\r/g, '')) {
    if (ch === '"') { inQ = !inQ; buf += ch; }
    else if (ch === '\n' && !inQ) { lines.push(buf); buf = ''; }
    else buf += ch;
  }
  if (buf) lines.push(buf);
  for (const line of lines) {
    const row = []; let cur = '', q = false;
    for (const ch of line) { if (ch === '"') q = !q; else if (ch === ',' && !q) { row.push(cur.trim()); cur = ''; } else cur += ch; }
    row.push(cur.trim()); rows.push(row);
  }
  return rows;
}

function findCol(rows, kws, scanRows = 15) {
  const kwArr = Array.isArray(kws) ? kws : [kws];
  for (let r = 0; r < Math.min(scanRows, rows.length); r++)
    for (let c = 0; c < rows[r].length; c++) {
      const cell = rows[r][c].replace(/\s+/g, '');
      for (const kw of kwArr)
        if (cell.includes(kw.replace(/\s+/g, ''))) return { row: r, col: c };
    }
  return null;
}

function parseNum(s) {
  if (!s || !s.trim()) return null;
  const n = parseFloat(s.replace(/[",\s%]/g, ''));
  return isNaN(n) ? null : n;
}

// ── 1. 구글시트 GID 탐색 + 캐시 ──────────────────────────────────────────────
// 탭명 패턴: YY.M (예: 2026-04 → "26.4")
async function discoverSheetGids(yyyyMM) {
  const [y, m] = yyyyMM.split('-');
  const tabName = y.slice(2) + '.' + parseInt(m);
  log(`시트 GID 탐색 시작 (탭명: ${tabName})`);

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Users/zoids/AppData/Local/ms-playwright/chromium-1212/chrome-win64/chrome.exe',
  });

  const gids = {};
  for (const [store, sheetId] of Object.entries(SHEET_IDS)) {
    try {
      const page = await browser.newPage();
      await page.setViewportSize({ width: 1600, height: 900 });
      await page.goto(`https://docs.google.com/spreadsheets/d/${sheetId}/edit`, {
        waitUntil: 'domcontentloaded', timeout: 30000
      });
      await page.waitForTimeout(3500);
      await page.locator('.docs-sheet-tab', { hasText: tabName }).first().click({ timeout: 8000 });
      await page.waitForTimeout(1500);
      const gid = await page.evaluate(() => window.location.hash.match(/gid=(\d+)/)?.[1] || '');
      if (gid) { gids[store] = gid; log(`  ${store}: GID=${gid}`); }
      else      log(`  [경고] ${store}: ${tabName} 탭 GID 획득 실패`);
      await page.close();
    } catch(e) {
      log(`  [경고] ${store}: ${e.message.slice(0, 60)}`);
    }
  }
  await browser.close();
  return gids;
}

async function getSheetGids(yyyyMM) {
  let cache = {};
  if (fs.existsSync(GID_CACHE_PATH))
    cache = JSON.parse(fs.readFileSync(GID_CACHE_PATH, 'utf8'));

  const cached = cache[yyyyMM] || {};
  const missing = Object.keys(SHEET_IDS).filter(s => !cached[s]);

  if (missing.length === 0) {
    log('시트 GID 캐시 사용:', yyyyMM);
    return cached;
  }

  log(`시트 GID 미캐시 (${missing.join(', ')}) → Playwright 탐색`);
  const discovered = await discoverSheetGids(yyyyMM);
  cache[yyyyMM] = { ...cached, ...discovered };
  fs.writeFileSync(GID_CACHE_PATH, JSON.stringify(cache, null, 2), 'utf8');
  return cache[yyyyMM];
}

// ── 2. OKPOS 스크래핑 ─────────────────────────────────────────────────────────
async function scrapeOkpos(yyyyMM) {
  log('OKPOS 스크래핑 시작:', yyyyMM);
  const { start, end } = getDateRange(yyyyMM);

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Users/zoids/AppData/Local/ms-playwright/chromium-1212/chrome-win64/chrome.exe',
  });

  try {
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1400, height: 900 });

    await page.goto('https://asp.netusys.com/login/login_form.jsp', { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('#user_id', ID);
    await page.fill('#user_pwd', PW);
    await page.press('#user_pwd', 'Enter');
    await page.waitForTimeout(3000);

    try {
      const pf = page.frames().find(f => f.url().includes('passwd'));
      if (pf) await pf.evaluate(() => {
        const b = [...document.querySelectorAll('button,input,a,td,span')]
          .find(e => /닫기|취소|나중/i.test(e.textContent + e.value));
        if (b) b.click();
      });
      await page.waitForTimeout(500);
    } catch(e) {}

    const mainFrame = page.frames().find(f => f.url().includes('top_page')) || page.frames().find(f => f.name() === 'MainFrm');
    if (mainFrame) {
      await mainFrame.goto(BASE + '/sale/day/day_jump010.jsp', { waitUntil: 'load', timeout: 20000 });
      await page.waitForTimeout(2000);
    }

    const dailyFrame = page.frames().find(f => f.url().includes('day_total010'));
    if (!dailyFrame) throw new Error('day_total 프레임 없음');

    let rawData = null;
    const handler = async route => {
      const url = route.request().url();
      if (url.includes('day') || url.includes('sale') || url.includes('list') || url.includes('Search')) {
        const response = await route.fetch();
        const text = await response.text();
        if (text.includes('SHOP_CD') && text.includes('SALE_DATE') && text.includes('DCM_SALE_AMT')) rawData = text;
        await route.fulfill({ response });
      } else await route.continue();
    };
    await page.route('**/*', handler);

    await dailyFrame.evaluate(({ s, e }) => {
      document.querySelector('#date1_1').value = s;
      document.querySelector('#date1_2').value = e;
      document.querySelector('#ss_SHOP_CD').value = '';
      document.querySelector('#ss_SHOP_NM').value = '전체';
      if (document.querySelector('#ss_SHOP_INFO')) document.querySelector('#ss_SHOP_INFO').value = '[]';
      const chk = document.querySelector('#chkRowShow');
      if (chk && !chk.checked) chk.click();
      fnSearch();
    }, { s: start, e: end });

    await page.waitForTimeout(5000);
    await page.unroute('**/*', handler);

    if (!rawData) throw new Error('AJAX 응답 없음');
    const data = JSON.parse(rawData);
    log(`  OKPOS 레코드: ${data.Data.length}개`);
    return data.Data;
  } finally {
    await browser.close();
  }
}

function applyOkposData(records, existing) {
  const byDateStore = {};
  for (const row of records) {
    const storeKey = SHOP_MAP[row.SHOP_CD];
    if (!storeKey || storeKey === '수원') continue; // 수원은 시트에서 처리
    const raw  = row.SALE_DATE;
    const date = `${raw.slice(0,4)}-${raw.slice(4,6)}-${raw.slice(6,8)}`;
    const gross    = parseInt(row.DCM_SALE_AMT,  10) || 0;
    const point    = parseInt(row.CST_POINT_AMT, 10) || 0;
    const sales    = gross - point;
    const receipts = parseInt(row.TOT_SALE_CNT,  10) || 0;
    if (!byDateStore[date]) byDateStore[date] = {};
    if (!byDateStore[date][storeKey]) byDateStore[date][storeKey] = { sales: 0, receipts: 0 };
    byDateStore[date][storeKey].sales    += sales;
    byDateStore[date][storeKey].receipts += receipts;
  }

  let updated = 0;
  for (const [store, entries] of Object.entries(existing)) {
    if (store === '수원' || store === '운정') continue;
    for (const entry of entries) {
      const ds = byDateStore[entry.date];
      if (!ds || !ds[store]) continue;
      const { sales, receipts } = ds[store];
      if (sales > 0) {
        entry.sales       = sales;
        entry.receipts    = receipts;
        entry.per_receipt = receipts > 0 ? Math.floor(sales / receipts) : null;
        if (entry.staff && entry.staff > 0) entry.productivity = Math.floor(sales / entry.staff);
        updated++;
      }
    }
  }
  log(`  OKPOS 업데이트: ${updated}건`);
  return byDateStore;
}

// ── 3. 토스플레이스 스크래핑 (운정 백업) ──────────────────────────────────────
async function scrapeToss(yyyyMM) {
  log('토스플레이스 스크래핑 시작:', yyyyMM);
  const { start, end } = getDateRange(yyyyMM);

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Users/zoids/AppData/Local/ms-playwright/chromium-1212/chrome-win64/chrome.exe',
  });

  try {
    const page = await browser.newPage();

    await page.goto('https://dashboard.tossplace.com/login', { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('input[type=tel]', TOSS_ID.replace(/-/g,''));
    await page.fill('input[type=password]', TOSS_PW);
    await page.click('button[type=submit]');
    await page.waitForTimeout(4000);

    let jwt = null;
    page.on('request', req => {
      const auth = req.headers()['authorization'];
      if (auth && auth.startsWith('Bearer ')) jwt = auth.slice(7);
    });

    await page.goto('https://dashboard.tossplace.com/sales-detail/period', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);

    if (!jwt) throw new Error('JWT 토큰 획득 실패');

    const result = await page.evaluate(async ({ jwt, merchantId, workplaceId, userId, start, end }) => {
      const res = await fetch('https://api-public.tossplace.com/dashboard/v1/reports/period/daily', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + jwt,
          'toss-workplace-id': String(workplaceId),
          'toss-place-user-id': String(userId),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ merchantIds: [merchantId], startDate: start, endDate: end, includeMerchantAsColumn: false }),
      });
      return res.json();
    }, { jwt, merchantId: TOSS_MERCHANT, workplaceId: TOSS_WORKPLACE, userId: TOSS_USER_ID, start, end });

    if (result.resultType !== 'SUCCESS') throw new Error('API 오류: ' + JSON.stringify(result.error));

    const records = result.success.report.map(r => ({
      date    : r.date,
      sales   : r.content.sales.netSalesAmount || 0,
      receipts: r.content.sales.paymentCount   || 0,
    })).filter(r => r.sales > 0);

    log(`  토스 레코드: ${records.length}개`);
    return records;
  } finally {
    await browser.close();
  }
}

function applyTossData(records, existing) {
  let updated = 0;
  for (const rec of records) {
    const entry = (existing['운정'] || []).find(e => e.date === rec.date);
    if (!entry) continue;
    entry.sales    = rec.sales;
    entry.receipts = rec.receipts;
    if (rec.sales && rec.receipts) entry.per_receipt = Math.floor(rec.sales / rec.receipts);
    if (entry.staff && entry.staff > 0) entry.productivity = Math.floor(rec.sales / entry.staff);
    updated++;
  }
  log(`  토스 업데이트: ${updated}건`);
}

// ── 4. 전 지점 구글시트 패치 ──────────────────────────────────────────────────
// - 수원: 시트 매출 우선, OKPOS 백업 / 영수·근무 시트
// - 운정: 시트 매출(POS+KIOSK) 우선, 토스 백업 / 영수·근무 시트
// - 기타: OKPOS 매출 유지, 근무인원만 시트에서 업데이트
async function patchStoreSheet(store, yyyyMM, existing, okposRecords, gid) {
  const sheetId = SHEET_IDS[store];
  log(`${store} 시트 패치 (gid=${gid})`);
  const [y, m] = yyyyMM.split('-');

  const csv  = await fetchCsv(sheetId, gid);
  const rows = parseCsv(csv);

  const salesCol    = findCol(rows, ['매출현황', '*POS+KIOSK', 'POS+KIOSK']);
  const receiptsCol = findCol(rows, ['영수건수']);
  const staffCol    = findCol(rows, ['당일근무인원']);
  const targetCol   = findCol(rows, ['목표매출']);

  if (!staffCol) log(`  [경고] ${store}: 당일근무인원 컬럼 없음`);

  const seen = new Set();
  const sheetByDate = {};
  rows.filter(r => {
    const n = parseInt(r[0]);
    if (isNaN(n) || n < 1 || n > 31 || String(n) !== r[0]) return false;
    if (seen.has(n)) return false;
    seen.add(n); return true;
  }).forEach(r => {
    const date = `${y}-${m}-${String(parseInt(r[0])).padStart(2,'0')}`;
    sheetByDate[date] = {
      sales    : salesCol    ? parseNum(r[salesCol.col])    : null,
      receipts : receiptsCol ? parseNum(r[receiptsCol.col]) : null,
      staff    : staffCol    ? parseNum(r[staffCol.col])    : null,
      target   : targetCol   ? parseNum(r[targetCol.col])   : null,
    };
  });

  // 수원 OKPOS 백업용
  const okposByDate = {};
  if (store === '수원') {
    for (const row of (okposRecords || [])) {
      if (row.SHOP_CD !== 'V68581') continue;
      const raw = row.SALE_DATE;
      const date = `${raw.slice(0,4)}-${raw.slice(4,6)}-${raw.slice(6,8)}`;
      const gross = parseInt(row.DCM_SALE_AMT, 10) || 0;
      const point = parseInt(row.CST_POINT_AMT, 10) || 0;
      const sales = gross - point;
      if (sales > 0) okposByDate[date] = sales;
    }
  }

  let updated = 0;
  for (const entry of (existing[store] || [])) {
    const dt    = entry.date;
    const sheet = sheetByDate[dt] || {};

    if (store === '수원') {
      const okpos = okposByDate[dt] || null;
      if (sheet.sales && okpos && sheet.sales !== okpos)
        log(`  [수원 참고] ${dt} 시트=${sheet.sales} OKPOS=${okpos} → 시트 사용`);
      if (sheet.sales)            entry.sales = sheet.sales;
      else if (okpos)             entry.sales = okpos;
      if (sheet.receipts != null) entry.receipts = sheet.receipts;
    } else if (store === '운정') {
      if (sheet.sales) {
        if (entry.sales && entry.sales !== sheet.sales)
          log(`  [운정 참고] ${dt} 토스=${entry.sales} 시트=${sheet.sales} → 시트 사용`);
        entry.sales = sheet.sales;
      }
      if (sheet.receipts != null) entry.receipts = sheet.receipts;
    }
    // OKPOS 매장(하남/가산/다산/광주): 매출·영수는 OKPOS 유지, 근무인원만 시트

    if (sheet.target != null)   entry.target = sheet.target;
    if (sheet.staff != null)    entry.staff  = sheet.staff;
    if (entry.sales && entry.receipts) entry.per_receipt  = Math.floor(entry.sales / entry.receipts);
    if (entry.sales && entry.staff)    entry.productivity = Math.floor(entry.sales / entry.staff);
    if (entry.sales) updated++;
  }
  log(`  ${store} 업데이트: ${updated}일 (시트: ${Object.keys(sheetByDate).length}일)`);
}

// ── 메인 ─────────────────────────────────────────────────────────────────────
(async () => {
  const yyyyMM  = process.argv[2] || getYYYYMM();
  const jsonPath = path.join(DATA_DIR, `${yyyyMM}.json`);

  log('=== 야간 수집 시작 ===', yyyyMM);

  if (!fs.existsSync(jsonPath)) {
    log('ERROR: JSON 파일 없음:', jsonPath);
    process.exit(1);
  }

  const existing = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

  // 1. OKPOS
  let okposRecords = [];
  try {
    okposRecords = await scrapeOkpos(yyyyMM);
    applyOkposData(okposRecords, existing);
  } catch(e) {
    log('ERROR OKPOS:', e.message);
  }

  // 2. 토스플레이스 (운정 백업)
  try {
    const tossRecords = await scrapeToss(yyyyMM);
    applyTossData(tossRecords, existing);
  } catch(e) {
    log('ERROR 토스:', e.message);
  }

  // 3. 전 지점 구글시트 패치
  let sheetGids = {};
  try {
    sheetGids = await getSheetGids(yyyyMM);
  } catch(e) {
    log('ERROR 시트 GID 탐색:', e.message);
  }

  for (const store of Object.keys(SHEET_IDS)) {
    const gid = sheetGids[store];
    if (!gid) { log(`[건너뜀] ${store}: GID 없음`); continue; }
    try {
      await patchStoreSheet(store, yyyyMM, existing, okposRecords, gid);
    } catch(e) {
      log(`ERROR ${store} 시트:`, e.message);
    }
  }

  // 저장
  fs.writeFileSync(jsonPath, JSON.stringify(existing, null, 2), 'utf8');
  log('저장 완료:', jsonPath);

  // 빌드 + 배포
  if (process.env.SKIP_DEPLOY === '1') { log('=== 완료 (배포 생략) ==='); process.exit(0); }
  try {
    const { execSync } = require('child_process');
    const cwd = __dirname;
    log('빌드 중...');
    execSync('node build.js', { cwd, stdio: 'inherit' });
    const dateStr = new Date().toISOString().slice(0,10);
    execSync(`git add docs/ ops_data/`, { cwd });
    execSync(`git commit -m "nightly: ${dateStr} 데이터 업데이트"`, { cwd });
    execSync(`git push`, { cwd });
    log('GitHub Pages 배포 완료');
  } catch(e) {
    log('ERROR 배포:', e.message);
  }

  log('=== 완료 ===');
})();
