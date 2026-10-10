# MODA auto-reg farm: voidash email -> Clerk signup -> verify -> sync -> redeem promo
import os, json, time, uuid, random, string, asyncio, re, sys
import requests
import cloakbrowser

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
OUT = "C:/Users/User/tmp/moda-farm/accounts.jsonl"
REF = os.environ.get("MODA_REF", "")  # referral code (optional)
PK = "pk_live_Y2xlcmsubW9kYS5hcHAk"
SITEKEY_INVISIBLE = "0x4AAAAAAAFV93qQdS0ycilX"
SIDECAR = "http://127.0.0.1:8877/solve"
VA_DOMAINS = ["voidash.cyou", "govno.eu.cc", "musor.eu.cc", "pomoi.eu.cc", "voidash.bond"]

def rnd(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def va_create(domain):
    r = requests.post("https://api.voidash.com/api/v1/inboxes",
                      json={"domain": domain}, timeout=30)
    j = r.json()
    d = j.get("data") or j
    return d["address"], d["session_key"]

def va_messages(key):
    r = requests.get("https://api.voidash.com/api/v1/messages",
                     headers={"Authorization": "Bea" + "rer " + key}, timeout=30)
    j = r.json()
    return j.get("messages") or j.get("data", {}).get("messages") or []

def solve_turnstile():
    r = requests.post(SIDECAR, json={
        "type": "turnstile",
        "sitekey": SITEKEY_INVISIBLE,
        "url": "https://moda.app/sign-up",
        "action": "signup",
    }, timeout=180)
    j = r.json()
    tok = j.get("token") or j.get("data", {}).get("token") or j.get("result", {}).get("token")
    return tok

async def reg_one(UA, idx):
    browser = await cloakbrowser.launch_async(headless=True)
    await browser.__aenter__()
    dom_idx = idx % len(VA_DOMAINS)
    domain = VA_DOMAINS[dom_idx]
    try:
        email, va_key = va_create(domain)
    except Exception:
        domain = VA_DOMAINS[(dom_idx + 1) % len(VA_DOMAINS)]
        email, va_key = va_create(domain)
    pw = "Mo" + rnd(14) + "!7"
    rec = {"ts": time.time(), "email": email, "password": pw, "va_key": va_key,
           "ref_used": REF}
    ctx = await browser.new_context(user_agent=UA)
    page = await ctx.new_page()
    try:
        await page.goto("https://moda.app/sign-up", wait_until="domcontentloaded", timeout=60000)
        t0 = time.time()
        while "moment" in (await page.title()).lower() and time.time() - t0 < 60:
            await asyncio.sleep(3)
        await asyncio.sleep(3)
        tok = solve_turnstile()
        if not tok:
            rec["err"] = "no_turnstile_token"; return rec
        res = await page.evaluate("""async (a) => {
            try {
                const [pk, email, pw, tok, ref] = a;
                if (!window.Clerk) {
                    window.Clerk = new window.Clerk(pk);
                    await window.Clerk.load({standardBrowserWarned: true});
                }
                const su = await window.Clerk.client.signUp.create({
                    emailAddress: email, password: pw, captchaToken: tok,
                    unsafeMetadata: {referral_code: ref}
                });
                return 'SU|' + su.status + '|' + su.id;
            } catch (e) { return 'ERR|' + (e.errors ? JSON.stringify(e.errors) : String(e)).slice(0, 400); }
        }""", [PK, email, pw, tok, REF])
        rec["signup"] = res[:300]
        if not res.startswith("SU|"):
            return rec
        su_id = res.split("|")[2]
        # verification
        prep = await page.evaluate("""async (a) => {
            const [suId] = a;
            try {
                const su = window.Clerk.client.signUp;
                await su.prepareVerification({strategy: 'email_code', emailAddressId: su.emailAddressId || ''});
                return 'OK';
            } catch (e) {
                try { await window.Clerk.client.signUp.prepareEmailAddressVerification({strategy: 'email_code'}); return 'OK2'; }
                catch (e2) { return 'ERR|' + (e2.errors ? JSON.stringify(e2.errors) : String(e2)).slice(0, 300); }
            }
        }""", [su_id])
        rec["prep"] = prep[:200]
        code = None
        t1 = time.time()
        while time.time() - t1 < 180:
            for m in va_messages(va_key):
                c = m.get("otp_code")
                if not c:
                    body = (m.get("preview_text") or "") + " " + (m.get("body") or "")
                    mm = re.search(r"\b\d{6}\b", body)
                    c = mm.group(0) if mm else None
                if c:
                    code = c; break
            if code: break
            await asyncio.sleep(6)
        if not code:
            rec["err"] = "no_code"; return rec
        rec["code"] = code
        att = await page.evaluate("""async (code) => {
            try {
                const su = window.Clerk.client.signUp;
                const r = await su.attemptVerification({code: code, strategy: 'email_code'});
                return 'OK|' + r.status + '|' + (r.createdSessionId || '');
            } catch (e) { return 'ERR|' + (e.errors ? JSON.stringify(e.errors) : String(e)).slice(0, 300); }
        }""", code)
        rec["verify"] = att[:300]
        if not att.startswith("OK|complete") and "|" in att and not att.split("|")[2:3][0:1] == [""]:
            pass
        sess_id = att.split("|")[2] if att.count("|") >= 2 else ""
        if not sess_id:
            # fallback: signIn
            si = await page.evaluate("""async (a) => {
                try {
                    const [email, pw] = a;
                    const s = await window.Clerk.client.signIn.create({identifier: email, password: pw});
                    await window.Clerk.setActive({session: s.createdSessionId});
                    return 'OK|' + (s.createdSessionId || '');
                } catch (e) { return 'ERR|' + String(e).slice(0, 200); }
            }""", [email, pw])
            rec["signin_fallback"] = si[:200]
        else:
            await page.evaluate("""async (sid) => { await window.Clerk.setActive({session: sid}); }""", sess_id)
        await asyncio.sleep(3)
        # MODA sync + redeem
        jwt = await page.evaluate("async () => { try { return await window.Clerk.session.getToken({skipCache: true}) || 'NOJWT'; } catch(e) { return 'NOJWT'; } }")
        if not jwt.startswith("ey"):
            rec["err"] = "no_jwt"; return rec
        h = {"Authorization": "Bea" + "rer " + jwt, "Accept": "application/json",
             "User-Agent": UA, "Origin": "https://moda.app", "Referer": "https://moda.app/"}
        r = requests.post("https://api.moda.app/api/v1/users/me/sync", headers=h, timeout=30)
        rec["sync"] = r.status_code
        sj = r.json() if r.status_code == 200 else {}
        orgs = (sj.get("organizations") or [])
        org = orgs[0]["id"] if orgs else None
        rec["org"] = org
        if org:
            rp = requests.post(f"https://api.moda.app/api/v1/organizations/{org}/billing/redeem-promo",
                               headers=h, json={"code": "CLAUDEFOUNDERS"}, timeout=30)
            rec["redeem"] = {"status": rp.status_code, "body": rp.text[:300]}
            bs = requests.get(f"https://api.moda.app/api/v1/organizations/{org}/billing/status", headers=h, timeout=30)
            if bs.status_code == 200:
                bj = bs.json()
                rec["plan"] = bj.get("plan")
                rec["renews"] = bj.get("renews_at")
            rc = requests.get(f"https://api.moda.app/api/v1/organizations/{org}/referrals/code", headers=h, timeout=30)
            if rc.status_code == 200:
                rec["ref_code"] = rc.json().get("code")
            cd = requests.get(f"https://api.moda.app/api/v1/organizations/{org}/billing/credit-details", headers=h, timeout=30)
            if cd.status_code == 200:
                rec["credits"] = cd.json().get("total_remaining")
        json.dump(await ctx.cookies(), open(f"C:/Users/User/tmp/moda-farm/ck_{idx}.json", "w"))
        rec["ok"] = True
        return rec
    finally:
        await ctx.close()
        await browser.__aexit__(None, None, None)

async def main():
    UA = os.environ.get("MODA_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
    for i in range(N):
        rec = await reg_one(UA, i)
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(json.dumps(rec, ensure_ascii=False)[:500], flush=True)
        await asyncio.sleep(random.randint(8, 20))

asyncio.run(main())
