// GET /api/prod-live
//   상품 대시보드 "오늘" 실시간 SKU별 판매.
//   OKPOS prod011 로 6개 OKPOS 매장 SKU별 조회 + 운정은 TOSS item-sales.
//   반환은 product-dashboard 의 data/daily/YYMMDD.json 과 동일 shape:
//     { date, fetchedAt, stores:{ 가산:[{item,code,qty,net,cat_big,cat_mid,cat_small}], ..., 운정:[...] } }
//   자격증명: Cloudflare 환경변수 OKPOS_ID / OKPOS_PW / TOSS_ID / TOSS_PW.

const OK = 'https://okasp.okpos.co.kr';
const TOSS_BASE = 'https://api-public.tossplace.com';
const TOSS_MERCHANT = 304265;

// location 기준 합산 (다산 1층+지하, 광주 챔피언스+ToGo)
const STORES = [
  { code: 'V09651', name: '인크커피(가산점)',             loc: '가산' },
  { code: 'V67293', name: '인크커피다산1호점(1층)',        loc: '다산' },
  { code: 'V67295', name: '인크커피다산1호점(지하)',        loc: '다산' },
  { code: 'V68581', name: '인크커피스타필드수원점',         loc: '수원' },
  { code: 'V00555', name: '인크커피(하남미사1호점)',        loc: '하남' },
  { code: 'V70577', name: '인크커피광주기아챔피언스필드점', loc: '광주' },
  { code: 'V70585', name: '인크커피광주(To go zone)',      loc: '광주' },
];

// 표기 통일 (밤 배치 actions_sync.py NAME_ALIASES 와 동일하게 유지)
const ALIASES = {
  '애플 잼 스콘': '애플잼 스콘',
  '카페라떼': 'I 카페 라떼',
  '카페모카': 'I 카페 모카',
  '피스타치오 퀸아망': '피스타치오 퀸 아망',
  '얼그레이 퀸아망': '얼 그레이 퀸 아망',
  '무화과크림치즈휘낭시에': '무화과 크림 치즈 휘낭시에',
  '얼그레이휘낭시에': '얼 그레이 휘낭시에',
  '햄치즈 소금빵': '햄 치즈 소금빵',
  '레몬 버터바': '레몬 버터 바',
  '피넛 버터바': '피넛 버터 바',
  '오렌지 쇼핑백': '오렌지쇼핑백',
  '다크 오리진 블렌드 (200g)': '다크 오리진블렌드 200g',
  '인크 오리진 블렌드 (200g)': '인크 오리진블렌드 200g',
  '벨벳 브리즈 (200g)': '벨벳브리즈 200g',
  '콜롬비아 디카페인 (200g)': '콜롬비아 디카페인(200g)',
  '인크 오리진 블렌드1KG': '인크 오리진블렌드 1Kg',
  '다크 오리진 블렌드 1KG': '다크 오리진블렌드 1Kg',
};
const normalize = (nm) => ALIASES[nm] || nm;

function isValid(nm) {
  if (!nm) return false;
  const stripped = nm.replace(/[*\-=★☆ ]/g, '');
  if (!stripped) return false;
  if (nm.startsWith('**') || nm.startsWith('--') || nm.startsWith('==')) return false;
  return true;
}

function findCsrf(html) {
  const U = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  let m = html.match(new RegExp(`name=['"](${U})['"]\\s+value=['"](${U})['"]`, 'i'));
  if (m) return [m[1], m[2]];
  m = html.match(new RegExp(`value=['"](${U})['"]\\s+name=['"](${U})['"]`, 'i'));
  if (m) return [m[2], m[1]];
  return [null, null];
}

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
  await req(jar, '/sale/sale/prod010.jsp');
  await req(jar, '/sale/sale/prod011.jsp', { referer: OK + '/sale/sale/prod010.jsp' });
  return sessCsrf;
}

async function fetchDay(jar, csrf, dateStr, code, name) {
  const shopInfo = JSON.stringify([{ SHOP_CD: code, SHOP_NM: name }]);
  const params = new URLSearchParams({
    [csrf[0]]: csrf[1],
    S_CONTROLLER: 'sale.sale.prod011', S_METHOD: 'search', SHEETSEQ: '1',
    S_SAVENAME: '', ss_PROD_FG: 'N',
    date1_1: dateStr, date1_2: dateStr, date_period1: '1',
    ss_CLS_TEXT: '전체', ss_SHOP_CD: code, ss_SHOP_NM: name,
    ss_SHOP_INFO: shopInfo, ss_VENDOR_NM: '전체', ss_VENDOR_INFO: '[]', ss_PAGE_NO1: '1',
  });
  const res = await req(jar, '/sale/sale/ddd.htmlSheetAction', {
    method: 'POST', body: params.toString(), referer: OK + '/sale/sale/prod011.jsp',
  });
  const j = await res.json();
  if ((j?.Result?.Code ?? 0) < 0) throw new Error(j?.Result?.Message || 'API 오류');
  return j.Data || [];
}

