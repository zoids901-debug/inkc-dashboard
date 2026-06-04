// GET /api/ops-live
//   운영 대시보드 "오늘" 실시간 매출/영수.
//   OKPOS(okasp.okpos.co.kr) day_total010 으로 6개 OKPOS 매장 일별총매출+영수 1회 조회,
//   운정은 TOSS period/daily 로 조회.
//   반환: { date, fetchedAt, stores:{ 가산:{sales,receipts}, 다산:{...}, ..., 운정:{...} } }
//   자격증명: Cloudflare 환경변수 OKPOS_ID / OKPOS_PW / TOSS_ID / TOSS_PW.
//   세션/CSRF 시퀀스는 ops_actions_sync.py(밤 배치) 및 베이커리 pos-live.js 와 동일.

const OK = 'https://okasp.okpos.co.kr';
const TOSS_BASE = 'https://api-public.tossplace.com';
const TOSS_MERCHANT = 304265;

// OKPOS SHOP_CD → 매장키 (수원 포함, 운정은 TOSS 별도)
const SHOP_MAP = {
  'V00555': '하남', 'V09651': '가산',
  'V67293': '다산', 'V67295': '다산',
  'V68581': '수원',
  'V70577': '광주', 'V70585': '광주',
};

// 36자리 UUID 형태 hidden input(CSRF) 추출 — name/value 순서 양쪽 대응
function findCsrf(html) {
  const U = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  let m = html.match(new RegExp(`name=['"](${U})['"]\\s+value=['"](${U})['"]`, 'i'));
  if (m) return [m[1], m[2]];
  m = html.match(new RegExp(`value=['"](${U})['"]\\s+name=['"](${U})['"]`, 'i'));
  if (m) return [m[2], m[1]];
  return [null, null];
}

// 쿠키 보관 (Workers fetch는 쿠키 자동관리 안 함 → 수동)
function makeJar() {
  const jar = {};
  return {
    header() { return Object.entries(jar).map(([k, v]) => `${k}=${v}`).join('; '); },
    capture(res) {
      let cookies = [];
      if (typeof res.headers.getSetCookie === 'function') cookies = res.headers.getSetCookie();
      else { const sc = res.headers.get('set-cookie'); if (sc) cookies = [sc]; }
      for (const c of cookies) {
        const first = c.split(';')[0];
        const idx = first.indexOf('=');
        if (idx > 0) {
          const k = first.slice(0, idx).trim();
          const v = first.slice(idx + 1).trim();
          if (v && v !== 'deleteMe') jar[k] = v;
        }
      }
    },
  };
}

async function req(jar, path, { method = 'GET', body = null, referer = null } = {}) {
  const headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Trident/7.0; rv:11.0) like Gecko',
    'Accept-Language': 'ko-KR',
  };
  const cookie = jar.header();
  if (cookie) headers['Cookie'] = cookie;
  if (referer) headers['Referer'] = referer;
  if (method === 'POST') headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8';
  const res = await fetch(OK + path, { method, headers, body, redirect: 'manual' });
  jar.capture(res);
  return res;
}

async function login(jar, id, pw) {
  let html = await (await req(jar, '/login/login_form.jsp')).text();
  const [ck, cv] = findCsrf(html);
  if (!ck) throw new Error('로그인 폼 CSRF 파싱 실패');
  const cred = `AutoFg=W&user_id=${encodeURIComponent(id)}&user_pwd=${encodeURIComponent(pw)}`;
  await req(jar, '/login/login_check.jsp', { method: 'POST', body: `${ck}=${cv}&${cred}`, referer: OK + '/login/login_form.jsp' });
  await req(jar, '/login/login_check_action.jsp', { method: 'POST', body: `${ck}=${cv}&${ck}=${cv}&${cred}`, referer: OK + '/login/login_form.jsp' });
  let sessCsrf = [null, null];
  for (const p of ['/login/top_frame.jsp', '/login/top_page.jsp', '/login/history.jsp', '/login/showitem.jsp', '/login/menuitem.jsp', '/login/menuv.jsp']) {
    const h = await (await req(jar, p)).text();
    if (!sessCsrf[0]) { const c = findCsrf(h); if (c[0]) sessCsrf = c; }
  }
  if (!sessCsrf[0]) throw new Error('세션 CSRF 파싱 실패 (로그인 실패 가능)');
  // 일별총매출 폼 진입(워밍업) — 컨트롤러는 day_jump010 안의 day_total010 프레임
  await req(jar, '/sale/day/day_jump010.jsp');
  await req(jar, '/sale/day/day_total010.jsp', { referer: OK + '/sale/day/day_jump010.jsp' });
  return sessCsrf;
}

