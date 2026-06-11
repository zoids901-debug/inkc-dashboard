// /api/bot — 통합 대시보드 채팅 위젯 → 서버 노트북 Vanna 봇(/api/ask) 중계 프록시.
//   위젯이 POST {q, hist} 로 부르면, 집 노트북의 Vanna 봇으로 넘기고 표 결과를 돌려준다.
//   봇은 집 네트워크 안 → cloudflared quick 터널의 공개 주소로만 닿는다.
//
//   봇 주소(BOT_URL) 출처:
//     - 1순위 KV 바인딩 BOT_KV['BOT_URL'] — 서버 노트북 tunnel_sync.py가 터널 뜰 때마다 실시간 기록.
//       (Pages env는 변경이 다음 배포부터라, 주소가 자주 바뀌는 값은 KV로 둬서 재배포 없이 즉시 반영)
//     - 2순위 env.BOT_URL — KV 비었을 때 폴백.
//   Pages 환경변수:
//     BOT_SECRET = 봇이 검증할 공유 비밀. 있으면 X-Bot-Secret 헤더로 전달.
//
//   안전: 봇이 꺼졌거나 주소 미설정이어도 위젯이 안 깨지게 항상 200 + {error 친절문}.
//   Vanna 응답 형식: { sql, columns, rows, note } 또는 { error }.

export async function onRequest(context) {
  const { request, env } = context;

  const json = (obj, status = 200) =>
    new Response(JSON.stringify(obj), {
      status,
      headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
    });

  // 질문/맥락 받기: POST {q, hist} 우선, 없으면 GET ?q= (단순 호출 호환)
  let q = '', hist = [];
  if (request.method === 'POST') {
    try {
      const body = await request.json();
      q = (body.q || '').trim();
      hist = Array.isArray(body.hist) ? body.hist.slice(-2) : [];
    } catch (_) {}
  } else {
    q = (new URL(request.url).searchParams.get('q') || '').trim();
  }

  if (!q) return json({ error: '질문을 입력해 주세요.' });

  // 봇 주소: KV(BOT_KV, 터널이 실시간 갱신) 우선 → env.BOT_URL 폴백.
  let base = '';
  try { if (env.BOT_KV) base = (await env.BOT_KV.get('BOT_URL')) || ''; } catch (_) {}
  if (!base) base = env.BOT_URL || '';
  base = base.replace(/\/+$/, '');
  if (!base) return json({ error: '봇 서버 주소가 아직 설정되지 않았어요. (서버 노트북에서 터널을 켜면 자동 연결됩니다)' });

  const headers = { 'content-type': 'application/json', 'accept': 'application/json' };
  if (env.BOT_SECRET) headers['X-Bot-Secret'] = env.BOT_SECRET;

  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 30000);
    const r = await fetch(base + '/api/ask', {
      method: 'POST',
      headers,
      body: JSON.stringify({ q, hist }),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (!r.ok) return json({ error: '봇이 잠시 응답하지 않아요. (상태 ' + r.status + ')' });
    const data = await r.json(); // { sql, columns, rows, note } 또는 { error }
    return json(data);
  } catch (e) {
    return json({ error: '봇 서버에 연결할 수 없어요. 서버(서브 노트북)가 켜져 있는지 확인해 주세요.' });
  }
}
