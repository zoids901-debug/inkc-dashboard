# -*- coding: utf-8 -*-
"""데이터 건강검진 결과를 zoids@ink-korea.co.kr로 메일 발송.
Gmail SMTP 사용 — 환경변수 SMTP_USER, SMTP_PASS 필요.

실행: data-health.yml 워크플로우의 마지막 step
"""
import os, json, smtplib, urllib.request
from datetime import date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from pathlib import Path

TABLIN_HEALTH_URL = 'https://raw.githubusercontent.com/zoids901-debug/tablin-dashboard/main/health.json'


def fetch_tablin_health():
    """테이블린 저장소의 health.json을 가져옴 (실패해도 인크 메일은 정상 발송)."""
    try:
        req = urllib.request.Request(TABLIN_HEALTH_URL, headers={'User-Agent': 'inkc-mail'})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f'테이블린 health.json 못 가져옴: {e}')
        return None


def build_tablin_section(t):
    """인크 메일에 합칠 테이블린 데이터 점검 섹션."""
    if not t or not t.get('results'):
        return ''
    color_map = {"ok": "#10B981", "warn": "#F59E0B", "bad": "#EF4444"}
    rows = ''
    for r in t['results']:
        lv = r.get('level', 'ok')
        c = color_map.get(lv, '#64748B')
        ic = {"ok": "✓", "warn": "⚠", "bad": "✗"}.get(lv, '·')
        msg = ' / '.join(r.get('messages', []))
        rows += f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;color:{c};font-weight:700;width:30px">{ic}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#64748B;width:90px">{r.get('date','')}({r.get('dow','')})</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;font-weight:600;width:70px">{r.get('store','')}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;color:#475569;font-size:13px">{msg}</td>
        </tr>"""
    s = t.get('summary', {})
    return f"""
      <h3 style="color:#334155;margin:24px 0 8px;font-size:15px">🍜 테이블린 데이터 점검 (정상 {s.get('ok',0)} / 의심 {s.get('warn',0)} / 이상 {s.get('bad',0)})</h3>
      <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #E2E8F0;border-radius:6px;overflow:hidden">
        {rows}
      </table>
      <div style="font-size:11px;color:#94A3B8;margin-top:6px">테이블린 — POS 누락 + 매장×요일 베이스라인 이상치 (매일 23시 동기화 기준)</div>"""

REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
HEALTH_PATH = REPO_ROOT / "ops_data" / "health.json"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
TO_ADDR = os.environ.get("MAIL_TO", "zoids@ink-korea.co.kr")
ONLY_ON_ANOMALY = os.environ.get("MAIL_ONLY_ON_ANOMALY", "0") == "1"


def build_html(h, tablin=None):
    overall = h.get("overall", "ok")
    sum_ = h.get("summary", {})
    cc = h.get("cross_check", {})

    color_map = {"ok": "#10B981", "warn": "#F59E0B", "bad": "#EF4444"}
    overall_color = color_map.get(overall, "#64748B")
    overall_icon = {"ok": "✓", "warn": "⚠", "bad": "✗"}.get(overall, "·")
    overall_label = {"ok": "전체 정상", "warn": "의심 감지", "bad": "데이터 이상"}.get(overall, overall)

    # 시계열 매장별 표
    ts_rows = ""
    for s in h.get("stores", []):
        st = s["status"]
        icon = {"ok": "✓", "warn": "⚠", "bad": "✗", "missing": "✗"}.get(st, "·")
        c = color_map.get(st, "#64748B")
        dt_tag = f" <span style='color:#94A3B8;font-size:11px'>({s['target_date']} 데이터)</span>" if s.get("delayed") else ""
        msg = " / ".join(s.get("messages", []))
        ts_rows += f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;color:{c};font-weight:700;width:30px">{icon}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;font-weight:600;width:80px">{s['store']}점{dt_tag}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;color:#475569">{msg}</td>
        </tr>"""

    # 교차 검증 표
    cc_rows = ""
    if cc and cc.get("stores"):
        for s in cc["stores"]:
            lv = s.get("level", "ok")
            icon = {"ok": "✓", "warn": "⚠", "bad": "✗", "info": "ⓘ"}.get(lv, "·")
            c = color_map.get(lv, "#0EA5E9" if lv == "info" else "#64748B")
            diff = s.get("diff", 0)
            sign = "+" if diff >= 0 else "-"
            abs_diff = abs(diff)
            diff_fmt = (f"{abs_diff/1e8:.2f}억" if abs_diff >= 1e8
                        else f"{int(abs_diff/1e4):,}만" if abs_diff >= 1e4
                        else f"{abs_diff:,}")
            cc_rows += f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;color:{c};font-weight:700;width:30px">{icon}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;font-weight:600;width:80px">{s['store']}점</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;text-align:right;color:#475569;font-variant-numeric:tabular-nums">{sign}{diff_fmt}원 ({s.get('pct', 0):.1f}%)</td>
          <td style="padding:8px 10px;border-bottom:1px solid #E2E8F0;color:#64748B;font-size:12px">{s.get('message', '')}</td>
        </tr>"""

    cc_section = ""
    if cc_rows:
        cc_section = f"""
      <h3 style="color:#334155;margin:24px 0 8px;font-size:15px">교차 검증 (OK포스 raw ↔ 운영 대시보드 · {cc.get('yyyy_mm', '')} 월 합산)</h3>
      <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #E2E8F0;border-radius:6px;overflow:hidden">
        {cc_rows}
      </table>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:#F8FAFC;padding:20px;color:#1E293B">
  <div style="max-width:680px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #E2E8F0">

    <div style="background:{overall_color};color:#fff;padding:16px 20px">
      <div style="font-size:20px;font-weight:700">{overall_icon} {overall_label}</div>
      <div style="font-size:12px;opacity:0.9;margin-top:4px">인크커피 데이터 건강검진 · {h.get('target_date')} ({h.get('dow')}요일)</div>
    </div>

    <div style="padding:20px">
      <div style="display:flex;gap:12px;margin-bottom:16px;font-size:13px">
        <span style="background:#ECFDF5;color:#10B981;padding:4px 10px;border-radius:4px;font-weight:700">정상 {sum_.get('ok', 0)}</span>
        <span style="background:#FFFBEB;color:#F59E0B;padding:4px 10px;border-radius:4px;font-weight:700">의심 {sum_.get('warn', 0)}</span>
        <span style="background:#FEF2F2;color:#EF4444;padding:4px 10px;border-radius:4px;font-weight:700">이상 {sum_.get('bad', 0)}</span>
        <span style="background:#FEF2F2;color:#EF4444;padding:4px 10px;border-radius:4px;font-weight:700">누락 {sum_.get('missing', 0)}</span>
      </div>

      <h3 style="color:#334155;margin:0 0 8px;font-size:15px">시계열 검사 (어제 데이터 vs 평소 같은 요일 패턴)</h3>
      <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #E2E8F0;border-radius:6px;overflow:hidden">
        {ts_rows}
      </table>

      {cc_section}

      {build_tablin_section(tablin)}

      <div style="margin-top:24px;padding-top:16px;border-top:1px solid #E2E8F0;color:#94A3B8;font-size:11px;line-height:1.6">
        검사 시각: {h.get('checked_at')}<br>
        학습 기간: 최근 3년 매장×요일별 평균 · 수원점은 1일 딜레이로 이틀 전 데이터로 검사<br>
        대시보드: <a href="https://zoids901-debug.github.io/inkc-dashboard/" style="color:#0EA5E9">inkc-dashboard</a> · <a href="https://zoids901-debug.github.io/tablin-dashboard/" style="color:#0EA5E9">tablin-dashboard</a>
      </div>
    </div>
  </div>
