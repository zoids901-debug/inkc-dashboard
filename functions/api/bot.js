// GET /api/bot?q=<질문>
//   통합 대시보드 채팅 위젯 → 서브 노트북 봇 서버(/ask) 로 중계하는 프록시.
//   봇 서버는 집 네트워크 안(localhost:8765) → cloudflared 터널의 공개 URL로만 닿는다.
//
//   Cloudflare Pages 환경변수(Preview/Production 각각 설정):
//     BOT_URL    = 터널 공개 주소 (예: https://xxxx.trycloudflare.com)  ※ 끝 슬래시 없이
//     BOT_SECRET = 봇이 검증할 공유 비밀(선택). 있으면 X-Bot-Secret 헤더로 전달.
//
//   안전: 봇이 꺼져 있거나 BOT_URL 미설정이어도 위젯이 깨지지 않게
//         항상 200 + {text} 로 친절한 메시지를 돌려준다(대시보드 영향 0).

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const q = (url.searchParams.get('q') || '').trim();

  const reply = (text, extra = {}) =>
    new Response(JSON.stringify({ text, kind: 'proxy', ...extra }), {
      status: 200,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'no-store',
      },
    });

  if (!q) return reply('질문을 입력해 주세요.');

  const base = (env.BOT_URL || '').replace(/\/+$/, '');
  if (!base) {
    return reply('봇 서버 주소가 아직 설정되지 않았어요. (관리자: Pages 환경변수 BOT_URL)');
  }

  const headers = { 'accept': 'application/json' };
  if (env.BOT_SECRET) headers['X-Bot-Secret'] = env.BOT_SECRET;

  const target = base + '/ask?q=' + encodeURIComponent(q);
  try {
    // 첫 질문은 로컬 AI 모델 로딩으로 ~15초 걸릴 수 있어 넉넉히.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 25000);
    const r = await fetch(target, { headers, signal: ctrl.signal });
    clearTimeout(timer);
    if (!r.ok) return reply('봇이 잠시 응답하지 않아요. (상태 ' + r.status + ')');
    const data = await r.json();
    // 봇 응답 형식 { text, sql, kind } 그대로 전달.
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'no-store',
      },
    });
  } catch (e) {
    return reply('봇 서버에 연결할 수 없어요. 서버(서브 노트북)가 켜져 있는지 확인해 주세요.');
  }
}
