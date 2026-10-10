import os, json, time, asyncio, requests
import cloakbrowser

GMAIL = os.environ["MODA_EMAIL"]  # your account email
NEWPW = os.environ["MODA_PASS"]  # your account password
ORG = "122633bc-8a72-4bac-bf96-10aa8234b942"

EPS = [
    ("GET", f"/api/v1/organizations/{ORG}/referrals/code"),
    ("GET", f"/api/v1/organizations/{ORG}/referrals/stats"),
    ("GET", f"/api/v1/organizations/{ORG}/billing/usage"),
    ("GET", f"/api/v1/organizations/{ORG}/billing/credit-details"),
    ("GET", f"/api/v1/organizations/{ORG}/billing/credit-bundles"),
    ("GET", f"/api/v1/organizations/{ORG}/teams"),
    ("GET", f"/api/v1/organizations/{ORG}/members"),
    ("GET", "/api/v1/users/me/settings"),
    ("GET", "/api/v1/folders/tree"),
    ("GET", "/api/v1/memory/list?limit=20"),
    ("GET", f"/api/v1/organizations/{ORG}/billing/status"),
]

async def main():
    async with await cloakbrowser.launch_async(headless=True) as browser:
        UA = os.environ.get("MODA_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
        ctx = await browser.new_context(user_agent=UA)
        page = await ctx.new_page()
        await page.goto("https://moda.app/sign-in", wait_until="domcontentloaded", timeout=60000)
        t0 = time.time()
        while "moment" in (await page.title()).lower() and time.time() - t0 < 60:
            await asyncio.sleep(3)
        await asyncio.sleep(4)
        si = await page.evaluate("""async (a) => {
            try {
                if (!window.Clerk) {
                    await new Promise((res, rej) => {
                        const s = document.createElement('script');
                        s.src = 'https://clerk.moda.app/npm/@clerk/clerk-js@6/dist/clerk.browser.js';
                        s.onload = res; s.onerror = () => rej(new Error('load fail'));
                        document.head.appendChild(s);
                    });
                    window.Clerk = new window.Clerk('pk_live_Y2xlcmsubW9kYS5hcHAk');
                    await window.Clerk.load({standardBrowserWarned: true});
                }
                const [email, pw] = a;
                let si = await window.Clerk.client.signIn.create({identifier: email, password: pw});
                if (si.status === 'needs_first_factor') {
                    si = await window.Clerk.client.signIn.attemptFirstFactor({password: pw, strategy: 'password'});
                }
                if (si.status === 'complete' && si.createdSessionId) {
                    await window.Clerk.setActive({session: si.createdSessionId});
                }
                return 'OK|' + si.status;
            } catch (e) { return 'ERR|' + (e.errors ? JSON.stringify(e.errors) : String(e)).slice(0, 400); }
        }""", [GMAIL, NEWPW])
        print("signIn:", si[:400])
        if not si.startswith("OK"):
            return
        await asyncio.sleep(3)
        jwt = await page.evaluate("""async () => {
            const t = await window.Clerk.session.getToken({skipCache: true});
            return t || 'NOJWT';
        }""")
        print("jwt:", len(jwt) if jwt.startswith("ey") else jwt[:80])
        if not jwt.startswith("ey"):
            return
        open("C:/Users/User/tmp/moda_jwt_work.txt", "w").write(jwt)
        json.dump(await ctx.cookies(), open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies_out.json"), "w"))
        h = {"User-Agent": UA, "Authorization": "Bea" + "rer " + jwt, "Accept": "application/json",
             "Origin": "https://moda.app", "Referer": "https://moda.app/"}
        out = {}
        for meth, ep in EPS:
            try:
                r = requests.request(meth, "https://api.moda.app" + ep, headers=h, timeout=25)
                print(meth, ep[8:70], "->", r.status_code, r.text[:300].replace("\n", " "))
                out[ep] = {"status": r.status_code, "body": r.text[:6000]}
            except Exception as e:
                print(meth, ep, "ERR", str(e)[:100])
        json.dump(out, open("C:/Users/User/tmp/moda_api_probe.json", "w"), indent=1)

asyncio.run(main())