</body></html>"""


def main():
    if not SMTP_USER or not SMTP_PASS:
        print("SMTP_USER 또는 SMTP_PASS 환경변수 없음 — 메일 발송 생략")
        return

    if not HEALTH_PATH.exists():
        print("health.json 없음 — 메일 발송 생략")
        return

    h = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
    overall = h.get("overall", "ok")

    if ONLY_ON_ANOMALY and overall == "ok":
        print(f"전체 OK — 메일 발송 생략 (MAIL_ONLY_ON_ANOMALY=1)")
        return

    icon = {"ok": "✓", "warn": "⚠", "bad": "✗"}.get(overall, "·")
    label = {"ok": "정상", "warn": "의심", "bad": "이상"}.get(overall, overall)
    subject = f"[인크 건강검진] {icon} {h.get('target_date')} {label} (정상 {h['summary'].get('ok', 0)} / 의심 {h['summary'].get('warn', 0)} / 이상 {h['summary'].get('bad', 0)})"

    tablin = fetch_tablin_health()

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = TO_ADDR
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(build_html(h, tablin), "html", "utf-8"))

    print(f"메일 발송: {TO_ADDR} ({subject})")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, [TO_ADDR], msg.as_string())
    print("발송 완료")


if __name__ == "__main__":
    main()
