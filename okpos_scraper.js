/**
 * OKPOS 일자별 매출 스크래퍼
 * 실행: node okpos_scraper.js [YYYY-MM]
 * 기본: 현재월
 * 결과: ops_data/YYYY-MM.json 에 sales/receipts/per_receipt 업데이트
 */
const { chromium } = require('C:/Users/zoids/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright-core');
const fs   = require('fs');
const path = require('path');

const BASE    = 'https://okasp.okpos.co.kr';
const OUT_DIR = path.join(__dirname, 'ops_data');
const ID      = 'hqrd';
const PW      = '01526';

// SHOP_CD → ops_data 매장키 매핑 (다산·광주는 합산)
const SHOP_MAP = {
  'V00555': '하남',
  'V09651': '가산',
  'V67293': '다산',
  'V67295': '다산',
  'V68581': '수원',
  'V70577': '광주',
  'V70585': '광주',
};

async function login(page) {
  await page.goto('https://asp.netusys.com/login/login_form.jsp', { waitUntil: 'networkidle', timeout: 30000 });
  await page.fill('#user_id', ID);
  await page.fill('#user_pwd', PW);
  await page.press('#user_pwd', 'Enter');
  await page.waitForTimeout(3000);
}

async function closePasswdPopup(page) {
  try {
    const pf = page.frames().find(f => f.url().includes('passwd'));
    if (pf) {
      await pf.evaluate(() => {
        const b = [...document.querySelectorAll('button,input,a,td,span')]
          .find(e => /닫기|취소|나중/i.test(e.textContent + e.value));
        if (b) b.click();
      });
      await page.waitForTimeout(500);
    }
  } catch(e) {}
}

async function scrapeMonth(page, yyyyMM) {
  const [y, m] = yyyyMM.split('-');
  const daysInMonth = new Date(+y, +m, 0).getDate();
  const today = new Date();
  const lastDay = (today.getFullYear() === +y && today.getMonth() + 1 === +m)
    ? String(today.getDate()).padStart(2, '0')
    : String(daysInMonth).padStart(2, '0');

  const startDate = `${y}-${m}-01`;
  const endDate   = `${y}-${m}-${lastDay}`;
  console.log(`\n조회: ${startDate} ~ ${endDate}`);

  // 일자별 페이지 로드
  const mainFrame = page.frames().find(f => f.url().includes('top_page') || f.url().includes('day_total'))
    || page.frames().find(f => f.name() === 'MainFrm');
  if (mainFrame) {
    await mainFrame.goto(BASE + '/sale/day/day_jump010.jsp', { waitUntil: 'load', timeout: 20000 });
    await page.waitForTimeout(2000);
  }

  const dailyFrame = page.frames().find(f => f.url().includes('day_total010'));
  if (!dailyFrame) {
    console.log('day_total 프레임 없음. 현재 프레임:');
    page.frames().forEach(f => console.log(' -', f.url().slice(0, 80)));
    return null;
  }

  await closePasswdPopup(page);

  // AJAX 인터셉트 설정
  let rawData = null;
  const handler = async route => {
    const url = route.request().url();
    if (url.includes('day') || url.includes('sale') || url.includes('list') || url.includes('Search')) {
      const response = await route.fetch();
      const text = await response.text();
      if (text.includes('SHOP_CD') && text.includes('SALE_DATE') && text.includes('DCM_SALE_AMT')) {
        rawData = text;
        console.log('  AJAX 캡쳐:', url.slice(0, 80), '| 길이:', text.length);
      }
      await route.fulfill({ response });
    } else {
      await route.continue();
    }
  };
  await page.route('**/*', handler);

  // 날짜·매장 설정 후 조회
  await dailyFrame.evaluate(({ s, e }) => {
    document.querySelector('#date1_1').value = s;
    document.querySelector('#date1_2').value = e;
    document.querySelector('#ss_SHOP_CD').value = '';
    document.querySelector('#ss_SHOP_NM').value = '전체';
    if (document.querySelector('#ss_SHOP_INFO'))
      document.querySelector('#ss_SHOP_INFO').value = '[]';
    const chk = document.querySelector('#chkRowShow');
    if (chk && !chk.checked) chk.click();
    fnSearch();
  }, { s: startDate, e: endDate });

  await page.waitForTimeout(5000);
  await page.unroute('**/*', handler);

  if (!rawData) {
    console.log('  AJAX 응답 없음');
    return null;
  }

  return { raw: rawData, startDate, endDate };
}

function parseAndMerge(result, yyyyMM) {
  const data = JSON.parse(result.raw);
  console.log(`\n파싱: 총 ${data.Data.length}개 레코드`);

  // SALE_DATE별, 매장별 합산
  // { '2026-04-01': { '하남': { sales, receipts }, ... }, ... }
  const byDateStore = {};

  for (const row of data.Data) {
    const storeKey = SHOP_MAP[row.SHOP_CD];
    if (!storeKey) continue;

    const raw = row.SALE_DATE; // '20260415'
    const date = `${raw.slice(0,4)}-${raw.slice(4,6)}-${raw.slice(6,8)}`;
    const sales    = parseInt(row.DCM_SALE_AMT, 10) || 0;
    const receipts = parseInt(row.TOT_SALE_CNT, 10) || 0;

    if (!byDateStore[date]) byDateStore[date] = {};
    if (!byDateStore[date][storeKey]) byDateStore[date][storeKey] = { sales: 0, receipts: 0 };
    byDateStore[date][storeKey].sales    += sales;
    byDateStore[date][storeKey].receipts += receipts;
  }

  // ops_data JSON 로드
  const jsonPath = path.join(OUT_DIR, `${yyyyMM}.json`);
  if (!fs.existsSync(jsonPath)) {
    console.log('JSON 파일 없음:', jsonPath);
    return;
  }
  const existing = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

  let updated = 0;
  for (const [store, entries] of Object.entries(existing)) {
    for (const entry of entries) {
      const ds = byDateStore[entry.date];
      if (!ds || !ds[store]) continue;
      const { sales, receipts } = ds[store];
      if (sales > 0) {
        entry.sales       = sales;
        entry.receipts    = receipts;
        entry.per_receipt = receipts > 0 ? Math.round(sales / receipts) : null;
        if (entry.staff && entry.staff > 0) {
          entry.productivity = Math.round(sales / entry.staff);
        }
        updated++;
      }
    }
  }

  fs.writeFileSync(jsonPath, JSON.stringify(existing, null, 2), 'utf8');
  console.log(`\n저장 완료: ${jsonPath}`);
  console.log(`업데이트된 항목: ${updated}개`);

  // 샘플 출력
  console.log('\n=== 샘플 (가산 첫 3일) ===');
  (existing['가산'] || []).slice(0, 3).forEach(e =>
    console.log(`  ${e.date}: 매출=${e.sales?.toLocaleString()} 영수=${e.receipts} 객단가=${e.per_receipt?.toLocaleString()}`));
}

(async () => {
  const yyyyMM = process.argv[2] || `${new Date().getFullYear()}-${String(new Date().getMonth()+1).padStart(2,'0')}`;
  console.log(`=== OKPOS 스크래퍼: ${yyyyMM} ===`);

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Users/zoids/AppData/Local/ms-playwright/chromium-1212/chrome-win64/chrome.exe',
  });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1400, height: 900 });

  await login(page);
  await closePasswdPopup(page);

  const result = await scrapeMonth(page, yyyyMM);
  await browser.close();

  if (result) {
    parseAndMerge(result, yyyyMM);
  } else {
    console.log('데이터 없음 - 종료');
  }
})();
