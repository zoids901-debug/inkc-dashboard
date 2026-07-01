# -*- coding: utf-8 -*-
"""[임시 진단] 클라우드(깃허브 액션)에서 큐브테크(cube-tech.co.kr) 접근이
어디까지/어떻게 막히는지 확인. 비밀번호는 출력하지 않음.
실행: cube-diag.yml (workflow_dispatch). 확인 후 이 파일 + 워크플로 삭제 예정."""
import os, sys, json, time, ssl, socket, urllib.request, urllib.error
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import requests

BASE = "https://www.cube-tech.co.kr"
HOST = "www.cube-tech.co.kr"
UID = os.environ.get("CUBEPOS_ID", "")
PW  = os.environ.get("CUBEPOS_PW", "")
BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Chromium";v="126", "Not.A/Brand";v="24"',
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty",
    "Origin": BASE, "Referer": BASE + "/webcc/",
}

def show(label, fn):
    t0 = time.time()
    try:
        r = fn(); ms = int((time.time()-t0)*1000)
        body = ""
        try: body = (r.text or "")[:80].replace("\n"," ")
        except Exception: pass
        print(f"  [{label}] OK status={r.status_code} {ms}ms len={len(r.content)} body='{body}'")
    except Exception as e:
        ms = int((time.time()-t0)*1000)
        print(f"  [{label}] FAIL {ms}ms {type(e).__name__}: {str(e)[:140]}")

def main():
    # 러너 IP
    try:
        ip = requests.get("https://api.ipify.org", timeout=10).text
        print("runner public IP:", ip)
    except Exception as e:
        print("ip 조회 실패:", e)

    # 0) DNS + raw TLS handshake
    try:
        addrs = socket.getaddrinfo(HOST, 443)
        print("DNS:", sorted({a[4][0] for a in addrs}))
    except Exception as e:
        print("DNS 실패:", e)
    try:
        t0=time.time(); ctx=ssl.create_default_context()
        with socket.create_connection((HOST,443),timeout=15) as s:
            with ctx.wrap_socket(s,server_hostname=HOST) as ss:
                print(f"  [raw TLS handshake] OK {int((time.time()-t0)*1000)}ms cipher={ss.cipher()[0]}")
    except Exception as e:
        print(f"  [raw TLS handshake] FAIL {type(e).__name__}: {str(e)[:120]}")

    s = requests.Session()
    # 1) requests GET (default UA / browser UA)
    show("GET / default-UA", lambda: s.get(BASE+"/", timeout=20))
    show("GET / browser-UA", lambda: s.get(BASE+"/", headers=BROWSER, timeout=20))
    show("GET /webcc/ browser", lambda: s.get(BASE+"/webcc/", headers=BROWSER, timeout=20))
    show("GET /api/auth/me browser", lambda: s.get(BASE+"/api/auth/me", headers=BROWSER, timeout=20))

    # 2) POST login — 최소 헤더 (현재 코드 방식)
    def login_min():
        return requests.post(BASE+"/api/auth/login",
            data=json.dumps({"username":UID,"password":PW}),
            headers={"User-Agent":"Mozilla/5.0","Origin":BASE,"Content-Type":"application/json","Accept":"application/json"},
            timeout=25)
    show("POST login min-headers", login_min)

    # 3) POST login — 풀 브라우저 헤더 + 세션(웜)
    def login_warm():
        s2 = requests.Session(); s2.headers.update(BROWSER)
        try: s2.get(BASE+"/webcc/", timeout=15)
        except Exception: pass
        h = dict(BROWSER); h["Content-Type"]="application/json"; h["Accept"]="application/json"
        return s2.post(BASE+"/api/auth/login", data=json.dumps({"username":UID,"password":PW}), headers=h, timeout=25)
    show("POST login browser+warm", login_warm)

    # 4) urllib 방식
    def login_urllib():
        req = urllib.request.Request(BASE+"/api/auth/login",
            data=json.dumps({"username":UID,"password":PW}).encode(),
            headers={**BROWSER,"Content-Type":"application/json","Accept":"application/json"}, method="POST")
        r = urllib.request.urlopen(req, timeout=25)
        class R: status_code=r.status; content=r.read(); text=content.decode("utf-8","replace")
        return R()
    show("POST login urllib", login_urllib)

if __name__ == "__main__":
    main()
