/**
 * 인크커피 운영팀 일데이터 대시보드
 * node dashboard_server.js → http://localhost:3000
 */
const http = require('http');
const fs   = require('fs');
const path = require('path');

const PORT     = 3000;
const DATA_DIR = path.join(__dirname, 'ops_data');

function loadAllData() {
  const result = {};
  fs.readdirSync(DATA_DIR).filter(f => f.endsWith('.json')).sort().forEach(f => {
    result[f.replace('.json', '')] = JSON.parse(fs.readFileSync(path.join(DATA_DIR, f), 'utf8'));
  });
  return result;
}

function html(allData) {
  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>인크커피 운영 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/litepicker/dist/litepicker.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#F1F5F9;color:#1E293B;font-size:13px}

/* ── 헤더 ── */
.hdr{background:#1E293B;padding:0 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;min-height:48px;position:sticky;top:0;z-index:200}
.hdr-title{font-size:15px;font-weight:700;color:#fff;white-space:nowrap;letter-spacing:-.3px}
.hdr-title em{color:#F59E0B;font-style:normal}
.sep{width:1px;height:20px;background:#334155;flex-shrink:0}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:8px}

/* ── 컨트롤 바 (날짜 + 매장) ── */
.ctrl-bar{background:#fff;border-bottom:1px solid #E2E8F0;padding:10px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;position:sticky;top:48px;z-index:190;box-shadow:0 1px 3px rgba(0,0,0,.05)}

/* 프리셋 버튼 */
.presets{display:flex;gap:5px}
.preset-btn{border:1px solid #CBD5E1;border-radius:6px;padding:5px 11px;font-size:12px;font-weight:600;color:#64748B;background:#fff;cursor:pointer;transition:.15s;white-space:nowrap}
.preset-btn:hover{border-color:#3B82F6;color:#3B82F6}
.preset-btn.active{background:#3B82F6;border-color:#3B82F6;color:#fff}

/* 날짜 범위 선택 */
.date-range{display:flex;align-items:center;gap:8px;background:#F8FAFC;border:1.5px solid #CBD5E1;border-radius:8px;padding:5px 12px;cursor:pointer}
.date-range .dr-label{font-size:11px;font-weight:700;color:#64748B;white-space:nowrap}
.date-range .dr-sep{color:#94A3B8;font-weight:700}
#dateRangeInput{border:none;background:transparent;font-size:13px;font-weight:600;color:#1E293B;cursor:pointer;padding:0 4px;width:200px;text-align:center}
#dateRangeInput:focus{outline:none}
.litepicker{--color-primary-btn:#3B82F6;--color-hover:#DBEAFE;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px}
.litepicker .container__months{box-shadow:0 4px 20px rgba(0,0,0,.12);border-radius:12px;background:#fff}
.litepicker .month-item-header button{color:#3B82F6}
.litepicker .day-item.is-start-date,.litepicker .day-item.is-end-date{background:#3B82F6!important;color:#fff!important;border-radius:50%}
.litepicker .day-item.is-in-range{background:#DBEAFE!important;color:#1E293B!important}
.ctrl-sep{width:1px;height:24px;background:#E2E8F0;flex-shrink:0}

/* 매장 필터 */
.store-pills{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
.pills-label{font-size:11px;font-weight:700;color:#94A3B8;white-space:nowrap}
.pill{border-radius:20px;padding:4px 12px;font-size:11px;font-weight:700;cursor:pointer;border:1.5px solid transparent;transition:.15s;opacity:.35;white-space:nowrap}
.pill.on{opacity:1}

/* ── 본문 ── */
.main{max-width:1440px;margin:0 auto;padding:16px 20px;display:flex;flex-direction:column;gap:14px}

/* 카드 */
.card{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.07);padding:18px 20px}
.card-title{font-size:12px;font-weight:700;color:#64748B;text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px}

/* ── 페이스 카드 ── */
.pace-card{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:1px;background:#E2E8F0;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.07)}
.pace-item{background:#fff;padding:16px 20px}
.pace-item .lbl{font-size:11px;font-weight:600;color:#94A3B8;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px}
.pace-item .val{font-size:24px;font-weight:800;color:#1E293B;line-height:1}
.pace-item .sub{font-size:11px;color:#94A3B8;margin-top:5px}
.pace-item .progress{height:5px;background:#E2E8F0;border-radius:3px;margin-top:10px;overflow:hidden}
.pace-item .progress-fill{height:100%;border-radius:3px;transition:width .4s}
.badge{display:inline-block;font-size:10px;font-weight:700;border-radius:10px;padding:2px 7px;margin-left:6px;vertical-align:middle}
.badge.up{background:#DCFCE7;color:#15803D}
.badge.down{background:#FEE2E2;color:#B91C1C}
.badge.neutral{background:#F1F5F9;color:#64748B}

/* ── 2단 레이아웃 ── */
.row2{display:grid;grid-template-columns:1fr 340px;gap:14px}
.row2b{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:960px){.row2,.row2b{grid-template-columns:1fr}}
@media(max-width:900px){
  .hdr{padding:0 12px;min-height:42px;gap:10px}
  .hdr-title{font-size:13px}
  .ctrl-bar{top:42px;padding:7px 12px;gap:10px;font-size:11px}
  .preset-btn{padding:4px 9px;font-size:11px}
  .date-range{padding:4px 9px;gap:5px}
  #dateRangeInput{width:150px;font-size:12px}
  .date-range .dr-label{font-size:10px}
  .pills-label{font-size:10px}
  .pill{padding:3px 10px;font-size:10.5px}
  .main{padding:12px 10px;gap:10px}
  .card{padding:13px 13px}
  .card-title{font-size:11px;margin-bottom:10px}
  .pace-card{grid-template-columns:repeat(2,1fr)}
  .pace-item{padding:12px 14px}
  .pace-item .val{font-size:19px}
  .pace-item .lbl{font-size:10px}
  .pace-item .sub{font-size:10px}
  .row2,.row2b{grid-template-columns:1fr}
  .h220{height:180px}
  .h240{height:200px}
  .h200{height:170px}
  .donut-canvas-wrap{width:150px;height:150px}
  .dt-table{font-size:11px}
  .dt-date,.dt-td,.dt-dow{padding:4px 5px}
  .rank-table th,.rank-table td{padding:6px 6px;font-size:11px}
}
@media(max-width:480px){
  .hdr{padding:0 10px;min-height:40px}
  .hdr-title{font-size:12px}
  .ctrl-bar{top:40px;padding:6px 10px;gap:8px}
  .preset-btn{padding:3px 7px;font-size:10px}
  .date-range{padding:3px 7px}
  #dateRangeInput{width:120px;font-size:11px}
  .ctrl-sep{display:none}
  .pill{padding:2px 8px;font-size:10px}
  .main{padding:8px 6px;gap:8px}
  .card{padding:10px 10px}
  .pace-card{grid-template-columns:repeat(2,1fr)}
  .pace-item{padding:10px 10px}
  .pace-item .val{font-size:17px}
  .h220{height:160px}
  .h240{height:180px}
  .h200{height:150px}
  .donut-canvas-wrap{width:130px;height:130px}
  .dt-table{font-size:10.5px}
}
.dt-table{width:100%;border-collapse:collapse;font-size:12px}
.dt-table thead tr:first-child th{background:#F8FAFC;font-weight:700;padding:6px 8px;border-bottom:2px solid #E2E8F0;text-align:center;white-space:nowrap}
.dt-table thead tr:last-child th{background:#F8FAFC;font-weight:500;color:#64748B;padding:3px 6px;border-bottom:1px solid #E2E8F0;text-align:center;font-size:11px}
.dt-th{white-space:nowrap}
.dt-sub{white-space:nowrap}
.dt-table tbody tr:hover{background:#F0F9FF}
.dt-table tfoot td{background:#F1F5F9;font-weight:700;border-top:2px solid #CBD5E1}
.dt-date{padding:5px 8px;color:#374151;font-weight:600;white-space:nowrap;text-align:center}
.dt-dow{padding:5px 4px;color:#6B7280;text-align:center;font-size:11px}
.dt-td{padding:5px 8px;text-align:right;color:#1E293B;border-bottom:1px solid #F1F5F9}
.dt-sum{font-weight:600;background:#F8FAFC}
.dt-total{font-weight:700;color:#1E293B}
.dt-wknd .dt-date,.dt-wknd .dt-dow{color:#EF4444}
.dt-wknd td{background:#FFF5F5}

/* ── 순위 테이블 ── */
.rank-table{width:100%;border-collapse:collapse}
.rank-table th{font-size:10px;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:.3px;padding:6px 10px;text-align:right;border-bottom:2px solid #F1F5F9;white-space:nowrap}
.rank-table th:first-child,.rank-table th:nth-child(2){text-align:left}
.rank-table td{padding:9px 10px;border-bottom:1px solid #F8FAFC;text-align:right;font-size:12px}
.rank-table td:first-child{text-align:center;font-size:11px;font-weight:700;color:#94A3B8;width:28px}
.rank-table td:nth-child(2){text-align:left;font-weight:700}
.rank-table tr:last-child td{border-bottom:none}
.rank-table tr:hover td{background:#F8FAFC}
.store-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle}
.delta{font-size:10px;margin-left:3px}
.delta.up{color:#15803D}
.delta.dn{color:#DC2626}
.ach-chip{display:inline-block;border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700}
.ach-g{background:#DCFCE7;color:#15803D}
.ach-y{background:#FEF9C3;color:#92400E}
.ach-r{background:#FEE2E2;color:#B91C1C}

/* ── 차트 ── */
.chart-wrap{position:relative}
.h220{height:220px}
.h240{height:240px}
.h200{height:200px}

/* ── 도넛 ── */
.donut-wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;height:100%;padding-top:4px}
.donut-canvas-wrap{position:relative;width:180px;height:180px}
.donut-legend{display:flex;flex-direction:column;gap:5px;width:100%}
.dl-item{display:flex;justify-content:space-between;align-items:center;font-size:11px}
.dl-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;margin-right:6px}
.dl-name{font-weight:600;color:#1E293B;flex:1}
.dl-pct{font-weight:700;color:#475569}

/* ── YoY 범례 ── */
.chart-legend{display:flex;gap:14px;margin-bottom:10px;flex-wrap:wrap}
.cl-item{display:flex;align-items:center;gap:5px;font-size:11px;color:#64748B}
.cl-line{width:20px;height:2px;border-radius:1px}
.cl-dashed{border-top:2px dashed #94A3B8;width:20px;height:0}
</style>
</head>
<body>

<!-- 헤더 -->
<div class="hdr">
  <div class="hdr-title">인크<em>커피</em> 운영 대시보드</div>
</div>

<!-- 컨트롤 바 -->
<div class="ctrl-bar">
  <!-- 프리셋 -->
  <div class="presets" id="presets">
    <button class="preset-btn" data-p="yesterday">어제</button>
    <button class="preset-btn" data-p="week">이번 주</button>
    <button class="preset-btn active" data-p="mtd">이번 달</button>
    <button class="preset-btn" data-p="last_month">지난 달</button>
    <button class="preset-btn" data-p="30d">최근 30일</button>
  </div>

  <div class="ctrl-sep"></div>

  <!-- 날짜 범위 선택 -->
  <div class="date-range">
    <span class="dr-label">📅</span>
    <input type="text" id="dateRangeInput" placeholder="날짜 범위 선택" readonly>
  </div>

  <div class="ctrl-sep"></div>

  <!-- 매장 필터 -->
  <span class="pills-label">매장</span>
  <div class="store-pills" id="storePills">
    <button class="pill on" id="pillAll">전체</button>
  </div>
</div>

<div class="main" id="main">
  <!-- 렌더링 후 채워짐 -->
</div>

<script>
const ALL_DATA = ${JSON.stringify(allData)};
const STORES   = ['하남','다산','가산','수원','광주','운정'];
const COLORS   = {하남:'#3B82F6',다산:'#10B981',가산:'#F59E0B',수원:'#8B5CF6',광주:'#EF4444',운정:'#06B6D4'};
const DOW      = ['일','월','화','수','목','금','토'];
const HOLIDAYS = new Set([
  // 2025
  '2025-01-01','2025-01-28','2025-01-29','2025-01-30',
  '2025-03-01','2025-05-05','2025-06-06','2025-08-15',
  '2025-10-03','2025-10-05','2025-10-06','2025-10-07','2025-10-09','2025-12-25',
  // 2026
  '2026-01-01','2026-02-17','2026-02-18','2026-02-19',
  '2026-03-01','2026-05-05','2026-05-24','2026-06-06','2026-08-15',
  '2026-09-24','2026-09-25','2026-09-26',
  '2026-10-03','2026-10-09','2026-12-25',
]);
const MONTHS   = Object.keys(ALL_DATA).sort();

let activeStores = new Set(STORES);
let charts = {};

// ── 날짜 유틸 ────────────────────────────────────────────────────────────────
const toStr = d => d.toISOString().slice(0,10);
const today = () => { const d=new Date(); return toStr(d); };
const addDays = (s,n) => toStr(new Date(new Date(s).getTime()+n*864e5));
const subYear = s => { const d=new Date(s); d.setFullYear(d.getFullYear()-1); return toStr(d); };

function presetDates(p) {
  const now = new Date();
  const t = toStr(now);
  if (p==='yesterday') { const y=addDays(t,-1); return [y,y]; }
  if (p==='week') {
    const d=new Date(now); d.setDate(d.getDate()-((d.getDay()+6)%7));
    return [toStr(d), t];
  }
  if (p==='mtd')       return [t.slice(0,7)+'-01', t];
  if (p==='last_month'){
    const d=new Date(now.getFullYear(), now.getMonth()-1, 1);
    const e=new Date(now.getFullYear(), now.getMonth(), 0);
    return [toStr(d), toStr(e)];
  }
  if (p==='30d')       return [addDays(t,-29), t];
  return [t.slice(0,7)+'-01', t];
}

// ── 날짜 범위에서 데이터 추출 ────────────────────────────────────────────────
function getRangeData(start, end) {
  // { store: [row, ...] }
  const res = {};
  STORES.forEach(s => res[s] = []);
  // 문자열 기반 월 순회 (타임존 버그 방지)
  let ym = start.slice(0,7);
  const endM = end.slice(0,7);
  while (ym <= endM) {
    const md = ALL_DATA[ym];
    if (md) {
      STORES.forEach(s => {
        (md[s]||[]).forEach(d => {
          if (d.date >= start && d.date <= end) res[s].push(d);
        });
      });
    }
    const [y, m] = ym.split('-').map(Number);
    ym = m === 12
      ? (y+1) + '-01'
      : y + '-' + String(m+1).padStart(2,'0');
  }
  return res;
}

// 활성 매장만
function activeData(rangeData) {
  const res = {};
  STORES.filter(s=>activeStores.has(s)).forEach(s => res[s] = rangeData[s]||[]);
  return res;
}

// 합계
function sum(data, field) {
  return Object.values(data).flat().reduce((a,d)=>a+(d[field]||0),0);
}

function storeSum(data, s, field) {
  return (data[s]||[]).reduce((a,d)=>a+(d[field]||0),0);
}

// 날짜 범위에 포함된 월들의 전체 월 목표 (날짜 필터 없이 월 전체 합산)
function getMonthlyTargets(start, end) {
  const res = {};
  STORES.forEach(s => res[s] = 0);
  let ym = start.slice(0,7);
  const endM = end.slice(0,7);
  while (ym <= endM) {
    const md = ALL_DATA[ym];
    if (md) STORES.forEach(s => (md[s]||[]).forEach(d => res[s] += (d.target||0)));
    const [y, m] = ym.split('-').map(Number);
    ym = m === 12 ? (y+1)+'-01' : y+'-'+String(m+1).padStart(2,'0');
  }
  return res;
}

// 날짜 목록
function dates(data) {
  const s = new Set();
  Object.values(data).flat().forEach(d => s.add(d.date));
  return [...s].sort();
}

// ── 매장 필터 UI ─────────────────────────────────────────────────────────────
const pillsEl = document.getElementById('storePills');

// 전체 버튼
const allBtn = document.getElementById('pillAll');
function updateAllBtn() {
  const allOn = STORES.every(s => activeStores.has(s));
  allBtn.classList.toggle('on', allOn);
  allBtn.style.background = allOn ? '#1E293B' : '';
  allBtn.style.borderColor = '#1E293B';
  allBtn.style.color = allOn ? '#fff' : '#1E293B';
}
allBtn.addEventListener('click', () => {
  const allOn = STORES.every(s => activeStores.has(s));
  if (allOn) {
    // 전체 해제
    activeStores.clear();
    document.querySelectorAll('.pill[data-store]').forEach(el => {
      el.classList.remove('on');
      el.style.background = '';
    });
  } else {
    // 전체 선택
    STORES.forEach(s => activeStores.add(s));
    document.querySelectorAll('.pill[data-store]').forEach(el => {
      el.classList.add('on');
      el.style.background = COLORS[el.dataset.store] + '22';
    });
  }
  updateAllBtn();
  render();
});

STORES.forEach(s => {
  const el = document.createElement('button');
  el.className = 'pill on';
  el.innerHTML = \`<span class="store-dot" style="background:\${COLORS[s]}"></span>\${s}\`;
  el.style.borderColor = COLORS[s];
  el.style.color = COLORS[s];
  el.dataset.store = s;
  el.addEventListener('click', ()=>{
    if (activeStores.has(s)) {
      activeStores.delete(s);
      el.classList.remove('on');
      el.style.background = '';
    } else {
      activeStores.add(s);
      el.classList.add('on');
    }
    updateAllBtn();
    render();
  });
  pillsEl.appendChild(el);
});
updateAllBtn();

// ── 프리셋 버튼 ──────────────────────────────────────────────────────────────
let curPreset = 'mtd';
document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', ()=>{
    curPreset = btn.dataset.p;
    document.querySelectorAll('.preset-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    const [s,e] = presetDates(curPreset);
    fpStart = s; fpEnd = e;
    picker.setDateRange(s, e);
    render();
  });
});

// ── 날짜 범위 선택 (litepicker - 독립 두달 달력) ────────────────────────────
let fpStart = '', fpEnd = '';
const [defS, defE] = presetDates('mtd');
fpStart = defS; fpEnd = defE;

const picker = new Litepicker({
  element: document.getElementById('dateRangeInput'),
  singleMode: false,
  numberOfMonths: 2,
  numberOfColumns: 2,
  splitView: true,
  lang: 'ko-KR',
  format: 'YYYY-MM-DD',
  startDate: defS,
  endDate: defE,
  setup(p) {
    p.on('selected', (s, e) => {
      fpStart = s.format('YYYY-MM-DD');
      fpEnd   = e.format('YYYY-MM-DD');
      document.querySelectorAll('.preset-btn').forEach(b=>b.classList.remove('active'));
      curPreset = '';
      render();
    });
  }
});

// ── 숫자 포맷 ────────────────────────────────────────────────────────────────
// 숫자 포맷 — 한국어 단위
const _fmt = (n, unit) => {
  const v = Math.floor(n * 10) / 10;
  return (v % 1 === 0 ? v.toLocaleString() : v.toFixed(1)) + unit;
};
const kor  = n => { // 억/만/원 자동, 소수점1자리 버림
  if (n==null) return '-';
  const abs = Math.abs(n);
  if (abs >= 1e8) return _fmt(n/1e7/10, '억');
  if (abs >= 1e4) return _fmt(n/1000/10, '만');
  return n.toLocaleString()+'원';
};
const korW = n => n==null?'-':_fmt(n/1000/10, '만원');
const w    = n => { if(n==null) return '-'; return Math.abs(n)>=1e8 ? _fmt(n/1e8,'억') : _fmt(n/1e4,'만'); };
const n0   = n => n==null?'-':Math.round(n).toLocaleString();
const pct  = (a,b) => (b&&b>0) ? Math.floor(a/b*1000)/10 : null;
const pctSign = n => n==null?'-':(n>=0?'▲':'▼')+(Math.floor(Math.abs(n)*10)/10).toFixed(1)+'%';
const calcProductivity = entries => {
  const v = entries.filter(d=>d.staff&&d.staff>0&&d.sales!=null);
  if (!v.length) return null;
  const s = v.reduce((a,d)=>a+d.sales,0), t = v.reduce((a,d)=>a+d.staff,0);
  return t>0 ? Math.floor(s/t) : null;
};

// ── 차트 정리 ────────────────────────────────────────────────────────────────
function dc(id) { if(charts[id]) { charts[id].destroy(); delete charts[id]; } }

// ── 메인 렌더 ────────────────────────────────────────────────────────────────
function render() {
  const start = fpStart;
  const end   = fpEnd;
  if (!start||!end||start>end) return;

  const rangeData    = getRangeData(start, end);
  const ad           = activeData(rangeData);
  const yStart       = subYear(start);
  const yEnd         = subYear(end);
  const yRangeData   = getRangeData(yStart, yEnd);
  const yad          = activeData(yRangeData);

  const storesArr = STORES.filter(s=>activeStores.has(s));

  // 월 전체 목표 (활성 매장, 날짜 필터 없이)
  const allMT = getMonthlyTargets(start, end);
  const monthlyTargets = {};
  storesArr.forEach(s => monthlyTargets[s] = allMT[s]||0);

  document.getElementById('main').innerHTML = \`
    <div id="sec-pace"></div>
    <div class="row2">
      <div class="card" id="sec-rank"></div>
      <div class="card" id="sec-donut" style="display:flex;flex-direction:column"></div>
    </div>
    <div class="card" id="sec-line"></div>
    <div class="row2b">
      <div class="card" id="sec-prod"></div>
      <div class="card" id="sec-dow"></div>
    </div>
    <div class="card" id="sec-daily"></div>
  \`;

  renderPace(ad, yad, start, end, storesArr, monthlyTargets);
  renderRank(ad, yad, storesArr, monthlyTargets);
  renderDonut(ad, storesArr);
  renderLine(start, end, ad, yad, storesArr);
  renderProd(ad, storesArr);
  renderDow(ad, storesArr);
  renderDailyTable(ad, yad, storesArr);
}

// ── 1. 페이스 카드 ────────────────────────────────────────────────────────────
function renderPace(ad, yad, start, end, stores, monthlyTargets) {
  const totalSales   = sum(ad,'sales');
  const totalTarget  = Object.values(monthlyTargets).reduce((a,v)=>a+v,0);
  const totalReceipts= sum(ad,'receipts');

  const salesDays = [...new Set(Object.values(ad).flat().filter(d=>d.sales!=null).map(d=>d.date))].length;
  const ySales    = sum(yad,'sales');

  const achRate  = pct(totalSales, totalTarget);
  const yoyDelta = ySales>0 ? (totalSales-ySales)/ySales*100 : null;

  // 이번 달 페이스 (MTD 선택 시)
  const todayStr = today();
  const isMtd = start.slice(0,7) === todayStr.slice(0,7) && start === start.slice(0,7)+'-01';
  let paceHtml = '';
  if (isMtd) {
    const yr = +start.slice(0,4), mo = +start.slice(5,7);
    const daysInMonth = new Date(yr, mo, 0).getDate();
    const elapsed = salesDays || 1;

    // 평일/주말 분리 일평균
    const dateSalesMap = {};
    Object.values(ad).flat().forEach(r => {
      if (r.sales != null) dateSalesMap[r.date] = (dateSalesMap[r.date]||0) + r.sales;
    });
    const wdSales = [], weSales = [];
    Object.entries(dateSalesMap).forEach(([dt, s]) => {
      const dow = new Date(dt+'T00:00:00').getDay();
      if (dow===0||dow===6||HOLIDAYS.has(dt)) weSales.push(s);
      else wdSales.push(s);
    });
    const wdAvg = wdSales.length ? wdSales.reduce((a,v)=>a+v,0)/wdSales.length : 0;
    const weAvg = weSales.length ? weSales.reduce((a,v)=>a+v,0)/weSales.length : 0;

    // 잔여 평일/주말 카운트
    let remWd = 0, remWe = 0;
    for (let d = elapsed+1; d <= daysInMonth; d++) {
      const dt = yr+'-'+String(mo).padStart(2,'0')+'-'+String(d).padStart(2,'0');
      const dow = new Date(dt+'T00:00:00').getDay();
      if (dow===0||dow===6||HOLIDAYS.has(dt)) remWe++; else remWd++;
    }
    const projected = Math.floor(totalSales + wdAvg * remWd + weAvg * remWe);
    const remaining = daysInMonth - elapsed;

    paceHtml = \`<div class="pace-item">
      <div class="lbl">월말 예상</div>
      <div class="val" style="font-size:20px">\${kor(projected)}</div>
      <div class="sub">잔여 \${remaining}일 (평일\${remWd}/주말\${remWe}) · 평 \${w(wdAvg)} 휴 \${w(weAvg)}</div>
    </div>\`;
  }

  const fillColor = achRate==null?'#94A3B8':achRate>=100?'#10B981':achRate>=85?'#F59E0B':'#EF4444';

  document.getElementById('sec-pace').innerHTML = \`
    <div class="pace-card">
      <div class="pace-item">
        <div class="lbl">실매출</div>
        <div class="val">\${kor(totalSales)}</div>
        <div class="sub">\${_fmt(totalSales/1e4,'만원')}</div>
        <div class="progress"><div class="progress-fill" style="width:\${Math.min(achRate||0,100)}%;background:\${fillColor}"></div></div>
      </div>
      <div class="pace-item">
        <div class="lbl">목표 달성률</div>
        <div class="val" style="color:\${fillColor}">\${achRate!=null?achRate+'%':'-'}</div>
        <div class="sub">목표 \${kor(totalTarget)}</div>
      </div>
      <div class="pace-item">
        <div class="lbl">영수건수</div>
        <div class="val">\${n0(totalReceipts)}</div>
        <div class="sub">영업일 \${salesDays}일</div>
      </div>
      <div class="pace-item">
        <div class="lbl">전년 대비</div>
        <div class="val" style="font-size:20px;\${yoyDelta!=null&&yoyDelta<0?'color:#EF4444':'color:#10B981'}">\${yoyDelta!=null?(yoyDelta>=0?'▲':'▼')+Math.abs(yoyDelta).toFixed(1)+'%':'-'}</div>
        <div class="sub">전년 \${kor(ySales)}</div>
      </div>
      \${paceHtml}
    </div>
  \`;
  if (isMtd) {
    // 5열로 조정
    document.querySelector('.pace-card').style.gridTemplateColumns='1fr 1fr 1fr 1fr 1fr';
  }
}

// ── 2. 순위 테이블 ────────────────────────────────────────────────────────────
function renderRank(ad, yad, stores, monthlyTargets) {
  const el = document.getElementById('sec-rank');
  el.innerHTML = '<div class="card-title">매장별 실적</div>';

  const rows = stores.map(s => {
    const sales     = storeSum(ad, s, 'sales');
    const target    = monthlyTargets[s] || 0;
    const receipts  = storeSum(ad, s, 'receipts');
    const ySales    = storeSum(yad, s, 'sales');
    const yReceipts = storeSum(yad, s, 'receipts');
    const prod   = calcProductivity(ad[s]||[]);
    const perRec = receipts>0 ? Math.floor(sales/receipts) : null;
    const achR      = pct(sales, target);
    const yoyPct    = ySales>0 ? (sales-ySales)/ySales*100 : null;
    return { s, sales, target, receipts, ySales, yReceipts, prod, perRec, achR, yoyPct };
  }).sort((a,b)=>b.sales-a.sales);

  const tbody = rows.map((r,i)=>{
    const achClass = r.achR==null?'':r.achR>=100?'ach-g':r.achR>=85?'ach-y':'ach-r';
    const ySign    = r.yoyPct==null?'':r.yoyPct>=0?'delta up':'delta dn';
    const noSales  = r.sales===0;
    return \`<tr style="\${noSales?'opacity:.4':''}">
      <td>\${i+1}</td>
      <td><span class="store-dot" style="background:\${COLORS[r.s]}"></span>\${r.s}점</td>
      <td>\${w(r.target)}</td>
      <td>\${w(r.sales)}\${r.yoyPct!=null?'<span class="'+ySign+'">'+pctSign(r.yoyPct)+'</span>':''}</td>
      <td>\${r.achR!=null?'<span class="ach-chip '+achClass+'">'+r.achR+'%</span>':'-'}</td>
      <td>\${n0(r.receipts)}</td>
      <td>\${r.perRec?_fmt(r.perRec/1000,'천원'):'-'}</td>
      <td>\${r.prod?_fmt(r.prod/1e4,'만원'):'-'}</td>
    </tr>\`;
  }).join('');

  el.innerHTML += \`<table class="rank-table">
    <thead><tr>
      <th>#</th><th>매장</th><th>목표</th><th>실매출</th><th>달성%</th>
      <th>영수</th><th>객단가</th><th>인당생산량</th>
    </tr></thead>
    <tbody>\${tbody}</tbody>
  </table>\`;
}

// ── 3. 매출 비중 도넛 ─────────────────────────────────────────────────────────
function renderDonut(ad, stores) {
  dc('donut');
  const el = document.getElementById('sec-donut');
  el.innerHTML = '<div class="card-title">매출 비중</div><div class="donut-wrap"><div class="donut-canvas-wrap"><canvas id="donutCanvas"></canvas></div><div class="donut-legend" id="donutLegend"></div></div>';

  const salesMap = {};
  stores.forEach(s => salesMap[s] = storeSum(ad, s, 'sales'));
  const total = Object.values(salesMap).reduce((a,v)=>a+v,0);

  const ctx = document.getElementById('donutCanvas').getContext('2d');
  charts.donut = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: stores,
      datasets:[{ data: stores.map(s=>salesMap[s]||0), backgroundColor: stores.map(s=>COLORS[s]), borderWidth:2, borderColor:'#fff', hoverOffset:6 }]
    },
    options: {
      responsive:true, maintainAspectRatio:true,
      cutout:'65%',
      plugins:{ legend:{display:false}, tooltip:{callbacks:{label:c=>c.label+': '+w(c.raw)+' ('+pct(c.raw,total)+'%)'}}}
    }
  });

  document.getElementById('donutLegend').innerHTML = stores
    .map(s=>({s,v:salesMap[s]||0}))
    .sort((a,b)=>b.v-a.v)
    .map(({s,v})=>\`
      <div class="dl-item">
        <span class="dl-dot" style="background:\${COLORS[s]}"></span>
        <span class="dl-name">\${s}</span>
        <span class="dl-pct">\${pct(v,total)||0}%</span>
      </div>\`).join('');
}

// ── 4. 일별 트렌드 라인차트 ───────────────────────────────────────────────────
function renderLine(start, end, ad, yad, stores) {
  dc('line');
  const el = document.getElementById('sec-line');
  el.innerHTML = \`
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
      <div class="card-title" style="margin:0">일별 실매출 · 영수건수</div>
      <div class="chart-legend">
        <div class="cl-item"><div class="cl-line" style="background:#3B82F6"></div>실매출</div>
        <div class="cl-item"><div class="cl-line" style="background:#F59E0B"></div>영수건수</div>
        <div class="cl-item"><div class="cl-dashed"></div>전년</div>
      </div>
    </div>
    <div class="chart-wrap h240"><canvas id="lineCanvas"></canvas></div>
  \`;

  // 날짜별 합산
  const dList = dates(ad);
  const yDList= dates(yad);

  const sumByDate=(data,field,dts)=>dts.map(dt=>{
    const v=stores.reduce((a,s)=>{const r=(data[s]||[]).find(d=>d.date===dt);return a+(r&&r[field]!=null?r[field]:0)},0);
    return v>0?v:null;
  });

  // YoY 날짜 대응: yDList와 dList는 같은 순서 (1년 차이)
  const yoyLabels = dList; // x축은 현재 날짜
  const yoySales  = yDList.map(yd=>{
    const v=stores.reduce((a,s)=>{const r=(yad[s]||[]).find(d=>d.date===yd);return a+(r&&r.sales!=null?r.sales:0)},0);
    return v>0?Math.floor(v/1e4*10)/10:null;
  });
  const yoyRec = yDList.map(yd=>{
    const v=stores.reduce((a,s)=>{const r=(yad[s]||[]).find(d=>d.date===yd);return a+(r&&r.receipts!=null?r.receipts:0)},0);
    return v>0?v:null;
  });

  const curSales   = sumByDate(ad,'sales',dList).map(v=>v?Math.floor(v/1e4*10)/10:null);
  const curReceipts= sumByDate(ad,'receipts',dList);

  const ctx = document.getElementById('lineCanvas').getContext('2d');
  charts.line = new Chart(ctx,{
    type:'line',
    data:{
      labels: dList.map(d=>d.slice(5)),
      datasets:[
        { label:'실매출', data:curSales, borderColor:'#3B82F6', backgroundColor:'#3B82F620', borderWidth:2, pointRadius:3, tension:.3, yAxisID:'y', spanGaps:false },
        { label:'전년매출', data:yoySales, borderColor:'#3B82F660', borderDash:[5,4], borderWidth:1.5, pointRadius:2, tension:.3, yAxisID:'y', spanGaps:false },
        { label:'영수건수', data:curReceipts, borderColor:'#F59E0B', backgroundColor:'#F59E0B20', borderWidth:2, pointRadius:3, tension:.3, yAxisID:'y1', spanGaps:false },
        { label:'전년영수', data:yoyRec, borderColor:'#F59E0B60', borderDash:[5,4], borderWidth:1.5, pointRadius:2, tension:.3, yAxisID:'y1', spanGaps:false },
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{ legend:{display:false}, tooltip:{callbacks:{
        label:c=>{
          if(c.dataset.label.includes('매출')) return c.dataset.label+': '+(c.raw!=null?c.raw.toLocaleString()+'만':'-');
          return c.dataset.label+': '+(c.raw!=null?c.raw.toLocaleString()+'건':'-');
        }
      }}},
      scales:{
        x:{ ticks:{font:{size:10},maxRotation:0,color:ctx2=>{
          const dt=dList[ctx2.index];
          if(!dt) return '#64748B';
          const d=new Date(dt), dow=d.getDay();
          return (dow===0||dow===6||HOLIDAYS.has(dt))?'#EF4444':'#64748B';
        }}, grid:{color:'#F1F5F9'} },
        y:{ position:'left', ticks:{font:{size:10},callback:v=>v+'만'}, grid:{color:'#F1F5F9'} },
        y1:{ position:'right', ticks:{font:{size:10},callback:v=>v+'건'}, grid:{display:false} }
      }
    },
    plugins:[{
      id:'wkndBg',
      beforeDraw(chart){
        const {ctx:c,chartArea:{left,right,top,bottom},scales:{x}}=chart;
        dList.forEach((dt,i)=>{
          const d=new Date(dt),dow=d.getDay();
          const isHoliday=HOLIDAYS.has(dt);
          const isWknd=dow===0||dow===6;
          if(!isWknd&&!isHoliday) return;
          const xPos=x.getPixelForValue(i);
          const half=(x.getPixelForValue(1)-x.getPixelForValue(0))/2;
          c.save();
          c.fillStyle=isHoliday&&!isWknd?'#FEF3C720':'#FEE2E230';
          c.fillRect(xPos-half,top,half*2,bottom-top);
          c.restore();
        });
      }
    }]
  });
}

// ── 5. 인당생산량 ─────────────────────────────────────────────────────────────
function renderProd(ad, stores) {
  dc('prod');
  const el = document.getElementById('sec-prod');
  el.innerHTML = '<div class="card-title">지점별 인당생산량</div><div class="chart-wrap h200"><canvas id="prodCanvas"></canvas></div>';

  const prods = stores.map(s => calcProductivity(ad[s]||[]));

  const ctx = document.getElementById('prodCanvas').getContext('2d');
  charts.prod = new Chart(ctx,{
    type:'bar',
    data:{
      labels: stores.map(s=>s+'점'),
      datasets:[{
        label:'인당생산량',
        data: prods,
        backgroundColor: stores.map(s=>COLORS[s]+'CC'),
        borderColor: stores.map(s=>COLORS[s]),
        borderWidth:1.5,
        borderRadius:5,
      }]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{
        legend:{display:false},
        tooltip:{callbacks:{label:c=>c.raw!=null?c.raw.toLocaleString()+'원':'-'}},
        annotation:{}
      },
      scales:{
        x:{ ticks:{font:{size:11,weight:'bold'}}, grid:{display:false} },
        y:{ ticks:{font:{size:10},callback:v=>v>=10000?_fmt(v/1e4,'만'):''+v}, grid:{color:'#F1F5F9'},
            suggestedMin:0, suggestedMax:600000 }
      }
    },
    plugins:[{
      id:'refband',
      beforeDraw(chart){
        const {ctx,chartArea:{left,right,top,bottom},scales:{y}}=chart;
        const y1=y.getPixelForValue(480000), y2=y.getPixelForValue(400000);
        ctx.save();
        ctx.fillStyle='#EF444420';
        ctx.fillRect(left,y1,right-left,y2-y1);
        ctx.strokeStyle='#EF4444';
        ctx.setLineDash([4,3]);
        ctx.lineWidth=1;
        ctx.beginPath();ctx.moveTo(left,y1);ctx.lineTo(right,y1);ctx.stroke();
        ctx.beginPath();ctx.moveTo(left,y2);ctx.lineTo(right,y2);ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }
    }]
  });
}

// ── 6. 요일별 패턴 ───────────────────────────────────────────────────────────
function renderDow(ad, stores) {
  dc('dow');
  const el = document.getElementById('sec-dow');
  el.innerHTML = '<div class="card-title">요일별 평균 매출 · 근무인원</div><div class="chart-wrap h200"><canvas id="dowCanvas"></canvas></div>';

  // 요일별 집계
  const dowSales = Array(7).fill(0), dowCnt=Array(7).fill(0);
  const dowStaff = Array(7).fill(0), dowStaffCnt=Array(7).fill(0);
  stores.forEach(s=>{
    (ad[s]||[]).forEach(d=>{
      if (d.sales==null) return;
      const dow = new Date(d.date).getDay();
      dowSales[dow]+=d.sales; dowCnt[dow]++;
      if (d.staff) { dowStaff[dow]+=d.staff; dowStaffCnt[dow]++; }
    });
  });
  const avgSales = dowSales.map((v,i)=>dowCnt[i]?Math.floor(v/dowCnt[i]/1e4*10)/10:null);
  const avgStaff = dowStaff.map((v,i)=>dowStaffCnt[i]?Math.floor(v/dowStaffCnt[i]*10)/10:null);

  // 월~일 순서로 재배열
  const order=[1,2,3,4,5,6,0];
  const labels=order.map(i=>DOW[i]+'요일');
  const sData =order.map(i=>avgSales[i]);
  const stData=order.map(i=>avgStaff[i]);

  const ctx=document.getElementById('dowCanvas').getContext('2d');
  charts.dow=new Chart(ctx,{
    type:'bar',
    data:{
      labels,
      datasets:[
        { label:'평균매출(만)', data:sData, backgroundColor:'#3B82F6CC', borderColor:'#3B82F6', borderWidth:1.5, borderRadius:4, yAxisID:'y' },
        { type:'line', label:'평균인원', data:stData, borderColor:'#F59E0B', backgroundColor:'#F59E0B22', borderWidth:2, pointRadius:4, pointBackgroundColor:'#F59E0B', tension:.3, yAxisID:'y1' }
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{position:'top',labels:{font:{size:10},padding:8,boxWidth:10}},
        tooltip:{callbacks:{
          label:c=>c.dataset.label.includes('매출')?c.dataset.label+': '+(c.raw!=null?c.raw.toLocaleString()+'만':'-'):c.dataset.label+': '+(c.raw!=null?c.raw+'명':'-')
        }}
      },
      scales:{
        x:{ ticks:{font:{size:11}}, grid:{display:false} },
        y:{ position:'left', ticks:{font:{size:10},callback:v=>v+'만'}, grid:{color:'#F1F5F9'} },
        y1:{ position:'right', ticks:{font:{size:10},callback:v=>v+'명'}, grid:{display:false}, suggestedMin:0 }
      }
    }
  });
}

// ── 7. 일자별 매장 상세 테이블 ──────────────────────────────────────────────
function renderDailyTable(ad, yad, stores) {
  const el = document.getElementById('sec-daily');
  const allDates = dates(ad);
  if (!allDates.length) { el.innerHTML = '<div class="card-title">일자별 매장 데이터</div><div style="color:#94A3B8;padding:12px">데이터 없음</div>'; return; }

  // 합계행 계산
  const totSales    = stores.reduce((a,s)=>a+storeSum(ad,s,'sales'),0);
  const totReceipts = stores.reduce((a,s)=>a+storeSum(ad,s,'receipts'),0);

  // 헤더
  let th = '<th class="dt-th">날짜</th><th class="dt-th">요일</th>';
  stores.forEach(s => { th += \`<th class="dt-th" colspan="2" style="color:\${COLORS[s]}">\${s}</th>\`; });
  th += '<th class="dt-th" colspan="2">합계</th>';

  let subTh = '<th></th><th></th>';
  stores.forEach(() => { subTh += '<th class="dt-sub">매출</th><th class="dt-sub">영수</th>'; });
  subTh += '<th class="dt-sub">매출</th><th class="dt-sub">영수</th>';

  // 데이터 행
  let rows = '';
  allDates.forEach(dt => {
    const dow = DOW[new Date(dt).getDay()];
    const isWknd = new Date(dt).getDay()===0||new Date(dt).getDay()===6;
    let daySales = 0, dayRec = 0;
    let cells = '';
    stores.forEach(s => {
      const r = (ad[s]||[]).find(d=>d.date===dt);
      const sv = r&&r.sales!=null ? r.sales : null;
      const rv = r&&r.receipts!=null ? r.receipts : null;
      if (sv!=null) daySales+=sv;
      if (rv!=null) dayRec+=rv;
      cells += \`<td class="dt-td">\${sv!=null?w(sv):'-'}</td><td class="dt-td">\${rv!=null?n0(rv):'-'}</td>\`;
    });
    rows += \`<tr class="\${isWknd?'dt-wknd':''}">
      <td class="dt-date">\${dt.slice(5)}</td>
      <td class="dt-dow">\${dow}</td>
      \${cells}
      <td class="dt-td dt-sum">\${daySales>0?w(daySales):'-'}</td>
      <td class="dt-td dt-sum">\${dayRec>0?n0(dayRec):'-'}</td>
    </tr>\`;
  });

  // 합계행
  let sumCells = '';
  stores.forEach(s => {
    const sv = storeSum(ad,s,'sales');
    const rv = storeSum(ad,s,'receipts');
    sumCells += \`<td class="dt-td dt-total">\${sv>0?w(sv):'-'}</td><td class="dt-td dt-total">\${rv>0?n0(rv):'-'}</td>\`;
  });

  el.innerHTML = \`
    <div class="card-title">일자별 매장 데이터</div>
    <div style="overflow-x:auto">
      <table class="dt-table">
        <thead>
          <tr>\${th}</tr>
          <tr>\${subTh}</tr>
        </thead>
        <tbody>\${rows}</tbody>
        <tfoot>
          <tr>
            <td class="dt-date dt-total" colspan="2">합계</td>
            \${sumCells}
            <td class="dt-td dt-total">\${totSales>0?w(totSales):'-'}</td>
            <td class="dt-td dt-total">\${totReceipts>0?n0(totReceipts):'-'}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  \`;
}

// ── 초기 실행 ────────────────────────────────────────────────────────────────
render();
</script>
</body>
</html>`;
}

// ── 서버 / 모듈 분기 ────────────────────────────────────────────────────────
if (require.main === module) {
  const server = http.createServer((req, res) => {
    try {
      const data = loadAllData();
      res.writeHead(200, {'Content-Type':'text/html;charset=utf-8'});
      res.end(html(data));
    } catch(e) {
      res.writeHead(500); res.end('Error: '+e.message);
    }
  });
  server.listen(PORT, '127.0.0.1', () => {
    console.log('✓ 대시보드: http://localhost:' + PORT);
    console.log('  Ctrl+C 종료');
  });
} else {
  module.exports = { html, loadAllData };
}
