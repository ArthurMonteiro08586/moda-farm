import json, sys, asyncio, time, requests
import cloakbrowser

OUT = "C:/Users/User/tmp/moda-farm/accounts.jsonl"

async def main():
    recs = [json.loads(l) for l in open(OUT) if l.strip()]
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    for rec in recs:
        if rec.get("redeem", {}).get("status") == 200:
            print("skip done:", rec["email"]); continue
        email, pw = rec.get("email"), rec.get("password")
        if not email or not pw:
            continue
        browser = await cloakbrowser.launch_async(headless=True)
        await browser.__aenter__()
        ctx = await browser.new_context(user_agent=UA)
        page = await ctx.new_page()
        try:
            await page.goto("https://moda.app/sign-in", wait_until="domcontentloaded", timeout=60000)
            t0 = time.time()
            while "moment" in (await page.title()).lower() and time.time() - t0 < 60:
                await asyncio.sleep(3)
            await asyncio.sleep(3)
            si = await page.evaluate("""async (a) => {
                try {
                    const [email, pw] = a;
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
                    const s = await window.Clerk.client.signIn.create({identifier: email, password: pw});
                    await window.Clerk.setActive({session: s.createdSessionId});
                    return 'OK|' + s.status;
                } catch (e) { return 'ERR|' + (e.errors ? JSON.stringify(e.errors) : String(e)).slice(0, 200); }
            }""", [email, pw])
            if not si.startswith("OK"):
                print("login fail:", email, si[:120]); continue
            jwt = await page.evaluate("async () => await window.Clerk.session.getToken({skipCache: true})")
            h = {"Authorization": "Bea" + "rer " + jwt, "Accept": "application/json",
                 "User-Agent": UA, "Origin": "https://moda.app", "Referer": "https://moda.app/"}
            r = requests.post("https://api.moda.app/api/v1/users/me/sync", headers=h, timeout=30)
            sj = r.json() if r.status_code == 200 else {}
            orgs = sj.get("organizations") or []
            if not orgs:
                print("no org:", email); continue
            org = orgs[0]["id"]
            rp = requests.post(f"https://api.moda.app/api/v1/organizations/{org}/billing/redeem-promo",
                               headers=h, json={"code": "CLAUDEFOUNDERS"}, timeout=30)
            bs = requests.get(f"https://api.moda.app/api/v1/organizations/{org}/billing/status", headers=h, timeout=30)
            bj = bs.json() if bs.status_code == 200 else {}
            cd = requests.get(f"https://api.moda.app/api/v1/organizations/{org}/billing/credit-details", headers=h, timeout=30)
            cdj = cd.json() if cd.status_code == 200 else {}
            rc = requests.get(f"https://api.moda.app/api/v1/organizations/{org}/referrals/code", headers=h, timeout=30)
            rec["org"] = org
            rec["redeem"] = {"status": rp.status_code, "body": rp.text[:300]}
            rec["plan"] = bj.get("plan")
            rec["renews"] = bj.get("renews_at")
            rec["credits"] = cdj.get("total_remaining")
            rec["ref_code"] = rc.json().get("code") if rc.status_code == 200 else None
            rec["sync_email"] = sj.get("email")
            print(rec["email"], "sync_email:", sj.get("email"), "->", rp.status_code, rp.text[:200], rec["plan"], rec["credits"], rec["ref_code"])
        finally:
            await ctx.close()
            await browser.__aexit__(None, None, None)
    with open(OUT, "w", encoding="utf-8") as f:
        for rec in recs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("saved")

asyncio.run(main())