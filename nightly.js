/**
 * 인크커피 야간 자동 데이터 수집
 * 실행: node nightly.js
 * 매일 영업 종료 후 자동 실행 (Task Scheduler 등록)
 *
 * 수행 작업:
 *  1. OKPOS 일자별 매출 스크래핑 → ops_data/YYYY-MM.json 업데이트
 *  2. 수원 영수건수 → Google Sheets에서 보정
 *  3. 실행 로그 → logs/YYYY-MM-DD.log
 */

const { chromium } = require('C:/Users/zoids/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright-core');
const https = require('https');
const fs    = require('fs');
const path  = require('path');

const BASE     = 'https://okasp.okpos.co.kr';
const DATA_DIR = path.join(__dirname, 'ops_data');
const LOG_DIR  = path.join(__dirname, 'logs');
const ID       = 'hqrd';
const PW       = '01526';

// OKPOS SHOP_CD → 매장키
const SHOP_MAP = {
  'V00555': '하남', 'V09651': '가산',
  'V67293': '다산', 'V67295': '다산',
  'V68581': '수원',
  'V70577': '광주', 'V70585': '광주',
};

// 수원 Google Sheets
const SUWON_SHEET = { id: '1niXSDHhFgz9KLrnrv8pDkE5Uf1CiZERlnSnLRSbNT8w', gid: '855315624' };

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

// ── CSV fetch ────────────────────────────────────────────────────────────────
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

// ── 1. OKPOS 스크래핑 ─────────────────────────────────────────────────────────
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

    // 로그인
    await page.goto('https://asp.netusys.com/login/login_form.jsp', { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('#user_id', ID);
    await page.fill('#user_pwd', PW);
    await page.press('#user_pwd', 'Enter');
    await page.waitForTimeout(3000);

    // 비번 팝업 닫기
    try {
      const pf = page.frames().find(f => f.url().includes('passwd'));
      if (pf) await pf.evaluate(() => {
        const b = [...document.querySelectorAll('button,input,a,td,span')]
          .find(e => /닫기|취소|나중/i.test(e.textContent + e.value));
        if (b) b.click();
      });
      await page.waitForTimeout(500);
    } catch(e) {}

    // 일자별 페이지
    const mainFrame = page.frames().find(f => f.url().includes('top_page')) || page.frames().find(f => f.name() === 'MainFrm');
    if (mainFrame) {
      await mainFrame.goto(BASE + '/sale/day/day_jump010.jsp', { waitUntil: 'load', timeout: 20000 });
      await page.waitForTimeout(2000);
    }

    const dailyFrame = page.frames().find(f => f.url().includes('day_total010'));
    if (!dailyFrame) throw new Error('day_total 프레임 없음');

    // AJAX 인터셉트
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

// ── 2. 수원 시트 패치 ─────────────────────────────────────────────────────────
async function patchSuwon(yyyyMM, existing) {
  log('수원 시트 패치 시작');
  const csv  = await fetchCsv(SUWON_SHEET.id, SUWON_SHEET.gid);
  const rows = parseCsv(csv);

  const salesCol    = findCol(rows, ['매출현황']);
  const receiptsCol = findCol(rows, ['영수건수']);
  const staffCol    = findCol(rows, ['당일근무인원']);

  const seen = new Set();
  const dataRows = rows.filter(r => {
    const n = parseInt(r[0]);
    if (isNaN(n) || n < 1 || n > 31 || String(n) !== r[0]) return false;
    if (seen.has(n)) return false;
    seen.add(n); return true;
  });

  let updated = 0;
  const [y, m] = yyyyMM.split('-');

  for (const r of dataRows) {
    const day = parseInt(r[0]);
    if (day < 1 || day > 31) continue;
    const date = `${y}-${m}-${String(day).padStart(2,'0')}`;
    const entry = (existing['수원'] || []).find(e => e.date === date);
    if (!entry) continue;

    const sales    = salesCol    ? parseNum(r[salesCol.col])    : null;
    const receipts = receiptsCol ? parseNum(r[receiptsCol.col]) : null;
    const staff    = staffCol    ? parseNum(r[staffCol.col])    : null;

    if (sales    !== null) entry.sales    = sales;
    if (receipts !== null) entry.receipts = receipts;
    if (staff    !== null) entry.staff    = staff;
    if (entry.sales && entry.receipts) entry.per_receipt = Math.round(entry.sales / entry.receipts);
    if (entry.sales && entry.staff)    entry.productivity = Math.round(entry.sales / entry.staff);
    updated++;
  }
  log(`  수원 시트 업데이트: ${updated}일`);
}

// ── 3. JSON 업데이트 ──────────────────────────────────────────────────────────
function applyOkposData(records, yyyyMM, existing) {
  const byDateStore = {};
  for (const row of records) {
    const storeKey = SHOP_MAP[row.SHOP_CD];
    if (!storeKey) continue;
    const raw  = row.SALE_DATE;
    const date = `${raw.slice(0,4)}-${raw.slice(4,6)}-${raw.slice(6,8)}`;
    const sales    = parseInt(row.DCM_SALE_AMT, 10) || 0;
    const receipts = parseInt(row.TOT_SALE_CNT, 10)  || 0;
    if (!byDateStore[date]) byDateStore[date] = {};
    if (!byDateStore[date][storeKey]) byDateStore[date][storeKey] = { sales: 0, receipts: 0 };
    byDateStore[date][storeKey].sales    += sales;
    byDateStore[date][storeKey].receipts += receipts;
  }

  let updated = 0;
  for (const [store, entries] of Object.entries(existing)) {
    if (store === '수원') continue; // 수원은 시트에서 처리
    for (const entry of entries) {
      const ds = byDateStore[entry.date];
      if (!ds || !ds[store]) continue;
      const { sales, receipts } = ds[store];
      if (sales > 0) {
        entry.sales       = sales;
        entry.receipts    = receipts;
        entry.per_receipt = receipts > 0 ? Math.round(sales / receipts) : null;
        if (entry.staff && entry.staff > 0) entry.productivity = Math.round(sales / entry.staff);
        updated++;
      }
    }
  }
  log(`  OKPOS 업데이트: ${updated}건`);
}

// ── 메인 ─────────────────────────────────────────────────────────────────────
(async () => {
  const yyyyMM  = process.argv[2] || getYYYYMM();
  const jsonPath = path.join(DATA_DIR, `${yyyyMM}.json`);

  log('=== 야간 수집 시작 ===', yyyyMM);

  if (!fs.existsSync(jsonPath)) {
    log('ERROR: JSON 파일 없음:', jsonPath);
    log('새 달 시작 시 fetch_april.js 먼저 실행 필요');
    process.exit(1);
  }

  const existing = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

  try {
    // 1. OKPOS
    const records = await scrapeOkpos(yyyyMM);
    applyOkposData(records, yyyyMM, existing);
  } catch(e) {
    log('ERROR OKPOS:', e.message);
  }

  try {
    // 2. 수원 시트
    await patchSuwon(yyyyMM, existing);
  } catch(e) {
    log('ERROR 수원시트:', e.message);
  }

  // 저장
  fs.writeFileSync(jsonPath, JSON.stringify(existing, null, 2), 'utf8');
  log('저장 완료:', jsonPath);
  log('=== 완료 ===');
})();
