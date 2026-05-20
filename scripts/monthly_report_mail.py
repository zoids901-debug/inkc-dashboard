# -*- coding: utf-8 -*-
"""월간 종합 보고서 메일 — 매월 1일 직전 월 backfill 후 발송.

내용:
- 직전 월 매장별 매출 + raw vs 대시보드 일치 여부
- 매장×연도별 누적 합계 (yearly_cross_check.json)
- 직전 월 시계열 이상치 일자
"""
import os, json, smtplib
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
OPS_DIR = REPO_ROOT / "ops_data"
RAW_DIR = OPS_DIR / "raw_okpos"
YCC_PATH = OPS_DIR / "yearly_cross_check.json"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
TO_ADDR = os.environ.get("MAIL_TO", "zoids@ink-korea.co.kr")

STORES = ['가산', '다산', '수원', '하남', '광주', '운정']


def w(v):
    if not v: return "0원"
    a = abs(v); s = '-' if v < 0 else ''
    if a >= 1e8:
        uk = int(a / 1e8); man = int((a % 1e8) / 1e4)
        return f'{s}{uk}억 {man:,}만원' if man else f'{s}{uk}억원'
    if a >= 1e4:
        return f'{s}{int(a/1e4):,}만원'
    return f'{s}{int(a):,}원'


def prev_month():
    today = date.today()
    first = today.replace(day=1)
    last_of_prev = first - timedelta(days=1)
    return f'{last_of_prev.year:04d}-{last_of_prev.month:02d}', last_of_prev


def build_product_section(pcc):
    """상품 대시보드 검증 섹션 — product_cross_check.json 기반."""
    if not pcc or not pcc.get('results'):
        return ""
    by_store_year = defaultdict(dict)
    for r in pcc['results']:
        by_store_year[r['store']][r['year']] = r
    years = sorted(set(r['year'] for r in pcc['results']))
    prod_stores = ['가산', '다산', '수원', '하남', '광주', '운정']
    header = '<th style="padding:8px 10px;background:#F8FAFC;border-bottom:2px solid #E2E8F0;text-align:left">매장</th>'
    for y in years:
        header += f'<th style="padding:8px 10px;background:#F8FAFC;border-bottom:2px solid #E2E8F0;text-align:right">{y}</th>'
    rows = ""
    for store in prod_stores:
        if store not in by_store_year:
            continue
        row = f'<tr><td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;font-weight:600">{store}점</td>'
        for y in years:
            r = by_store_year[store].get(y)
            if not r:
                row += '<td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;text-align:right;color:#CBD5E1">—</td>'
                continue
            color = {"ok": "#10B981", "warn": "#F59E0B", "bad": "#EF4444"}.get(r['level'], "#64748B")
            icon = {"ok": "✓", "warn": "⚠", "bad": "✗"}.get(r['level'], "·")
            row += (f'<td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;text-align:right;'
                    f'font-variant-numeric:tabular-nums" title="{r.get("message","")}">'
                    f'<span style="color:{color}">{icon}</span> {w(r.get("prod_total",0))}</td>')
        row += '</tr>'
        rows += row
    return f"""
      <h3 style="color:#334155;margin:24px 0 8px;font-size:15px">상품 대시보드 검증 (OK포스 상품별 매출현황 = 정가 기준)</h3>
      <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #E2E8F0;border-radius:6px;overflow:hidden">
        <thead><tr>{header}</tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <div style="font-size:11px;color:#94A3B8;margin-top:6px">상품 대시보드는 할인·부가세 미적용 정가 → OK포스 원본과 0원 일치가 정상</div>"""


