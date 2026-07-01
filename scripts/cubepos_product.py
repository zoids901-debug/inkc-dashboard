# -*- coding: utf-8 -*-
"""[로컬 전용 / 서버노트북] 큐브포스 → 상품 대시보드(product-dashboard) 수집기.

하남/가산/다산은 큐브포스 전환 → 클라우드(GH Actions)가 IP 차단으로 상품 수집 불가.
주거 IP 로컬에서 큐브포스 상품합산조회(goods-list)를 받아 product-dashboard의
일별 JSON(data/daily/YYMMDD.json)에서 이 3개 매장을 채우고(깃허브 API), 월별 재빌드를 트리거한다.

소스: GET /api/bsn-mst-hq-rtv/goods-list (본사경영분석>전매장 실시간현황>상품합산조회)
매핑: item=gd_nm, code=gd_id, qty=sbg_real_qty, net=sbg_amt(정가), 분류=gdh/gdmj 명 + gdmr_nm

자격증명: keyring cubepos_id/pw + github_pat (env CUBEPOS_ID/PW, GH_PAT/GH_TOKEN 우선)
실행:  py <inkc-dashboard>/scripts/cubepos_product.py
"""
import os
import sys
import json
import base64
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cubepos_lib

KST = timezone(timedelta(hours=9))
PROD_REPO = 'zoids901-debug/product-dashboard'
MIGRATION_START = '2026-07-01'
# 큐브포스 매장코드 → product-dashboard location. INC03-1(에스프레소바)은 다산 합산.
SHOP_TO_LOC = {'INC01': '하남', 'INC02': '가산', 'INC03': '다산', 'INC03-1': '다산'}


def log(*a):
    print('[' + datetime.now(KST).strftime('%H:%M:%S') + '] ' + ' '.join(str(x) for x in a), flush=True)


def get_creds():
    cid = os.environ.get('CUBEPOS_ID')
    cpw = os.environ.get('CUBEPOS_PW')
    pat = os.environ.get('GH_PAT') or os.environ.get('GH_TOKEN')
    try:
        import keyring
        cid = cid or keyring.get_password('zoids', 'cubepos_id')
        cpw = cpw or keyring.get_password('zoids', 'cubepos_pw')
        pat = pat or keyring.get_password('zoids', 'github_pat')
    except Exception:
        pass
    if not (cid and cpw):
        raise SystemExit('큐브포스 자격증명 없음 (keyring cubepos_id/pw 또는 env)')
    if not pat:
        raise SystemExit('github_pat 없음 (keyring github_pat 또는 env GH_PAT)')
    return cid, cpw, pat


def is_valid(name):
    if not name:
        return False
    s = name.replace('*', '').replace('-', '').replace('=', '').replace(' ', '').replace('★', '').replace('☆', '')
    if not s:
        return False
    if name.startswith('**') or name.startswith('--') or name.startswith('=='):
        return False
    return True