// ── TOSS 운정 (item-sales) ──
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

async function tossItemsDay(headers, dateStr) {
  const res = await fetch(`${TOSS_BASE}/dashboard/v1/reports/multivariate/item-sales`, {
    method: 'POST', headers,
    body: JSON.stringify({ merchantIds: [TOSS_MERCHANT], dateRange: { start: dateStr, end: dateStr }, aggFields: ['ITEM_SALES'] }),
  });
  const j = await res.json();
  const items = j?.success?.data?.itemSales || [];
  const out = [];
  for (const it of items) {
    let nm = (it.itemTitle || '').trim();
    const c = it.content || {};
    const qty = parseInt(c.transactionCount || 0, 10);
    const net = parseInt(c.amountMoney || 0, 10);
    if (!isValid(nm) || qty <= 0) continue;
    nm = normalize(nm);
    out.push({ item: nm, code: '', qty, net, cat_big: '', cat_mid: '', cat_small: '' });
  }
  return out;
}

function kstToday() {
  const t = Date.now() + 9 * 3600 * 1000;
  return new Date(t).toISOString().slice(0, 10);
}

export async function onRequestGet(context) {
  const { env, request, waitUntil } = context;
  const id = env.OKPOS_ID, pw = env.OKPOS_PW;
  if (!id || !pw) {
    return Response.json({ error: 'OKPOS_ID/OKPOS_PW 환경변수 미설정' }, { status: 500 });
  }
  const url = new URL(request.url);
  const cache = caches.default;
  const cacheKey = new Request(url.origin + '/api/prod-live-cache', { method: 'GET' });
  if (!url.searchParams.get('force')) {
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
  }
  const date = kstToday();
  const buckets = {};  // loc → { item: row }
  try {
    const jar = makeJar();
    const csrf = await login(jar, id, pw);
    for (const st of STORES) {
      let rows;
      try { rows = await fetchDay(jar, csrf, date, st.code, st.name); }
      catch (e) { continue; }
      const b = buckets[st.loc] || (buckets[st.loc] = {});
      for (const row of rows) {
        let nm = (row.PROD_NM || '').trim();
        const qty = parseInt(row.SALE_QTY || 0, 10);
        const net = parseInt(row.TOT_SALE_AMT || 0, 10);
        if (!isValid(nm) || net === 0) continue;
        nm = normalize(nm);
        if (b[nm]) {
          b[nm].qty += qty; b[nm].net += net;
          if (!b[nm].code && row.PROD_CD) b[nm].code = (row.PROD_CD || '').trim();
          if (!b[nm].cat_big && row.LCLS_NM) {
            b[nm].cat_big = (row.LCLS_NM || '').trim();
            b[nm].cat_mid = (row.MCLS_NM || '').trim();
            b[nm].cat_small = (row.SCLS_NM || '').trim();
          }
        } else {
          b[nm] = {
            item: nm, code: (row.PROD_CD || '').trim(), qty, net,
            cat_big: (row.LCLS_NM || '').trim(),
            cat_mid: (row.MCLS_NM || '').trim(),
            cat_small: (row.SCLS_NM || '').trim(),
          };
        }
      }
    }
  } catch (e) {
    return Response.json({ error: 'OKPOS: ' + String(e && e.message || e), date }, { status: 502 });
  }
  const stores = {};
  for (const loc of Object.keys(buckets)) stores[loc] = Object.values(buckets[loc]);
  // 운정 (TOSS) — 실패해도 OKPOS 결과는 반환
  try {
    if (env.TOSS_ID && env.TOSS_PW) {
      const th = await tossLogin(env.TOSS_ID, env.TOSS_PW);
      const rows = await tossItemsDay(th, date);
      if (rows.length) stores['운정'] = rows;
    }
  } catch (e) { /* 운정 실패 무시 */ }

  const resp = Response.json(
    { date, fetchedAt: new Date().toISOString(), stores },
    { headers: { 'Cache-Control': 'public, max-age=60' } });
  waitUntil(cache.put(cacheKey, resp.clone()));
  return resp;
}