def build_html(prev_ym, prev_last_date, ycc, raw_data, ops_data, pcc=None):
    # 직전 월 매장별 매출 + 일치 여부
    rows_prev = ""
    for store in STORES:
        raw_records = (raw_data or {}).get(store, [])
        ops_records = (ops_data or {}).get(store, [])
        raw_sum = sum((r.get('sales') or 0) for r in raw_records)
        ops_sum = sum((r.get('sales') or 0) for r in ops_records)
        diff = ops_sum - raw_sum
        if raw_sum == 0:
            note = "raw 없음 (backfill 전)"
            match_icon = "·"; color = "#94A3B8"
        elif abs(diff) < 100_000:
            note = "raw와 대시보드 일치"
            match_icon = "✓"; color = "#10B981"
        else:
            note = f"차이 {w(abs(diff))}"
            match_icon = "✗"; color = "#EF4444"
        rows_prev += f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;color:{color};font-weight:700;width:30px">{match_icon}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;font-weight:600">{store}점</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;text-align:right;font-variant-numeric:tabular-nums">{w(ops_sum)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;color:#64748B;font-size:12px">{note}</td>
        </tr>"""

    # 매장×연도 누적 표
    yearly_rows = ""
    by_store_year = defaultdict(dict)
    if ycc and ycc.get('results'):
        for r in ycc['results']:
            by_store_year[r['store']][r['year']] = r
        years = sorted(set(r['year'] for r in ycc['results']))
        header = '<th style="padding:8px 10px;background:#F8FAFC;border-bottom:2px solid #E2E8F0;text-align:left">매장</th>'
        for y in years:
            header += f'<th style="padding:8px 10px;background:#F8FAFC;border-bottom:2px solid #E2E8F0;text-align:right">{y}</th>'
        for store in STORES:
            if store not in by_store_year: continue
            row = f'<tr><td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;font-weight:600">{store}점</td>'
            for y in years:
                r = by_store_year[store].get(y)
                if not r:
                    row += '<td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;text-align:right;color:#CBD5E1">—</td>'
                    continue
                lv = r.get('level', 'ok')
                color = {"ok":"#10B981","warn":"#F59E0B","bad":"#EF4444","info":"#0EA5E9","no_raw":"#94A3B8"}.get(lv, "#64748B")
                icon = {"ok":"✓","warn":"⚠","bad":"✗","info":"ⓘ","no_raw":"?"}.get(lv, "·")
                row += f'<td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;text-align:right;font-variant-numeric:tabular-nums" title="{r.get(\"message\",\"\")}"><span style="color:{color}">{icon}</span> {w(r.get(\"ops_total\",0))}</td>'
            row += '</tr>'
            yearly_rows += row
        yearly_section = f"""
      <h3 style="color:#334155;margin:24px 0 8px;font-size:15px">매장 × 연도 누적 매출 (OK포스 raw 기반 검증)</h3>
      <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #E2E8F0;border-radius:6px;overflow:hidden">
        <thead><tr>{header}</tr></thead>
        <tbody>{yearly_rows}</tbody>
      </table>
      <div style="font-size:11px;color:#94A3B8;margin-top:6px">✓ 일치 / ⓘ fallback 매장 / ⚠ 의심 / ✗ 큰 차이 / ? raw 없음</div>"""
    else:
        yearly_section = ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:#F8FAFC;padding:20px;color:#1E293B">
  <div style="max-width:720px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #E2E8F0">

    <div style="background:#1E293B;color:#fff;padding:16px 20px">
      <div style="font-size:20px;font-weight:700">📊 {prev_ym} 월간 종합 보고서</div>
      <div style="font-size:12px;opacity:0.9;margin-top:4px">인크커피 데이터 건강검진 · {prev_ym} 직전 월 OK포스 raw 재fetch + 대시보드 비교</div>
    </div>

    <div style="padding:20px">
      <h3 style="color:#334155;margin:0 0 8px;font-size:15px">{prev_ym} 매장별 합계 (OK포스 raw ↔ 운영 대시보드)</h3>
      <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #E2E8F0;border-radius:6px;overflow:hidden">
        {rows_prev}
      </table>

      {yearly_section}

      {build_product_section(pcc)}

      <div style="margin-top:24px;padding-top:16px;border-top:1px solid #E2E8F0;color:#94A3B8;font-size:11px;line-height:1.6">
        검사 시각: {datetime.now().isoformat(timespec='seconds')}<br>
        매월 2일 KST 04:00 자동 실행 · 직전 월 OK포스 재fetch + 매장×연도 누적 검증<br>
        대시보드: <a href="https://zoids901-debug.github.io/inkc-dashboard/" style="color:#0EA5E9">inkc-dashboard.github.io</a>
      </div>
    </div>
  </div>
</body></html>"""


def main():
    if not SMTP_USER or not SMTP_PASS:
        print("SMTP credentials 없음 — 발송 생략"); return

    prev_ym, prev_last = prev_month()
    print(f"직전 월: {prev_ym}")

    raw_path = RAW_DIR / f"{prev_ym}.json"
    ops_path = OPS_DIR / f"{prev_ym}.json"
    raw_data = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else {}
    ops_data = json.loads(ops_path.read_text(encoding="utf-8")) if ops_path.exists() else {}
    ycc = json.loads(YCC_PATH.read_text(encoding="utf-8")) if YCC_PATH.exists() else {}
    pcc_path = OPS_DIR / "product_cross_check.json"
    pcc = json.loads(pcc_path.read_text(encoding="utf-8")) if pcc_path.exists() else {}

    html = build_html(prev_ym, prev_last, ycc, raw_data, ops_data, pcc)
    subject = f"[인크 월간보고] 📊 {prev_ym} 매장별 합계 + 매장×연도 누적 검증"

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = TO_ADDR
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(html, "html", "utf-8"))

    print(f"메일 발송: {TO_ADDR}")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, [TO_ADDR], msg.as_string())
    print("발송 완료")


if __name__ == "__main__":
    main()
