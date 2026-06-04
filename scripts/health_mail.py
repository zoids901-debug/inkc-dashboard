# -*- coding: utf-8 -*-
"""데이터 건강검진 결과를 zoids@ink-korea.co.kr로 메일 발송.

점검 종류별 2개 섹션으로 정리:
  📋 원본 백데이터 점검 — 운영·상품·테이블린 수집/원본 일치 여부 (통일 형식)
  📈 시계열 이상 감지   — 운영·테이블린 평소 패턴 대비 이상치

Gmail SMTP 사용 — 환경변수 SMTP_USER, SMTP_PASS 필요.
실행: data-health.yml 워크플로우의 마지막 step
"""
import os, json, smtplib, urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from pathlib import Path

TABLIN_HEALTH_URL = 'https://raw.githubusercontent.com/zoids901-debug/tablin-dashboard/main/health.json'

_ICON = {"ok": "✓", "warn": "⚠", "bad": "✗", "missing": "✗", "info": "ⓘ", "no_data": "·"}
_COLOR = {"ok": "#10B981", "warn": "#F59E0B", "bad": "#EF4444", "missing": "#EF4444",
          "info": "#0EA5E9", "no_data": "#94A3B8"}


def fetch_tablin_health():
    """테이블린 저장소의 health.json을 가져옴 (실패해도 인크 메일은 정상 발송)."""
    try:
        req = urllib.request.Request(TABLIN_HEALTH_URL, headers={'User-Agent': 'inkc-mail'})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f'테이블린 health.json 못 가져옴: {e}')
        return None


# ── 통일 렌더링 헬퍼 ──────────────────────────────────
def _row(level, label, msg):
    """통일된 점검 행 — 아이콘 / 대상 / 메시지."""
    c = _COLOR.get(level, "#64748B")
    ic = _ICON.get(level, "·")
    return f"""
        <tr>
          <td style="padding:7px 10px;border-bottom:1px solid #EEF2F6;color:{c};font-weight:700;width:26px">{ic}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #EEF2F6;font-weight:600;width:150px;font-size:13px">{label}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #EEF2F6;color:#475569;font-size:13px">{msg}</td>
        </tr>"""


def _subblock(title, rows, empty_msg="점검 결과 없음"):
    """대시보드별 하위 블록 — 라벨 + 통일 표."""
    body = rows if rows else _row("no_data", "—", empty_msg)
    return f"""
      <div style="margin:14px 0 0">
        <div style="font-size:12px;font-weight:700;color:#64748B;margin-bottom:4px">{title}</div>
        <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #E2E8F0;border-radius:6px;overflow:hidden">
          {body}
        </table>
      </div>"""


def _counts(levels):
    s = {"ok": 0, "warn": 0, "bad": 0}
    for lv in levels:
        if lv in ("bad", "missing"):
            s["bad"] += 1
        elif lv == "warn":
            s["warn"] += 1
        else:
            s["ok"] += 1
    return s


def _section_header(emoji, title, subtitle, counts):
    return f"""
      <div style="margin:24px 0 2px">
        <div style="font-size:16px;font-weight:700;color:#1E293B">{emoji} {title}
          <span style="font-size:12px;font-weight:600;color:#64748B;margin-left:6px">정상 {counts['ok']} · 의심 {counts['warn']} · 이상 {counts['bad']}</span>
        </div>
        <div style="font-size:11px;color:#94A3B8;margin-top:3px">{subtitle}</div>
      </div>"""


# ── 대시보드별 점검 행 생성 ───────────────────────────
def _ops_raw_rows(cc):
    """운영 대시보드 원본 점검 — OK포스 raw ↔ 운영 대시보드 교차 검증."""
    rows, levels = "", []
    for s in (cc or {}).get("stores", []):
        lv = s.get("level", "ok")
        levels.append(lv)
        diff = s.get("diff", 0)
        sign = "+" if diff >= 0 else "-"
        ad = abs(diff)
        dfmt = (f"{ad/1e8:.2f}억" if ad >= 1e8
                else f"{int(ad/1e4):,}만" if ad >= 1e4 else f"{ad:,}")
        msg = f"{sign}{dfmt}원 ({s.get('pct',0):.1f}%) — {s.get('message','')}"
        rows += _row(lv, f"{s['store']}점", msg)
    return rows, levels


def _product_rows(p):
    """상품 대시보드 원본 점검 — 6개 매장 수집 + 운정 토스 대조."""
    rows, levels = "", []
    for r in (p or {}).get("stores", []):
        st = r.get("status", "ok")
        levels.append(st)
        tag = (f" <span style='color:#94A3B8;font-size:11px'>({r.get('target_date','')})</span>"
               if r.get("delayed") else "")
        rows += _row(st, f"{r.get('store','')}점{tag}", " / ".join(r.get("messages", [])))
    return rows, levels