// day_total010: ss_SHOP_CD='' → 전매장 1회 조회, chkRowShow=Y 필수
async function fetchDayTotal(jar, csrf, dateStr) {
  const params = new URLSearchParams({
    [csrf[0]]: csrf[1],
    S_CONTROLLER: 'sale.day.day_total010', S_METHOD: 'search', SHEETSEQ: '1',
    date1_1: dateStr, date1_2: dateStr, date_period1: '1',
    ss_SHOP_CD: '', ss_SHOP_NM: '전체', ss_SHOP_INFO: '[]',
    ss_PAGE_NO1: '1', chkRowShow: 'Y',
  });
  const res = await req(jar, '/sale/day/ddd.htmlSheetAction', {
    method: 'POST', body: params.toString(), referer: OK + '/sale/day/day_total010.jsp',
  });
  const j = await res.json();
  if ((j?.Result?.Code ?? 0) < 0) throw new Error(j?.Result?.Message || 'OKPOS day_total 오류');
  return j.Data || [];
}

// ── TOSS 운정 (period/daily) ──
async function tossLogin(id, pw) {
  const r1 = await fetch(`${TOSS_BASE}/api-public/dashboard/v2/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0',
               'Origin': 'https://dashboard.tossplace.com', 'Accept': 'application/json' },
    body: JSON.stringify({ id, password: pw, loginType: 'DASHBOARD_USER' }),
  });
  const d1 = await r1.json();
  if (d1?.resultType !== 'SUCCESS') throw new Error('TOSS 로그인 실패');
  const token = d1.success.accessToken;
  const r2 = await fetch(`${TOSS_BASE}/api-public/dashboard/v1/workspaces?type=BRAND`, {
    headers: { 'Authorization': `Bearer ${token}`, 'User-Agent': 'Mozilla/5.0',
               'Origin': 'https://dashboard.tossplace.com', 'Accept': 'application/json' },
  });
  const items = ((await r2.json())?.success || {}).items || [];
  if (!items.length) throw new Error('TOSS workspace(type=BRAND) 없음');
  return {
    'Authorization': `Bearer ${token}`, 'dashboard-workspace-id': String(items[0].id),
    'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0',
    'Origin': 'https://dashboard.tossplace.com', 'Accept': 'application/json',
  };
}

async function tossDay(headers, dateStr) {
  const res = await fetch(`${TOSS_BASE}/dashboard/v1/reports/period/daily`, {
    method: 'POST', headers,
    body: JSON.stringify({ merchantIds: [TOSS_MERCHANT], startDate: dateStr, endDate: dateStr, includeMerchantAsColumn: false }),
  });
  const j = await res.json();
  if (j?.resultType !== 'SUCCESS') throw new Error('TOSS period/daily 오류');
  for (const r of (j.success?.report || [])) {
    const s = r?.content?.sales || {};
    const sales = parseInt(s.netSalesAmount || 0, 10);
    const receipts = parseInt(s.paymentCount || 0, 10);
    if (sales > 0) return { sales, receipts };
  }
  return null;
}

function kstToday() {
  const t = Date.now() + 9 * 3600 * 1000;       // UTC+9
  return new Date(t).toISOString().slice(0, 10);
}

export async function onRequestGet(context) {
  const { env, request, waitUntil } = context;
  const id = env.OKPOS_ID, pw = env.OKPOS_PW;
  if (!id || !pw) {
    return Response.json({ error: 'OKPOS_ID/OKPOS_PW 환경변수 미설정' }, { status: 500 });
  }
  // 캐시: 60초. 여러 탭/사용자가 자주 호출해도 OKPOS/TOSS엔 1분에 1회만 로그인.
  const url = new URL(request.url);
  const cache = caches.default;
  const cacheKey = new Request(url.origin + '/api/ops-live-cache', { method: 'GET' });
  if (!url.searchParams.get('force')) {
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
  }
  const date = kstToday();
  const stores = {};
  try {
    const jar = makeJar();
    const csrf = await login(jar, id, pw);
    const rows = await fetchDayTotal(jar, csrf, date);
    for (const row of rows) {
      const loc = SHOP_MAP[row.SHOP_CD];
      if (!loc) continue;
      const gross = parseInt(row.DCM_SALE_AMT || 0, 10);
      const point = parseInt(row.CST_POINT_AMT || 0, 10);
      const sales = gross - point;
      const receipts = parseInt(row.TOT_SALE_CNT || 0, 10);
      const b = stores[loc] || (stores[loc] = { sales: 0, receipts: 0 });
      b.sales += sales;
      b.receipts += receipts;
    }
    // 영수=1 + 매출>20만 가드 (영수증 시스템 미작동 시기 보정 — 밤배치와 동일)
    for (const loc of Object.keys(stores)) {
      const b = stores[loc];
      if (b.receipts === 1 && b.sales > 200000) b.receipts = null;
    }
  } catch (e) {
    return Response.json({ error: 'OKPOS: ' + String(e && e.message || e), date }, { status: 502 });
  }
  // 운정 (TOSS) — 실패해도 OKPOS 결과는 반환
  try {
    if (env.TOSS_ID && env.TOSS_PW) {
      const th = await tossLogin(env.TOSS_ID, env.TOSS_PW);
      const u = await tossDay(th, date);
      if (u) stores['운정'] = u;
    }
  } catch (e) { /* 운정 실패 무시 */ }

  const resp = Response.json(
    { date, fetchedAt: new Date().toISOString(), stores },
    { headers: { 'Cache-Control': 'public, max-age=60' } });
  waitUntil(cache.put(cacheKey, resp.clone()));
  return resp;
}
