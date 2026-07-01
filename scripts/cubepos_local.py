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
import socket
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cubepos_lib

REPO = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))

# 서버노트북 생존/성공 심장박동. 클라우드 점검 메일(health_mail.py)이 이 파일을 읽어
# "마지막 성공 N시간 전" 신호로 서버노트북 상태를 표시한다.
STATUS_PATH = REPO / 'ops_data' / 'cubepos_status.json'
STALE_HOURS = 3  # 조용한(반영 0) 정상 실행은 이 간격마다만 심장박동 갱신(커밋 잡음 방지)


def log(*a):
    print('[' + datetime.now(KST).strftime('%H:%M:%S') + '] ' + ' '.join(str(x) for x in a), flush=True)


def get_creds():
    uid = os.environ.get('CUBEPOS_ID')
    pw = os.environ.get('CUBEPOS_PW')
    if uid and pw:
        return uid, pw
    # 이식성: keyring 직접 사용(어느 PC든 동일 서비스명 'zoids'). Scripts 경로 무의존.
    try:
        import keyring
        uid = keyring.get_password('zoids', 'cubepos_id')
        pw = keyring.get_password('zoids', 'cubepos_pw')
        if uid and pw:
            return uid, pw
    except Exception as e:
        raise SystemExit(f'keyring 조회 실패: {e}')
    raise SystemExit('큐브포스 자격증명 없음 — keyring(zoids/cubepos_id·cubepos_pw) 또는 env(CUBEPOS_ID/PW) 등록 필요')


def git(*args, check=True):
    r = subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.stdout.strip(): log('git', args[0], '→', r.stdout.strip()[:200])
    if check and r.returncode != 0:
        raise RuntimeError(f'git {args[0]} 실패: {r.stderr.strip()[:200]}')
    return r


def read_prev_status():
    try:
        return json.loads(STATUS_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}


def hours_since(kst_str):
    try:
        dt = datetime.strptime(kst_str, '%Y-%m-%d %H:%M').replace(tzinfo=KST)
        return (datetime.now(KST) - dt).total_seconds() / 3600
    except Exception:
        return 1e9


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

    prev = read_prev_status()
    now = datetime.now(KST)
    status = {
        'host': socket.gethostname(),
        'last_run_kst': now.strftime('%Y-%m-%d %H:%M'),
        'last_success_kst': prev.get('last_success_kst'),  # 성공 시 아래에서 갱신
        'applied_last': 0,
        'error': None,
    }

    # 1) 최신 받기 (rebase; 로컬 변경 없다고 가정)
    try:
        git('fetch', 'origin', '-q')
        git('rebase', 'origin/main', '-q')
    except Exception as e:
        log('rebase 경고(무시하고 진행):', e)

    total = 0
    err = None
    for ym in target_months():
        p = REPO / 'ops_data' / f'{ym}.json'
        if not p.exists():
            log(f'{ym}.json 없음 — 스킵'); continue
        existing = json.loads(p.read_text(encoding='utf-8'))
        try:
            cube = cubepos_lib.scrape_month(uid, pw, ym, log)
        except Exception as e:
            err = f'{type(e).__name__}: {e}'
            log(f'{ym} 큐브포스 수집 실패:', e); continue
        n = cubepos_lib.apply_to_existing(cube, existing, log)
        if n:
            p.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
            log(f'{ym}: {n}건 반영 저장')
            total += n

    # 심장박동 갱신: 오류 없이 끝났으면 성공 시각 갱신, 아니면 오류 기록
    if err is None:
        status['last_success_kst'] = now.strftime('%Y-%m-%d %H:%M')
        status['applied_last'] = total
    else:
        status['error'] = err
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')

    # 커밋 여부 결정:
    #  - 데이터 반영 있음 → 커밋(심장박동 동승)
    #  - 반영 0 & 정상 → 마지막 커밋된 성공이 STALE_HOURS 넘게 오래됐을 때만 심장박동 갱신 커밋
    #  - 반영 0 & 실패 → 커밋 안 함(커밋된 성공시각이 자연히 오래돼 메일이 '마지막 성공 N시간 전'으로 잡아냄)
    should_commit = False
    if total > 0:
        should_commit = True
    elif err is None:
        ps = prev.get('last_success_kst')
        if (not ps) or hours_since(ps) >= STALE_HOURS:
            should_commit = True

    if not should_commit:
        # 트리 정리(다음 실행 rebase가 dirty로 실패하지 않게 심장박동 변경 되돌림)
        git('checkout', '--', 'ops_data/cubepos_status.json', check=False)
        reason = '수집 실패' if err else f'반영 0 & 최근 {STALE_HOURS}h 내 성공'
        log(f'커밋 생략({reason}).')
        if err:
            raise SystemExit(1)  # 스케줄러 로그/이력에 실패로 남김
        return

    # 4) 빌드 (node 필요, 데이터 바뀐 경우만). 실패해도 데이터는 잃지 않게 커밋은 진행.
    if total > 0:
        try:
            r = subprocess.run(['node', 'build.js'], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8', errors='replace')
            if r.returncode != 0:
                log('⚠ build.js 실패(데이터는 커밋함, docs 재생성은 다음 실행/노드설치 후):', r.stderr.strip()[:200])
            else:
                log('build.js OK')
        except FileNotFoundError:
            log('⚠ node 없음 — docs 미빌드(데이터만 커밋). 서버노트북에 node 설치 권장.')

    # 5) commit & push (충돌 시 rebase 후 1회 재시도)
    git('add', 'ops_data', 'docs')
    st = git('status', '--porcelain', check=False)
    if not st.stdout.strip():
        log('변경 없음 — 커밋 생략'); return
    stamp = now.strftime('%Y-%m-%d %H:%M')
    msg = (f'auto(cubepos-local): 하남/가산/다산 매출 반영 ({stamp} KST)' if total > 0
           else f'chore(cubepos-local): 수집기 심장박동 갱신 ({stamp} KST)')
    git('commit', '-q', '-m', msg)
    push = git('push', 'origin', 'HEAD:main', check=False)
    if push.returncode != 0:
        log('push 재시도(rebase 후)...')
        git('fetch', 'origin', '-q'); git('rebase', 'origin/main', '-q')
        git('push', 'origin', 'HEAD:main')
    log('=== 완료: push 성공 ===')


if __name__ == '__main__':
    main()
