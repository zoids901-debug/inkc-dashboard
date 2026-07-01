# -*- coding: utf-8 -*-
"""[로컬 전용 / 서버노트북] 큐브포스 매출 수집기 — 하남/가산/다산.

큐브테크 WAF가 데이터센터 IP를 차단하므로 클라우드(GH Actions)에선 안 됨.
주거 IP를 쓰는 로컬 PC(서버노트북)의 작업 스케줄러로 돌린다.

하는 일:
  1) git pull --rebase (클라우드 ops-sync가 밀어둔 최신 ops_data 받기)
  2) 큐브포스 로그인 → 이번 달(+월초엔 지난달) 하남/가산/다산 매출/영수 수집
  3) ops_data/{YYYY-MM}.json 에 반영
  4) node build.js 로 docs 재생성
  5) 변경 있으면 commit & push

자격증명: keyring cubepos_id/cubepos_pw (없으면 환경변수 CUBEPOS_ID/PW)
필요: git, node, requests, keyring. github push 권한(기존 봇들과 동일 환경 가정).

실행:  py <repo>/scripts/cubepos_local.py
"""
import os
import sys
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cubepos_lib

REPO = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))


def log(*a):
    print('[' + datetime.now(KST).strftime('%H:%M:%S') + '] ' + ' '.join(str(x) for x in a), flush=True)


def get_creds():
    uid = os.environ.get('CUBEPOS_ID')
    pw = os.environ.get('CUBEPOS_PW')
    if uid and pw:
        return uid, pw
    try:
        sys.path.insert(0, r'C:\Users\zoids\Scripts')
        from creds.creds import get_cred
        return get_cred('cubepos_id'), get_cred('cubepos_pw')
    except Exception as e:
        raise SystemExit(f'큐브포스 자격증명 없음(keyring cubepos_id/pw 또는 env CUBEPOS_ID/PW): {e}')


def git(*args, check=True):
    r = subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.stdout.strip(): log('git', args[0], '→', r.stdout.strip()[:200])
    if check and r.returncode != 0:
        raise RuntimeError(f'git {args[0]} 실패: {r.stderr.strip()[:200]}')
    return r


def target_months():
    today = datetime.now(KST).date()
    months = [today.strftime('%Y-%m')]
    if today.day <= 2:  # 월초엔 지난달(어제)도 채움
        prev = (today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
        months.insert(0, prev)
    return months


def main():
    uid, pw = get_creds()
    log('=== 큐브포스 로컬 수집 시작 (repo:', REPO, ') ===')

    # 1) 최신 받기 (rebase; 로컬 변경 없다고 가정)
    try:
        git('fetch', 'origin', '-q')
        git('rebase', 'origin/main', '-q')
    except Exception as e:
        log('rebase 경고(무시하고 진행):', e)

    total = 0
    for ym in target_months():
        p = REPO / 'ops_data' / f'{ym}.json'
        if not p.exists():
            log(f'{ym}.json 없음 — 스킵'); continue
        existing = json.loads(p.read_text(encoding='utf-8'))
        try:
            cube = cubepos_lib.scrape_month(uid, pw, ym, log)
        except Exception as e:
            log(f'{ym} 큐브포스 수집 실패:', e); continue
        n = cubepos_lib.apply_to_existing(cube, existing, log)
        if n:
            p.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
            log(f'{ym}: {n}건 반영 저장')
            total += n

    if total == 0:
        log('반영 건수 0 — 커밋 생략'); return

    # 4) 빌드
    r = subprocess.run(['node', 'build.js'], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        log('build.js 실패:', r.stderr.strip()[:300]); return
    log('build.js OK')

    # 5) commit & push (충돌 시 rebase 후 1회 재시도)
    git('add', 'ops_data', 'docs')
    st = git('status', '--porcelain', check=False)
    if not st.stdout.strip():
        log('변경 없음 — 커밋 생략'); return
    stamp = datetime.now(KST).strftime('%Y-%m-%d %H:%M')
    git('commit', '-q', '-m', f'auto(cubepos-local): 하남/가산/다산 매출 반영 ({stamp} KST)')
    push = git('push', 'origin', 'HEAD:main', check=False)
    if push.returncode != 0:
        log('push 재시도(rebase 후)...')
        git('fetch', 'origin', '-q'); git('rebase', 'origin/main', '-q')
        git('push', 'origin', 'HEAD:main')
    log('=== 완료: push 성공 ===')


if __name__ == '__main__':
    main()
