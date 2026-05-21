# -*- coding: utf-8 -*-
"""TOSS(토스플레이스) API 헬퍼 — 운정점 검증 공용 모듈.

product_health.py(일 점검) / product_cross_check.py(월 점검)에서 함께 사용.
필요 환경변수: TOSS_ID, TOSS_PW
"""
import os
import json
import urllib.request

TOSS_BASE = 'https://api-public.tossplace.com'
TOSS_MERCHANT_ID = 304265  # 운정점


def toss_login():
    """TOSS dashboard API 로그인 → accessToken + workspace_id 헤더 dict 반환."""
    tid = os.environ['TOSS_ID']
    tpw = os.environ['TOSS_PW']
    body = {'id': tid, 'password': tpw, 'loginType': 'DASHBOARD_USER'}
    req = urllib.request.Request(
        f'{TOSS_BASE}/api-public/dashboard/v2/auth/login',
        data=json.dumps(body).encode(),
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0',
            'Origin': 'https://dashboard.tossplace.com',
            'Accept': 'application/json',
        }, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    if data.get('resultType') != 'SUCCESS':
        raise RuntimeError(f"TOSS 로그인 실패: {data.get('error')}")
    token = data['success']['accessToken']

    req = urllib.request.Request(
        f'{TOSS_BASE}/api-public/dashboard/v1/workspaces?type=BRAND',
        headers={
            'Authorization': f'Bearer {token}',
            'User-Agent': 'Mozilla/5.0',
            'Origin': 'https://dashboard.tossplace.com',
            'Accept': 'application/json',
        })
    with urllib.request.urlopen(req, timeout=15) as r:
        ws = json.loads(r.read())
    items = (ws.get('success') or {}).get('items') or []
    if not items:
        raise RuntimeError("TOSS workspace(type=BRAND) 없음")
    return {
        'Authorization': f'Bearer {token}',
        'dashboard-workspace-id': str(items[0]['id']),
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0',
        'Origin': 'https://dashboard.tossplace.com',
        'Accept': 'application/json',
    }


def toss_day_net(headers, date_str):
    """해당 일자 운정점 상품 매출(item-sales) → {net, qty, items} 반환.
    net = 정가 매출 합계(amountMoney) — 상품 대시보드와 같은 기준."""
    body = {
        'merchantIds': [TOSS_MERCHANT_ID],
        'dateRange': {'start': date_str, 'end': date_str},
        'aggFields': ['ITEM_SALES'],
    }
    req = urllib.request.Request(
        f'{TOSS_BASE}/dashboard/v1/reports/multivariate/item-sales',
        data=json.dumps(body).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    items = data.get('success', {}).get('data', {}).get('itemSales', []) or []
    net = sum((it.get('content', {}) or {}).get('amountMoney', 0) for it in items)
    qty = sum((it.get('content', {}) or {}).get('transactionCount', 0) for it in items)
    return {'net': net, 'qty': qty, 'items': len(items)}