class GH:
    def __init__(self, pat):
        self.h = {'Authorization': f'token {pat}', 'User-Agent': 'cubepos-product/1.0',
                  'Accept': 'application/vnd.github+json'}

    def get(self, path):
        api = f'https://api.github.com/repos/{PROD_REPO}/contents/{path}'
        try:
            with urllib.request.urlopen(urllib.request.Request(api, headers=self.h), timeout=20) as r:
                d = json.loads(r.read())
                return d['sha'], json.loads(base64.b64decode(d['content']).decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, None
            raise

    def put(self, path, obj, message, sha=None):
        api = f'https://api.github.com/repos/{PROD_REPO}/contents/{path}'
        content = base64.b64encode(json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).decode()
        for _ in range(3):
            body = {'message': message, 'content': content}
            if sha:
                body['sha'] = sha
            req = urllib.request.Request(api, data=json.dumps(body).encode(),
                                         headers={**self.h, 'Content-Type': 'application/json'}, method='PUT')
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                if e.code == 409:  # sha 충돌 → 다시 읽고 재시도
                    sha, _ = self.get(path)
                    time.sleep(1)
                    continue
                raise

    def dispatch(self, workflow):
        api = f'https://api.github.com/repos/{PROD_REPO}/actions/workflows/{workflow}/dispatches'
        req = urllib.request.Request(api, data=json.dumps({'ref': 'main'}).encode(),
                                     headers={**self.h, 'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status


def cat_maps(session):
    B = cubepos_lib.CUBE_BASE
    def m(url, idk, nmk):
        j = session.get(B + url, timeout=30).json()
        rows = j if isinstance(j, list) else (j.get('data') or [])
        return {r[idk]: r[nmk] for r in rows}
    higher = m('/api/stt_bsn_gd/goods-higher?h_id=INC&s_id=INC01&shop_id=ALL', 'gdh_id', 'gdh_nm')
    major = m('/api/stt_bsn_gd/goods-major?h_id=INC&s_id=INC01&shop_id=ALL&gdh_id=', 'gdmj_id', 'gdmj_nm')
    return higher, major


def fetch_products(session, shop_id, dstr, higher, major):
    """한 매장/하루 상품 리스트 → {item_name: {item,code,qty,net,cat_big,cat_mid,cat_small}}"""
    url = (f'{cubepos_lib.CUBE_BASE}/api/bsn-mst-hq-rtv/goods-list'
           f'?h_id=INC&s_id=INC01&shop_id={shop_id}&fm_dt={dstr}&to_dt={dstr}')
    j = session.get(url, timeout=60).json()
    rows = j if isinstance(j, list) else (j.get('data') or [])
    out = {}
    for r in rows:
        nm = (r.get('gd_nm') or '').strip()
        qty = int(r.get('sbg_real_qty', 0) or 0)
        net = int(r.get('sbg_amt', 0) or 0)  # 정가 총액 = OKPOS TOT_SALE_AMT 대응
        if not is_valid(nm) or net == 0:
            continue
        it = out.get(nm)
        if it:
            it['qty'] += qty
            it['net'] += net
        else:
            out[nm] = {
                'item': nm, 'code': (r.get('gd_id') or '').strip(), 'qty': qty, 'net': net,
                'cat_big': higher.get(r.get('gdh_id'), ''),
                'cat_mid': major.get(r.get('gdmj_id'), ''),
                'cat_small': (r.get('gdmr_nm') or '').strip(),
            }
    return out


def main():
    cid, cpw, pat = get_creds()
    gh = GH(pat)
    log('=== 큐브포스 → 상품 대시보드 수집 시작 ===')
    s = cubepos_lib.login(cid, cpw)
    higher, major = cat_maps(s)

    today = datetime.now(KST).date()
    dates = [d for d in (today, today - timedelta(days=1)) if d.isoformat() >= MIGRATION_START]

    changed = False
    for d in dates:
        dstr = d.strftime('%Y-%m-%d')
        # 매장별 수집(INC03+INC03-1 → 다산 합산)
        by_loc = {}
        for shop_id, loc in SHOP_TO_LOC.items():
            items = fetch_products(s, shop_id, dstr, higher, major)
            dst = by_loc.setdefault(loc, {})
            for nm, it in items.items():
                if nm in dst:
                    dst[nm]['qty'] += it['qty']; dst[nm]['net'] += it['net']
                else:
                    dst[nm] = it
        counts = {loc: len(v) for loc, v in by_loc.items()}
        if not any(counts.values()):
            log(f'{dstr}: 큐브포스 상품 0 — 스킵'); continue

        fname = d.strftime('%y%m%d') + '.json'
        path = f'data/daily/{fname}'
        sha, existing = gh.get(path)
        out = existing or {'date': dstr, 'stores': {}}
        out.setdefault('stores', {})
        for loc, items in by_loc.items():
            out['stores'][loc] = list(items.values())
        gh.put(path, out, f'cubepos-local: 하남/가산/다산 상품 {dstr}', sha=sha)
        log(f'{dstr} 패치: ' + ', '.join(f'{k} {v}종' for k, v in counts.items()))
        changed = True

    if not changed:
        log('변경 없음 — 재빌드 생략'); return

    # 월별 재빌드 트리거 (클라우드 daily-sync: 하남/가산/다산은 건너뛰고 나머지 수집 후 월별 재생성)
    if os.environ.get('SKIP_TRIGGER') != '1':
        try:
            st = gh.dispatch('daily-sync.yml')
            log(f'daily-sync 재빌드 트리거: {st} (204=성공)')
        except Exception as e:
            log(f'재빌드 트리거 실패(야간 자동 재빌드로 반영됨): {e}')
    log('=== 완료 ===')


if __name__ == '__main__':
    main()
