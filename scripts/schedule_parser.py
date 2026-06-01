# -*- coding: utf-8 -*-
"""인크커피 매장별 근무 스케줄 파서 (Google Sheets API).

각 매장 스케줄 탭에서 일별 근무인원 + 시간대별(시프트 코드) 분포를 추출한다.
- 매장마다 시프트 코드/레이아웃이 다름 → 탭 상단 범례(코드→시간)를 읽어 동적 인식.
- 단일 월 탭(가산 '스케줄_26.5', 수원 '2026.05 스케줄', 광주/운정 'N월 스케줄')과
  여러 달 스택 탭(다산 '스케줄', 하남 '26.1,2,..월스케줄') 둘 다 처리.
- 날짜 시작 컬럼은 동적 감지(매장별 1칸 오프셋 있음). 성명 = 날짜시작-4.

API 키: env GOOGLE_SHEETS_API_KEY 우선, 없으면 keyring 'google_sheets_api_key'.

사용:
    from schedule_parser import fetch_schedule
    data = fetch_schedule('다산', 2026, 5)
    # → {1: {'count': 14, 'shifts': {'N3': 5, 'N8': 4, 'N6': 2, ...}}, 2: {...}, ...}
"""
import os
import re
import sys
import json
import urllib.request
from urllib.parse import quote

# 매장별 스케줄 스프레드시트 ID (ops_actions_sync.py SHEET_IDS와 동일)
STORE_SHEETS = {
    "하남": "1elj1WazP29hobZ6l1sLTy77eo2kNCnMr2tEdoRCxaC0",
    "가산": "1lVkO-6PzbegxlRqPwNRMeFt_5dsLuSztzhevpqv650k",
    "다산": "1jQemSMvxiWi9eVonqQdxJh542EBftt-tsI4VNegvISw",
    "광주": "1xC0fKGOGiK2ABw4G6zkjFl7vMpmSIq5BCH1bVVpdCuQ",
    "수원": "1niXSDHhFgz9KLrnrv8pDkE5Uf1CiZERlnSnLRSbNT8w",
    "운정": "1GgfvL9kRjU9OACDZYr3jKdDEXpX32ebzdeZIqIBsZYw",
}

_TIME = re.compile(r"^[0-2]?\d:[0-5]\d$")

# 현장 출근 판정용 — 휴무/휴가/파견(타매장)·빈칸은 제외, 그 외 비표준 코드(반차·h/p·파트)는 출근으로 카운트
# (사장님 기준: "현장에 나오면 다 1명")
_STORE_NAMES = set(STORE_SHEETS)
_OFF_EXACT = {"D/O", "D/0", "DO", "OFF", "O", "X", "-", "휴", "휴무"}
_OFF_SUB = ("휴", "연차", "월차", "공가", "경조", "병가", "예비군",
            "교육", "파견", "연가", "대휴", "산휴", "육휴", "퇴사", "입사예정")


def _is_present(cell):
    """그날 현장 출근이면 True. 휴무/휴가/타매장 파견/빈칸만 제외."""
    v = str(cell).strip()
    if not v or v.upper() in _OFF_EXACT or v in _STORE_NAMES:
        return False
    return not any(s in v for s in _OFF_SUB)


def _api_key():
    k = os.environ.get("GOOGLE_SHEETS_API_KEY")
    if k:
        return k
    try:
        sys.path.insert(0, r"C:\Users\zoids\Scripts\creds")
        from creds import get_cred  # type: ignore
        return get_cred("google_sheets_api_key") or ""
    except Exception:
        return ""


