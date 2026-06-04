# -*- coding: utf-8 -*-
"""인케이코리아 통합(애그리게이터) dist 빌드 — CI/로컬 공용.

통합셸 + 운영(ops-only) + 상품(product) + 손익(pl) + 테이블린(tablin)을
한 dist/ 폴더(같은 출처 하위경로)로 합친다. Cloudflare Pages 한 프로젝트로 배포.

소스 위치(기본값, 환경변수로 덮어쓰기 가능):
  SELF       = .                      (이 repo: docs/, ops_data/health.json)
  SRC_PRODUCT= _src/product-dashboard
  SRC_PL     = _src/pl-dashboard
  SRC_TABLIN = _src/tablin-dashboard
출력: ./dist
"""
import os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
SELF = os.environ.get('SELF', ROOT)
SRC_PRODUCT = os.environ.get('SRC_PRODUCT', os.path.join(ROOT, '_src', 'product-dashboard'))
SRC_PL = os.environ.get('SRC_PL', os.path.join(ROOT, '_src', 'pl-dashboard'))
SRC_TABLIN = os.environ.get('SRC_TABLIN', os.path.join(ROOT, '_src', 'tablin-dashboard'))
DIST = os.environ.get('DIST', os.path.join(ROOT, 'dist'))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def copytree(src, dst):
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('.git', '.github'))


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    # 1) 셸 + 운영(ops-only): docs/* → dist/
    copytree(os.path.join(SELF, 'docs'), DIST)
    health = os.path.join(SELF, 'ops_data', 'health.json')
    if os.path.exists(health):
        shutil.copy2(health, os.path.join(DIST, 'health.json'))

    # 2~4) 상품 / 손익 / 테이블린
    copytree(SRC_PRODUCT, os.path.join(DIST, 'product'))
    copytree(SRC_PL, os.path.join(DIST, 'pl'))
    copytree(SRC_TABLIN, os.path.join(DIST, 'tablin'))

    open(os.path.join(DIST, '.nojekyll'), 'w').close()

    # 5) 셸 index.html 경로 재작성 (github.io 절대경로 → 같은-출처 하위경로)
    idx = os.path.join(DIST, 'index.html')
    html = open(idx, encoding='utf-8').read()
    repl = [
        ('https://zoids901-debug.github.io/product-dashboard/', '/product/'),
        ('https://zoids901-debug.github.io/inkc-dashboard/ops-only/', '/ops-only/'),
        ('https://zoids901-debug.github.io/tablin-dashboard/', '/tablin/'),
        ('https://raw.githubusercontent.com/zoids901-debug/inkc-dashboard/main/ops_data/health.json',
         '/health.json'),
    ]
    for a, b in repl:
        if a not in html:
            print(f'  WARN 셸에서 못 찾음(스킵): {a}')
        html = html.replace(a, b)

    # 6) 손익 탭: 🔒 잠금 카드 → iframe 임베드 복원 (같은 출처라 임베드 가능)
    new_pl = ('  <section id="tab-pl" class="tab-panel" hidden>\n'
              '    <iframe class="tab-frame" data-src="/pl/" loading="lazy"></iframe>\n'
              '  </section>')
    pl_pat = re.compile(r'  <section id="tab-pl".*?</section>', re.S)
    if pl_pat.search(html):
        html = pl_pat.sub(new_pl, html, count=1)
    else:
        print('  WARN 손익 섹션 패턴 못 찾음 — 임베드 복원 실패')
    open(idx, 'w', encoding='utf-8').write(html)

    # 검증
    nfiles = sum(len(f) for _, _, f in os.walk(DIST))
    print(f'OK dist 빌드 완료: {DIST} (파일 {nfiles}개)')
    h = open(idx, encoding='utf-8').read()
    for token in ['data-src="/product/"', 'data-src="/ops-only/"',
                  'data-src="/pl/"', 'data-src="/tablin/"', "'/health.json'"]:
        print(f'   {"OK" if token in h else "MISSING"}  {token}')
    if 'github.io' in h:
        print('  WARN 셸에 github.io 잔존:', h.count('github.io'))
        sys.exit(1)


if __name__ == '__main__':
    main()
