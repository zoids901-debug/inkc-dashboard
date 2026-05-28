// 공통 + 탭 라우팅 + 운영 대시보드 패턴의 기간/매장 컨트롤
(function () {
  'use strict';

  window.App = window.App || {};
  App.util = {
    comma: (n) => (n == null ? '-' : Number(n).toLocaleString('ko-KR')),
    M: (n) => (n == null ? '-' : (Math.round(n / 1e4) / 100).toLocaleString('ko-KR') + 'M'),
  };

  // ── 매장 정의 (탭 그룹별로 다름) ─────
  const STORE_SETS = {
    inkc: {  // 운영/상품/손익 탭 공용
      stores: ['하남','다산','가산','수원','광주','운정'],
      colors: { 하남:'#3B82F6', 다산:'#10B981', 가산:'#F59E0B', 수원:'#8B5CF6', 광주:'#EF4444', 운정:'#06B6D4' },
      open:   { '하남':'2021-05-29','가산':'2021-09-09','다산':'2023-12-21','수원':'2024-01-24','광주':'2024-03-21','운정':'2025-12-03' },
    },
    tablin: {  // 테이블린 탭
      stores: ['다산점','하남점','운정점'],
      colors: { '다산점':'#3B82F6','하남점':'#10B981','운정점':'#F59E0B' },
      open:   {},
    },
  };
  // 손익 탭은 브랜드 그룹 pill — 브랜드 → PL 매장명 (새 매장 추가 시 여기 갱신)
  const PL_BRANDS = {
    '인크':     ['미사점','가산점','가산팩토리','다산점','수원점','광주점','운정점'],
    '테이블린': ['테이블린하남','테이블린다산','테이블린운정'],
    '극장':     ['롯데시네마 하남점','CGV'],
    '본사':     ['본사'],
  };
  const PL_BRAND_COLOR = { '인크':'#8B5CF6', '테이블린':'#EF4444', '극장':'#3B82F6', '본사':'#64748B' };
  const PL_ALL_STORES = Object.values(PL_BRANDS).flat();
  App.PL_BRANDS = PL_BRANDS;

  // 현재 탭에 맞는 매장 셋 (showTab → App.setStoreSetForTab 에서 갱신)
  let STORES = STORE_SETS.inkc.stores;
  let COLORS = STORE_SETS.inkc.colors;
  let STORE_OPEN = STORE_SETS.inkc.open;
  App.STORE_SETS = STORE_SETS;
  App.STORES = STORES;
  App.COLORS = COLORS;
  App.STORE_OPEN = STORE_OPEN;

  // ── 전역 상태 ─────────────────────────────────
  App.state = {
    period: { preset: 'mtd', start: null, end: null },
    activeStores: new Set(STORE_SETS.inkc.stores),    // 운영/상품 탭용 (인크 6개)
    tablinStores: new Set(STORE_SETS.tablin.stores),  // 테이블린 탭용
    plStores: new Set(PL_ALL_STORES),                 // 손익 탭용 (브랜드 그룹, PL 매장명)
    activeTab: null,
  };
  // 현재 탭의 활성 매장 Set
  const curStoreSet = () => (
    App.state.activeTab === 'tablin' ? App.state.tablinStores :
    App.state.activeTab === 'pl'     ? App.state.plStores :
    App.state.activeStores
  );
  App.curStoreSet = curStoreSet;
  App.events = new EventTarget();

  // ── 날짜 유틸 ─────────────────────────────────
  const toStr = d => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + day;
  };
  const fmt = s => s ? s.replaceAll('-', '.') : '';

  // 월 시작 / 월 끝 헬퍼
  const monthStart = (d) => { const x = new Date(d); x.setDate(1); return x; };
  const monthEnd   = (d) => { const x = new Date(d); x.setMonth(x.getMonth()+1, 0); return x; };

  function computePeriod(preset) {
    const now = new Date();
    let start, end;
    switch(preset) {
      case 'yesterday': {
        const d = new Date(now); d.setDate(d.getDate()-1);
        start = end = d; break;
      }
      case 'week': {
        const d = new Date(now);
        const dow = d.getDay() || 7;  // 1=월 ~ 7=일
        d.setDate(d.getDate() - dow + 1);
        start = d; end = now; break;
      }
      case 'mtd': {
        start = monthStart(now); end = now; break;
      }
      case 'last_month': {
        const d = new Date(now); d.setMonth(d.getMonth()-1);
        start = monthStart(d); end = monthEnd(d); break;
      }
      case '30d': {
        const d = new Date(now); d.setDate(d.getDate()-29);
        start = d; end = now; break;
      }
      case '3m': {
        const d = new Date(now); d.setMonth(d.getMonth()-2);
        start = monthStart(d); end = now; break;
      }
      case '6m': {
        const d = new Date(now); d.setMonth(d.getMonth()-5);
        start = monthStart(d); end = now; break;
      }
      case 'ytd': {
        start = new Date(now.getFullYear(), 0, 1); end = now; break;
      }
      case 'last_year': {
        const y = now.getFullYear() - 1;
        start = new Date(y, 0, 1); end = new Date(y, 11, 31); break;
      }
      default: {
        // 분기: 'q1'~'q4' (올해), 'ly_q1'~'ly_q4' (작년)
        const mTY = /^q([1-4])$/.exec(preset);
        const mLY = /^ly_q([1-4])$/.exec(preset);
        if (mTY || mLY) {
          const q = parseInt((mTY || mLY)[1], 10);
          const y = (mLY ? now.getFullYear() - 1 : now.getFullYear());
          start = new Date(y, (q - 1) * 3, 1);
          end = new Date(y, q * 3, 0);  // 분기 마지막 날
          if (end > now) end = now;     // 미래 구간은 오늘까지로 절단
          if (start > now) return null; // 아직 시작도 안 한 분기
          break;
        }
        return null;
      }
    }
    return { preset, start: toStr(start), end: toStr(end) };
  }
  App.computePeriod = computePeriod;

  function setPeriod(period) {
    App.state.period = period;
    document.querySelectorAll('.preset-btn').forEach(b => {
      let on = b.dataset.p === period.preset;
      // 분기 선택 시 해당 연도 버튼(올해/작년) 활성 유지
      if (!on && b.dataset.p === 'ytd' && /^q[1-4]$/.test(period.preset)) on = true;
      if (!on && b.dataset.p === 'last_year' && /^ly_q[1-4]$/.test(period.preset)) on = true;
      b.classList.toggle('active', on);
    });
    const inp = document.getElementById('dateRangeInput');
    if (inp) inp.value = `${fmt(period.start)} ~ ${fmt(period.end)}`;
    App.events.dispatchEvent(new CustomEvent('period', { detail: period }));
    // 로드된 iframe 모두 동기화
    syncAllFrames();
  }

  // ── 탭 라우팅 (lazy iframe 로드) ──────────────
  const TABS = ['ops', 'product', 'pl', 'tablin'];
  // 'tablin'은 HIDE_SELECTORS/syncFrame 케이스 없음 — 자체 헤더·컨트롤 그대로 노출

  // 각 iframe 내부에서 숨길 selector (제목 + 자체 필터바) — 통합 헤더·컨트롤바를 쓰므로
  const HIDE_SELECTORS = {
    product: '.hdr, .sticky-bar',
    ops:     '.hdr, .ctrl-bar',
    pl:      '.header, .sel-card',
    tablin:  '.hdr, .ctrl-bar',  // 테이블린 자체 타이틀 + 컨트롤바 숨김 → 통합 컨트롤바가 구동
  };

  // 탭별 추가 주입 CSS (헤더 숨김 후 레이아웃 보정 등)
  const EXTRA_INJECT_CSS = {};

  function injectFrameStyles(name, frame) {
    try {
      const doc = frame.contentDocument;
      if (!doc) return;
      const sel = HIDE_SELECTORS[name];
      if (!sel) return;
      let style = doc.getElementById('__unified_inject_style');
      if (!style) {
        style = doc.createElement('style');
        style.id = '__unified_inject_style';
        doc.head.appendChild(style);
      }
      style.textContent = `
        ${sel} { display: none !important; }
        body { padding-top: 0 !important; }
        .wrap, .container, .main { padding-top: 12px !important; }
        ${EXTRA_INJECT_CSS[name] || ''}
      `;
    } catch (e) {
      console.warn('[App] frame style inject failed:', e);
    }
  }

  // ============================================================
  // postMessage 기반 동기화 (additive — 기존 syncFrame과 공존)
  //
  // 프로토콜:
  //  - 자식 → 부모: {type:'inkc:ready', tab:'...'}        (페이지 준비됨)
  //  - 부모 → 자식: {type:'inkc:sync', payload:{...}}     (동기화 명령)
  //  - 자식 → 부모: {type:'inkc:synced', tab:'...'}       (적용 완료)
  //
  // 자식이 응답 있는 탭은 postMessage 경로, 없는 탭은 기존 글로벌 set 경로(fallback).
  // ============================================================
  const _pmReady = new Set();   // postMessage 지원 확인된 탭
  const _pmAckTimers = {};      // 각 탭별 응답 대기 타이머

  function _pmTabFromOrigin(originUrl) {
    // 어느 탭의 iframe에서 온 메시지인지 src로 식별
    for (const name of TABS) {
      const panel = document.getElementById(`tab-${name}`);
      if (!panel) continue;
      const frame = panel.querySelector('iframe.tab-frame');
      if (frame && frame.contentWindow && originUrl === frame.contentWindow) return name;
    }
    return null;
  }

  window.addEventListener('message', (e) => {
    const msg = e.data;
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'inkc:ready' && msg.tab) {
      _pmReady.add(msg.tab);
      // ready 직후 1회 sync 시도 (그래야 자식이 막 로드됐을 때도 상태 받음)
      const panel = document.getElementById(`tab-${msg.tab}`);
      const frame = panel && panel.querySelector('iframe.tab-frame');
      if (frame) _trySyncViaPostMessage(msg.tab, frame);
    }
    if (msg.type === 'inkc:synced' && msg.tab) {
      if (_pmAckTimers[msg.tab]) {
        clearTimeout(_pmAckTimers[msg.tab]);
        delete _pmAckTimers[msg.tab];
      }
    }
  });

  function _buildSyncPayload(name) {
    const period = App.state.period;
    if (!period || !period.start) return null;
    const isTablin = (name === 'tablin');
    const isPL = (name === 'pl');
    let stores;
    if (isTablin) stores = [...App.state.tablinStores];
    else if (isPL) stores = [...App.state.plStores];
    else stores = [...App.state.activeStores];
    return {
      tab: name,
      period: { start: period.start, end: period.end, preset: period.preset || '' },
      stores,
    };
  }

  function _trySyncViaPostMessage(name, frame) {
    if (!_pmReady.has(name)) return false;  // 자식이 아직 ready 안 보냄
    if (!frame || !frame.contentWindow) return false;
    const payload = _buildSyncPayload(name);
    if (!payload) return false;
    try {
      frame.contentWindow.postMessage({ type: 'inkc:sync', payload }, '*');
    } catch (e) {
      console.warn(`[App] postMessage(${name}) failed:`, e);
      return false;
    }
    // 1초 내 inkc:synced 응답 없으면 fallback 호출
    if (_pmAckTimers[name]) clearTimeout(_pmAckTimers[name]);
    _pmAckTimers[name] = setTimeout(() => {
      delete _pmAckTimers[name];
      console.warn(`[App] postMessage(${name}) 응답 없음 — fallback 사용`);
      _pmReady.delete(name);   // 다음부턴 처음부터 fallback 시도
      syncFrame(name, frame);
    }, 1000);
    return true;
  }

  function lazyLoadFrame(name) {
    const panel = document.getElementById(`tab-${name}`);
    if (!panel) return;
    // 서브탭 있으면 첫 번째 visible 패널에서 iframe 찾음
    const visibleSub = panel.querySelector('.subtab-panel:not([hidden])');
    const frame = (visibleSub || panel).querySelector('iframe.tab-frame');
    if (!frame) return;
    if (!frame.src && frame.dataset.src) {
      // 캐시 우회: 페이지 로드 시점 timestamp를 쿼리로 붙여서 매번 새 fetch
      const baseSrc = frame.dataset.src;
      const sep = baseSrc.includes('?') ? '&' : '?';
      frame.src = baseSrc + sep + 'v=' + Date.now();
      frame.addEventListener('load', () => {
        injectFrameStyles(name, frame);
        setTimeout(() => syncFrame(name, frame), 800);
      }, { once: false });
    } else {
      injectFrameStyles(name, frame);
      syncFrame(name, frame);
    }
  }

  // iframe 안의 글로벌 스코프에서 코드 실행 (script 주입 방식 — let/const 변수 접근 가능)
  function runInFrame(frame, code) {
    const doc = frame.contentDocument;
    if (!doc || !doc.body) return false;
    try {
      const s = doc.createElement('script');
      s.textContent = code;
      doc.body.appendChild(s);
      doc.body.removeChild(s);
      return true;
    } catch (e) {
      console.warn('[App] runInFrame failed:', e);
      return false;
    }
  }


  // ── iframe 동기화 (탭별 다른 필터 메커니즘 처리) ──────
  function syncFrame(name, frame) {
    // postMessage 경로 사용 가능하면 그걸로 (응답 없으면 fallback)
    if (_pmReady.has(name) && _trySyncViaPostMessage(name, frame)) return;

    const period = App.state.period;
    if (!period || !period.start) return;
    const doc = frame.contentDocument;
    if (!doc) return;

    // 매장 상태 — 프레임(탭)별 셋이 다름 (인크 6개 vs 테이블린 3개)
    const isTablin = (name === 'tablin');
    const stores = [...(isTablin ? App.state.tablinStores : App.state.activeStores)];
    const isAllStores = stores.length === (isTablin ? STORE_SETS.tablin.stores : STORE_SETS.inkc.stores).length;

    try {
      if (name === 'product') {
        // 새 API 우선: loadDateRange가 있으면 일/월 자동 분기
        const win = frame.contentWindow;
        const hasNewAPI = win && typeof win.loadDateRange === 'function';
        if (!hasNewAPI) {
          // product-dashboard 아직 로딩 중 — 잠시 후 재시도
          const mf = doc.getElementById('month-from');
          if (!mf || mf.options.length < 2) {
            setTimeout(() => syncFrame(name, frame), 800);
            return;
          }
        }
        runInFrame(frame, `
          try {
            // selStores 먼저 갱신
            if (typeof selStores !== 'undefined') {
              selStores.clear();
              ${isAllStores ? '' : `${JSON.stringify(stores)}.forEach(s => selStores.add(s));`}
              const lbl = document.getElementById('store-label');
              if (lbl) lbl.textContent = selStores.size===0 ? '' : '● ' + [...selStores].join(' + ') + ' 보는 중';
            }
            // 새 API: loadDateRange가 일/월 자동 분기
            if (typeof loadDateRange === 'function') {
              loadDateRange('${period.start}', '${period.end}');
            } else if (typeof onRangeChange === 'function') {
              // fallback: 기존 select 기반
              const mf = document.getElementById('month-from');
              const mt = document.getElementById('month-to');
              if (mf && mt) {
                const fromYM = '${period.start.slice(0,7)}';
                const toYM   = '${period.end.slice(0,7)}';
                const yymmFrom = fromYM.slice(2,4) + fromYM.slice(5,7);
                const yymmTo   = toYM.slice(2,4) + toYM.slice(5,7);
                const find = (el, cands) => {
                  for (const c of cands) for (const o of el.options) if (o.value === c) return c;
                  const sorted = [...el.options].map(o=>o.value).filter(v=>v).sort();
                  let best = sorted[0];
                  for (const v of sorted) if (v <= cands[cands.length-1]) best = v;
                  return best;
                };
                mf.value = find(mf, [fromYM+'.json', yymmFrom+'.json', fromYM, yymmFrom]);
                mt.value = find(mt, [toYM+'.json',   yymmTo+'.json',   toYM,   yymmTo]);
                onRangeChange();
              }
            }
          } catch (e) { console.warn('[product sync]', e); }
        `);
      }
      else if (name === 'ops') {
        runInFrame(frame, `
          try {
            if (typeof picker !== 'undefined' && picker.setDateRange) {
              picker.setDateRange('${period.start}', '${period.end}');
            }
            if (typeof fpStart !== 'undefined') fpStart = '${period.start}';
            if (typeof fpEnd !== 'undefined') fpEnd = '${period.end}';
            if (typeof curPreset !== 'undefined') curPreset = '${period.preset || ''}';
            if (typeof activeStores !== 'undefined') {
              activeStores.clear();
              ${JSON.stringify(stores)}.forEach(s => activeStores.add(s));
              if (typeof updateAllBtn === 'function') updateAllBtn();
              // 내부 pill 색칠 갱신
              document.querySelectorAll('.pill[data-store]').forEach(el => {
                if (activeStores.has(el.dataset.store)) {
                  el.classList.add('on');
                  el.style.background = (typeof COLORS !== 'undefined' && COLORS[el.dataset.store]) ? COLORS[el.dataset.store] + '22' : '';
                } else {
                  el.classList.remove('on');
                  el.style.background = '';
                }
              });
            }
            if (typeof render === 'function') render();
          } catch (e) { console.warn('[ops sync]', e); }
        `);
      }
      else if (name === 'pl') {
        // PL 형식: selYears = Set('YYYY'), selMonths = Set('M월') (비우면 전체 월)
        const [sY, sM] = period.start.slice(0, 7).split('-').map(Number);
        const [eY, eM] = period.end.slice(0, 7).split('-').map(Number);
        const yearArr = []; for (let y = sY; y <= eY; y++) yearArr.push(String(y));
        // 같은 해 안의 범위면 그 월들을 push → 분기/월 프리셋이 PL에도 먹힘.
        // 여러 해에 걸치면 selMonths 비움(전체 월) — 연도×월 교차 오선택 방지.
        let monthArr = [];
        if (sY === eY) for (let mo = sM; mo <= eM; mo++) monthArr.push(mo + '월');
        const plStores = [...App.state.plStores];
        const isAllPL = plStores.length === PL_ALL_STORES.length;
        runInFrame(frame, `
          try {
            if (typeof selYears !== 'undefined') {
              selYears.clear();
              ${JSON.stringify(yearArr)}.forEach(y => selYears.add(y));
            }
            if (typeof selMonths !== 'undefined') {
              selMonths.clear();
              ${JSON.stringify(monthArr)}.forEach(m => selMonths.add(m));
            }
            if (typeof selStores !== 'undefined') {
              selStores.clear();
              ${isAllPL ? '' : `${JSON.stringify(plStores)}.forEach(s => selStores.add(s));`}
            }
            if (typeof buildYearChecks === 'function') buildYearChecks();
            if (typeof buildMonthChecks === 'function') buildMonthChecks();
            if (typeof buildStorePanel === 'function') buildStorePanel();
            if (typeof updateAll === 'function') updateAll();
          } catch (e) { console.warn('[pl sync]', e); }
        `);
      }
      else if (name === 'tablin') {
        const cw = frame.contentWindow;
        // 테이블린 로딩(data.json fetch) 완료 전이면 잠시 후 재시도 (DATA.records 가 채워졌는지로 판정)
        if (!cw || typeof cw.render !== 'function' || !cw.DATA || !cw.DATA.records || !cw.DATA.records.length) {
          setTimeout(() => syncFrame(name, frame), 800);
          return;
        }
        // stores 는 이미 테이블린 지점명(다산점/하남점/운정점). 비면 전체.
        const tStores = stores.length ? stores : STORE_SETS.tablin.stores.slice();
        runInFrame(frame, `
          try {
            fpStart = '${period.start}'; fpEnd = '${period.end}';
            activeStores = new Set(${JSON.stringify(tStores)});
            render();
          } catch (e) { console.warn('[tablin sync]', e); }
        `);
      }
    } catch (e) {
      console.warn(`[App] syncFrame(${name}) failed:`, e);
    }
  }

  // 모든 로드된 iframe 동기화
  function syncAllFrames() {
    TABS.forEach(name => {
      const panel = document.getElementById(`tab-${name}`);
      const frame = panel?.querySelector('iframe.tab-frame');
      if (frame && frame.src) syncFrame(name, frame);
    });
  }
  function showTab(name) {
    if (!TABS.includes(name)) name = 'ops';
    App.state.activeTab = name;
    if (App.setStoreSetForTab) App.setStoreSetForTab(name);  // 인크 ↔ 테이블린 매장 pill 교체
    document.body.dataset.tab = name;  // CSS에서 일 단위 프리셋 숨김에 활용
    document.querySelectorAll('.hdr-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.tab-panel').forEach(p => {
      p.hidden = (p.id !== `tab-${name}`);
    });
    lazyLoadFrame(name);
    if (location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);
    App.events.dispatchEvent(new CustomEvent('tabchange', { detail: name }));

    // 탭별 호환/기본 프리셋 자동 보정
    const cur = App.state.period?.preset;
    let targetPreset = null;
    // 손익: 단기 프리셋(어제·이번 주·이번 달)이면 올해(ytd)로 자동 변경
    if (name === 'pl' && (cur === 'yesterday' || cur === 'week' || cur === 'mtd')) {
      targetPreset = 'ytd';
    }
    // 운영: 장기 프리셋(3·6개월)이면 이번 달로
    if (name === 'ops' && (cur === '3m' || cur === '6m')) {
      targetPreset = 'mtd';
    }
    if (targetPreset && targetPreset !== cur) {
      const p = computePeriod(targetPreset);
      if (p) {
        App._programmaticPicker = true;
        try { if (App.picker?.setDateRange) App.picker.setDateRange(p.start, p.end); }
        finally { App._programmaticPicker = false; }
        setPeriod(p);
      }
    }
  }
  App.showTab = showTab;

  // ── 초기화 ───────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {

    // 탭 클릭
    document.querySelectorAll('.hdr-tab').forEach(b => {
      b.addEventListener('click', () => showTab(b.dataset.tab));
    });

    // 엑셀 다운로드 (현재 탭의 iframe 내부 함수 호출)
    const excelBtn = document.getElementById('btnExcelUnified');
    if (excelBtn) {
      excelBtn.addEventListener('click', () => {
        const tab = App.state.activeTab || 'ops';
        if (tab === 'pl') {
          alert('손익 탭은 엑셀 다운로드가 별도 시트에서 제공됩니다');
          return;
        }
        const panel = document.getElementById(`tab-${tab}`);
        const frame = panel && panel.querySelector('iframe.tab-frame');
        if (!frame || !frame.contentWindow) {
          alert('탭 iframe을 찾지 못했습니다');
          return;
        }
        try {
          const fn = frame.contentWindow.downloadExcel;
          if (typeof fn !== 'function') {
            alert('현재 탭은 엑셀 다운로드 미지원');
            return;
          }
          fn();
        } catch (e) {
          alert('엑셀 다운로드 실패: ' + e.message);
        }
      });
    }

    // VAT 포함/제외 토글 — 운영 탭 iframe의 applyVatMode + render 호출
    const vatBtn = document.getElementById('btnVatUnified');
    if (vatBtn) {
      vatBtn.addEventListener('click', () => {
        const panel = document.getElementById('tab-ops');
        const frame = panel && panel.querySelector('iframe.tab-frame');
        if (!frame || !frame.contentWindow) { alert('운영 iframe을 찾지 못했습니다'); return; }
        try {
          const w = frame.contentWindow;
          if (typeof w.applyVatMode !== 'function') { alert('운영 탭 로딩 중입니다 — 잠시 후 다시'); return; }
          // 스크롤 위치 보존 (render가 main을 통째로 다시 그려서 리셋됨)
          const scY = w.scrollY, scX = w.scrollX;
          w.VAT_MODE = w.VAT_MODE === 'incl' ? 'excl' : 'incl';
          w.applyVatMode();
          // 라벨은 "VAT 제외" 고정 (액션 라벨). 활성 시 색만 강조 (=적용중)
          if (w.VAT_MODE === 'excl') {
            vatBtn.style.background = '#3B82F6'; vatBtn.style.borderColor = '#3B82F6'; vatBtn.style.color = '#fff';
          } else {
            vatBtn.style.background = '#fff'; vatBtn.style.borderColor = '#CBD5E1'; vatBtn.style.color = '#475569';
          }
          if (typeof w.render === 'function') w.render();
          // 렌더 직후 동기 복원 + 다음 프레임 한 번 더 (차트 lazy 그리기 시 흔들림 방지)
          w.scrollTo(scX, scY);
          w.requestAnimationFrame(() => w.scrollTo(scX, scY));
        } catch (e) {
          alert('VAT 토글 실패: ' + e.message);
        }
      });
    }

    // 서브탭 (손익 → 대시보드/업로드)
    document.querySelectorAll('.subtab').forEach(b => {
      b.addEventListener('click', () => {
        const target = b.dataset.subtab;
        b.parentElement.querySelectorAll('.subtab').forEach(sb =>
          sb.classList.toggle('active', sb === b)
        );
        const section = b.closest('.tab-panel');
        section.querySelectorAll('.subtab-panel').forEach(p => {
          p.hidden = !p.id.endsWith(target);
        });
        // lazy load 업로드 iframe
        const frame = section.querySelector(`#pl-${target} iframe`);
        if (frame && !frame.src && frame.dataset.src) {
          frame.src = frame.dataset.src;
        }
      });
    });
    window.addEventListener('hashchange', () => {
      const t = (location.hash || '#ops').slice(1);
      if (t !== App.state.activeTab) showTab(t);
    });

    // ── 분기 드롭다운 (올해/작년) ──────────────────
    const popup = document.getElementById('presetPopup');
    function applyPreset(presetKey) {
      const p = computePeriod(presetKey);
      if (!p) return;
      App._programmaticPicker = true;
      try { if (App.picker && App.picker.setDateRange) App.picker.setDateRange(p.start, p.end); }
      finally { App._programmaticPicker = false; }
      setPeriod(p);
    }
    function closeQuarterPopup() { if (popup) { popup.hidden = true; popup.innerHTML = ''; popup.dataset.base = ''; } }
    function openQuarterPopup(btn, base) {
      if (!popup) return;
      const isLY = (base === 'last_year');
      const yearLabel = isLY ? '작년' : '올해';
      const wholeKey = base; // 'ytd' or 'last_year'
      const qKey = (q) => isLY ? `ly_q${q}` : `q${q}`;
      const cur = App.state.period?.preset;
      const now = new Date();
      popup.innerHTML = '';
      popup.dataset.base = base;
      const mkOpt = (key, text, disabled) => {
        const b = document.createElement('button');
        b.className = 'q-opt' + (cur === key ? ' active' : '');
        b.textContent = text;
        if (disabled) b.disabled = true;
        else b.addEventListener('click', () => { applyPreset(key); closeQuarterPopup(); });
        return b;
      };
      popup.appendChild(mkOpt(wholeKey, `${yearLabel} 전체`));
      const div = document.createElement('div'); div.className = 'q-divider'; popup.appendChild(div);
      for (let q = 1; q <= 4; q++) {
        // 올해의 미래 분기(아직 시작 안 함)는 비활성
        const qStartDate = new Date((isLY ? now.getFullYear() - 1 : now.getFullYear()), (q - 1) * 3, 1);
        const disabled = !isLY && qStartDate > now;
        popup.appendChild(mkOpt(qKey(q), `${q}분기 (${q*3-2}~${q*3}월)`, disabled));
      }
      // 위치: 버튼 바로 아래 (fixed → 뷰포트 기준)
      popup.hidden = false;
      const r = btn.getBoundingClientRect();
      popup.style.left = Math.round(r.left) + 'px';
      popup.style.top  = Math.round(r.bottom + 4) + 'px';
    }
    document.addEventListener('click', (e) => {
      if (popup && !popup.hidden && !popup.contains(e.target) && !e.target.closest('.preset-btn.has-quarter, .pill.brand-pill')) closeQuarterPopup();
    });

    // 올해/작년 버튼에 마우스 올리면 분기 팝업 (버튼↔팝업 사이 이동 시 닫히지 않게 딜레이)
    let _qTimer = null;
    const _qClear = () => { if (_qTimer) { clearTimeout(_qTimer); _qTimer = null; } };
    const _qCloseSoon = () => { _qClear(); _qTimer = setTimeout(closeQuarterPopup, 220); };
    document.querySelectorAll('.preset-btn.has-quarter').forEach(b => {
      b.addEventListener('mouseenter', () => { _qClear(); openQuarterPopup(b, b.dataset.p); });
      b.addEventListener('mouseleave', _qCloseSoon);
    });
    if (popup) {
      popup.addEventListener('mouseenter', _qClear);
      popup.addEventListener('mouseleave', _qCloseSoon);
    }

    // 프리셋 버튼
    document.querySelectorAll('.preset-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.p;
        const p = computePeriod(key);
        if (!p) return;
        App._programmaticPicker = true;
        try { if (App.picker && App.picker.setDateRange) App.picker.setDateRange(p.start, p.end); }
        finally { App._programmaticPicker = false; }
        setPeriod(p);
        // 올해/작년 → 분기 드롭다운 열기 (전체 기간으로 설정 + 분기 선택지 제공)
        if (btn.classList.contains('has-quarter')) openQuarterPopup(btn, key);
        else closeQuarterPopup();
      });
    });

    // 매장 pills
    const pillsEl = document.getElementById('storePills');
    const allBtn = document.getElementById('pillAll');

    function emitStores(set) {
      App.events.dispatchEvent(new CustomEvent('stores', { detail: [...set] }));
      syncAllFrames();
    }
    function updateAllBtn() {
      const set = curStoreSet();
      const ref = (App.state.activeTab === 'pl') ? PL_ALL_STORES : STORES;
      const allOn = ref.every(s => set.has(s));
      allBtn.classList.toggle('on', allOn);
      allBtn.style.background = allOn ? '#1E293B' : '';
      allBtn.style.borderColor = '#1E293B';
      allBtn.style.color = allOn ? '#fff' : '#1E293B';
    }
    allBtn.addEventListener('click', () => {
      const set = curStoreSet();
      const ref = (App.state.activeTab === 'pl') ? PL_ALL_STORES : STORES;
      if (ref.every(s => set.has(s))) set.clear(); else ref.forEach(s => set.add(s));
      buildPills(); updateAllBtn(); emitStores(set);
    });

    // ── flat pill (운영/상품/테이블린): 매장 1개당 1개 ──
    // 단축: 클릭=토글, 더블클릭=단독(solo), Shift+클릭=페어 비교
    let _pillClickTimer = null;
    function buildFlatPills() {
      const set = curStoreSet();
      STORES.forEach(s => {
        const on = set.has(s);
        const el = document.createElement('button');
        el.className = 'pill' + (on ? ' on' : '');
        el.innerHTML = `<span class="store-dot" style="background:${COLORS[s]}"></span>${s}`;
        el.style.borderColor = COLORS[s];
        el.style.color = on ? COLORS[s] : '#94A3B8';
        el.style.background = on ? COLORS[s] + '22' : '';
        el.dataset.store = s;
        const hints = [];
        if (STORE_OPEN[s]) hints.push(`오픈 ${STORE_OPEN[s]}`);
        hints.push('클릭=토글 · 더블클릭=단독 · Shift+클릭=페어');
        el.title = hints.join(' · ');
        el.addEventListener('click', (e) => {
          const isShift = e.shiftKey;
          if (_pillClickTimer) return; // 더블클릭 처리 중이면 무시
          _pillClickTimer = setTimeout(() => {
            _pillClickTimer = null;
            const cs = curStoreSet();
            if (isShift) {
              // 페어 모드: 클릭한 매장 + 현재 활성된 매장 중 첫번째(자기 제외) 둘만 유지
              const partner = [...cs].find(x => x !== s);
              cs.clear();
              if (partner) cs.add(partner);
              cs.add(s);
            } else {
              if (cs.has(s)) cs.delete(s); else cs.add(s);
            }
            buildPills(); updateAllBtn(); emitStores(cs);
          }, 220);
        });
        el.addEventListener('dblclick', () => {
          if (_pillClickTimer) { clearTimeout(_pillClickTimer); _pillClickTimer = null; }
          const cs = curStoreSet();
          cs.clear(); cs.add(s);
          buildPills(); updateAllBtn(); emitStores(cs);
        });
        pillsEl.appendChild(el);
      });
    }

    // ── 브랜드 그룹 pill (손익): 인크/테이블린/극장/본사 + 마우스오버 시 지점 선택 팝업 ──
    function buildBrandPills() {
      const set = App.state.plStores;
      for (const brand of Object.keys(PL_BRANDS)) {
        const brStores = PL_BRANDS[brand];
        const onCnt = brStores.filter(s => set.has(s)).length;
        const allOn = onCnt === brStores.length, someOn = onCnt > 0;
        const color = PL_BRAND_COLOR[brand] || '#64748B';
        const el = document.createElement('button');
        el.className = 'pill brand-pill' + (allOn ? ' on' : someOn ? ' partial' : '');
        el.dataset.brand = brand;
        el.style.borderColor = color;
        el.style.color = (allOn || someOn) ? color : '#94A3B8';
        el.style.background = allOn ? color + '22' : someOn ? color + '11' : '';
        el.innerHTML = `<span class="store-dot" style="background:${color}"></span>${brand}` +
          (someOn && !allOn && brStores.length > 1 ? ` <span class="brand-cnt">${onCnt}/${brStores.length}</span>` : '') +
          (brStores.length > 1 ? ` <span class="q-caret">▾</span>` : '');
        el.addEventListener('click', () => {
          const turnOn = !brStores.every(s => set.has(s));
          brStores.forEach(s => turnOn ? set.add(s) : set.delete(s));
          closeQuarterPopup();
          buildPills(); updateAllBtn(); emitStores(set);
        });
        if (brStores.length > 1) {
          el.addEventListener('mouseenter', () => { _qClear(); openBrandPopup(el, brStores); });
          el.addEventListener('mouseleave', _qCloseSoon);
        }
        pillsEl.appendChild(el);
      }
    }
    function openBrandPopup(btn, brStores) {
      if (!popup) return;
      const set = App.state.plStores;
      popup.innerHTML = '';
      brStores.forEach(s => {
        const b = document.createElement('button');
        b.className = 'q-opt' + (set.has(s) ? ' on' : '');
        b.textContent = s;
        b.addEventListener('click', () => {
          if (set.has(s)) set.delete(s); else set.add(s);
          b.classList.toggle('on', set.has(s));
          buildPills(); updateAllBtn(); emitStores(set);
        });
        popup.appendChild(b);
      });
      popup.hidden = false;
      const r = btn.getBoundingClientRect();
      popup.style.left = Math.round(r.left) + 'px';
      popup.style.top  = Math.round(r.bottom + 4) + 'px';
    }

    function buildPills() {
      pillsEl.querySelectorAll('.pill[data-store], .pill[data-brand]').forEach(el => el.remove());
      if (App.state.activeTab === 'pl') buildBrandPills();
      else buildFlatPills();
    }
    buildPills();
    updateAllBtn();

    // 탭 전환 시 pill 모드 교체 (인크 6개 ↔ 테이블린 3개 ↔ 손익 브랜드그룹)
    let _pillKey = 'inkc';
    App.setStoreSetForTab = (tab) => {
      const key = (tab === 'pl') ? 'pl' : (tab === 'tablin') ? 'tablin' : 'inkc';
      if (key === _pillKey) return;
      _pillKey = key;
      if (key !== 'pl') {
        const want = (tab === 'tablin') ? STORE_SETS.tablin : STORE_SETS.inkc;
        STORES = want.stores; COLORS = want.colors; STORE_OPEN = want.open;
        App.STORES = STORES; App.COLORS = COLORS; App.STORE_OPEN = STORE_OPEN;
      }
      buildPills();
      updateAllBtn();
    };

    // Litepicker
    if (window.Litepicker) {
      const def = computePeriod('mtd');
      const picker = new Litepicker({
        element: document.getElementById('dateRangeInput'),
        singleMode: false,
        numberOfMonths: 2,
        numberOfColumns: 2,
        splitView: true,
        lang: 'ko-KR',
        format: 'YYYY-MM-DD',
        startDate: def.start,
        endDate: def.end,
        dropdowns: { minYear: 2021, maxYear: null, months: true, years: true },
        setup(p) {
          p.on('selected', (s, e) => {
            // 프로그램이 picker.setDateRange() 호출했을 때는 무시
            if (App._programmaticPicker) return;
            setPeriod({ preset: 'custom', start: s.format('YYYY-MM-DD'), end: e.format('YYYY-MM-DD') });
          });
        }
      });
      App.picker = picker;
    }

    // 초기 기간: 이번 달
    setPeriod(computePeriod('mtd'));

    // 초기 탭
    const t = (location.hash || '#ops').slice(1);
    showTab(t);
  });

  App.fetchJson = async (url) => {
    const r = await fetch(url + (url.includes('?') ? '&' : '?') + 't=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status} on ${url}`);
    return r.json();
  };

  console.log('[App] shared.js loaded');
})();