def _gs(sid, rng, key):
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sid}"
           f"/values/{quote(rng)}?key={key}")
    req = urllib.request.Request(url, headers={"User-Agent": "inkc-sched"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read()).get("values", [])


def _tab_titles(sid, key):
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sid}"
           f"?fields=sheets.properties.title&key={key}")
    req = urllib.request.Request(url, headers={"User-Agent": "inkc-sched"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return [s["properties"]["title"] for s in json.loads(r.read())["sheets"]]


def _pick_tab(titles, month):
    """해당 월 스케줄 탭 선택. (탭명, 'single'|'stack') 반환."""
    single = stack = None
    for t in titles:
        tn = t.replace(" ", "")
        if "스케줄" not in tn:
            continue
        months = set()
        for g in re.findall(r"((?:\d{1,2})(?:,\d{1,2})*)월", t):
            months |= {int(x) for x in g.split(",")}
        if not months:
            m2 = re.search(r"(?:_26\.|2026\.0?|^26\.)(\d{1,2})", tn)
            if m2:
                months = {int(m2.group(1))}
        if months == {month}:
            single = single or t
        elif tn == "스케줄" or (month in months and len(months) > 1):
            stack = stack or t
    if single:
        return single, "single"
    if stack:
        return stack, "stack"
    return None, None


def _legend(vals):
    """탭 상단 범례에서 근무 시프트 코드 집합 + 코드→시작시간."""
    work, times = set(), {}
    for r in vals[:12]:
        for c in range(6, 12):
            if len(r) > c + 2:
                code = str(r[c]).strip()
                t = str(r[c + 2]).strip()
                if code and not _TIME.match(code) and _TIME.match(t):
                    work.add(code)
                    times[code] = t
    return work, times


def _date_headers(block):
    """블록 내 모든 날짜헤더 (행idx, 날짜시작col). 팀 섹션마다 반복될 수 있음."""
    hdrs = []
    for i, r in enumerate(block):
        for c in range(2, 14):
            if [str(r[c + k]).strip() if c + k < len(r) else "" for k in range(5)] == ["1", "2", "3", "4", "5"]:
                hdrs.append((i, c))
                break
    return hdrs


def _name_col(block, hr, dc):
    """섹션 헤더 주변에서 성명 컬럼 탐색. 팀마다 부서/직책 컬럼 수가 달라 오프셋이 변동됨."""
    for i in (hr, hr - 1, hr - 2):
        if i < 0:
            continue
        row = block[i]
        for c in range(dc):
            if c < len(row) and str(row[c]).replace(" ", "") in ("성명", "이름", "성함"):
                return c
    return max(0, dc - 4)


def _parse_block(block, work):
    """블록에서 일별 {count, shifts}. 팀 섹션별로 날짜헤더+성명컬럼을 재감지해
    바리스타/베이커리/푸드/일용직/세척 등 레이아웃이 다른 팀까지 모두 합산."""
    out = {}
    headers = _date_headers(block)
    for idx, (hr, dc) in enumerate(headers):
        nc = _name_col(block, hr, dc)
        end = headers[idx + 1][0] if idx + 1 < len(headers) else len(block)
        for r in block[hr + 1:end]:
            if len(r) <= nc:
                continue
            nm = str(r[nc]).strip()
            if not re.search("[가-힣]", nm):
                continue
            if nm in ("성 명", "성명", "이름") or any(t in nm for t in ("TEAM", "부서", "직책", "총괄", "합계")):
                continue
            for day in range(1, 32):
                c = dc + day - 1
                if c >= len(r):
                    continue
                cell = str(r[c]).strip()
                if not _is_present(cell):
                    continue
                e = out.setdefault(day, {"count": 0, "shifts": {}})
                e["count"] += 1
                code = cell.split("/")[0]
                if code in work:
                    e["shifts"][code] = e["shifts"].get(code, 0) + 1
    return out


def fetch_schedule(store, year, month, key=None):
    """매장 1곳의 해당 연·월 일별 근무인원 + 시프트 분포.
    {day: {'count': int, 'shifts': {code: n}}} 반환. 실패 시 {}."""
    key = key or _api_key()
    if not key or store not in STORE_SHEETS:
        return {}
    sid = STORE_SHEETS[store]
    tab, mode = _pick_tab(_tab_titles(sid, key), month)
    if not tab:
        return {}
    vals = _gs(sid, f"{tab}!A1:BB800", key)
    work, _times = _legend(vals)
    if mode == "stack":
        mark = f"{year}년 {month}월"
        s = next((i for i, r in enumerate(vals) if any(mark in str(c) for c in r)), None)
        if s is None:
            return {}
        e = next((i for i in range(s + 1, len(vals))
                  if any("근무일정표" in str(c) for c in vals[i])), len(vals))
        block = vals[s:e]
    else:
        block = vals
    return _parse_block(block, work)


if __name__ == "__main__":
    y, m = 2026, 5
    for st in STORE_SHEETS:
        d = fetch_schedule(st, y, m)
        days = [v["count"] for v in d.values() if v["count"]]
        tot = sum(v["count"] for v in d.values())
        rng = f"{min(days)}~{max(days)}명" if days else "데이터없음"
        print(f"{st}: {y}.{m} 일별 {rng}, 연인원 {tot}")