def _ops_series_rows(h):
    """운영 대시보드 시계열 검사 — 어제 매출 vs 요일 베이스라인."""
    rows, levels = "", []
    for s in h.get("stores", []):
        st = s.get("status", "ok")
        levels.append(st)
        tag = (f" <span style='color:#94A3B8;font-size:11px'>({s.get('target_date','')})</span>"
               if s.get("delayed") else "")
        rows += _row(st, f"{s['store']}점{tag}", " / ".join(s.get("messages", [])))
    return rows, levels


def _tablin_rows(t, kind):
    """테이블린 점검 행 — kind: 'raw'(원본) 또는 'series'(시계열).
    구버전 health.json(raw/series 분리 전)도 통합 level/messages로 fallback."""
    rows, levels = "", []
    for r in (t or {}).get("results", []):
        block = r.get(kind)
        if isinstance(block, dict):
            lv = block.get("level", "ok")
            msgs = block.get("messages", [])
        else:  # 구버전 fallback
            lv = r.get("level", "ok")
            msgs = r.get("messages", [])
        levels.append(lv)
        label = f"{r.get('date','')[5:]}({r.get('dow','')}) {r.get('store','')}"
        rows += _row(lv, label, " / ".join(msgs))
    return rows, levels


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
    overall_color = _COLOR.get(overall, "#64748B")
    overall_icon = _ICON.get(overall, "·")
    overall_label = {"ok": "전체 정상", "warn": "의심 감지", "bad": "데이터 이상"}.get(overall, overall)

    cc = h.get("cross_check") or {}
    cc_ym = cc.get("yyyy_mm", "")

    # ── 📋 원본 백데이터 점검 ──
    ops_raw, l1 = _ops_raw_rows(cc)
    prod_rows, l2 = _product_rows(h.get("product_health"))
    tab_raw, l3 = _tablin_rows(tablin, "raw")
    raw_counts = _counts(l1 + l2 + l3)
    raw_section = (
        _section_header("📋", "원본 백데이터 점검",
                        "수집된 데이터가 원본(OK포스·토스·POS)과 일치하는지 · 빠진 매장·날짜는 없는지",
                        raw_counts)
        + _subblock(f"운영 대시보드 — OK포스 원본 ↔ 운영 대시보드 ({cc_ym} 월 합산)", ops_raw,
                    "교차 검증 결과 없음 (raw 미수집)")
        + _subblock("상품 대시보드 — 6개 매장 수집 + 운정 토스 원본 대조", prod_rows)
        + _subblock("테이블린 — POS 수집 · 매출 결측", tab_raw)
    )

    # ── 📈 시계열 이상 감지 ──
    ops_series, l4 = _ops_series_rows(h)
    tab_series, l5 = _tablin_rows(tablin, "series")
    series_counts = _counts(l4 + l5)
    series_section = (
        _section_header("📈", "시계열 이상 감지",
                        "어제 매출이 평소 같은 요일 패턴과 크게 다른지",
                        series_counts)
        + _subblock("운영 대시보드 — 어제 매출 vs 요일 베이스라인", ops_series)
        + _subblock("테이블린 — 매장×요일 베이스라인 (최근 8주)", tab_series)
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:#F8FAFC;padding:20px;color:#1E293B">
  <div style="max-width:680px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #E2E8F0">

    <div style="background:{overall_color};color:#fff;padding:16px 20px">
      <div style="font-size:20px;font-weight:700">{overall_icon} {overall_label}</div>
      <div style="font-size:12px;opacity:0.9;margin-top:4px">인크커피 데이터 건강검진 · {h.get('target_date')} ({h.get('dow')}요일)</div>
    </div>

    <div style="padding:20px">
      {raw_section}
      {series_section}

      <div style="margin-top:24px;padding-top:16px;border-top:1px solid #E2E8F0;color:#94A3B8;font-size:11px;line-height:1.6">
        검사 시각: {h.get('checked_at')}<br>
        📋 원본 점검 = 수집 데이터가 원본과 일치하는지 / 📈 시계열 = 평소 패턴 대비 이상치<br>
        시계열 학습: 최근 3년 매장×요일별 평균 · 수원점은 1일 딜레이로 이틀 전 데이터로 검사<br>
        대시보드: <a href="https://ink-korea.pages.dev/" style="color:#0EA5E9">INK-KOREA 통합 대시보드</a> (인크 직원 로그인)
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
        print("전체 OK — 메일 발송 생략 (MAIL_ONLY_ON_ANOMALY=1)")
        return

    icon = _ICON.get(overall, "·")
    label = {"ok": "정상", "warn": "의심", "bad": "이상"}.get(overall, overall)
    subject = f"[인크 건강검진] {icon} {h.get('target_date')} {label}"

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
