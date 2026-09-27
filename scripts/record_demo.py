"""Record the setup screen as timestamped PNG frames for docs/demo.gif.

The search is faked and every address uses the reserved .example domain, so the demo
contains no real person's data and needs no network. Run from an empty directory:

    mkdir -p /tmp/demo && cd /tmp/demo && mkdir frames
    <repo>/.venv/bin/python <repo>/scripts/record_demo.py
    python3 <repo>/scripts/build_gif.py 960      # needs Pillow
"""
import asyncio, time
from contextlib import asynccontextmanager
from pathlib import Path
from playwright.async_api import async_playwright
import harvester.ui as ui, harvester.cli as cli
from harvester.store import Lead

cli.PROFILES_DIR = Path("profiles"); cli.ROOT = Path.cwd()
state = {"frames": [], "rec": True}
W, H = 1280, 820

@asynccontextmanager
async def fake_browser(headless=False):
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        ctx = await b.new_context(viewport={"width": W, "height": H}, color_scheme="light", device_scale_factor=1)
        await ctx.new_page(); state["ctx"] = ctx
        yield ctx
        await b.close()
ui.browser = fake_browser

POSTS = {
  "Accountant": [
    ("[naukri] Accountant", None), ("hr@acme-finance.example", "kept"), ("careers@bluepeak.example", "experience 8-10 yrs"),
    ("[linkedin] hiring Accountant share resume", None), ("jobs@northwind.example", "kept"),
    ("talent@farhorizon.example", "location hyderabad"), ("me.jobhunt@mail.example", 'job seeker: "#OpenToWork"'),
    ("[linkedin] Accountant hiring email", None), ("accounts@ledgerly.example", "kept"),
    ("bench@staffing.example", 'us staffing: "C2C"'), ("hiring@tallyworks.example", "kept"),
  ],
  "Sales Executive": [
    ("[naukri] Sales Executive", None), ("sales.hr@brightmart.example", "kept"),
    ("jobs@fieldforce.example", 'excluded keyword: "door to door"'),
    ("[linkedin] hiring Sales Executive share resume", None), ("careers@retailhub.example", "kept"),
    ("hr@citymotors.example", "location pune"),
  ],
}

async def fake_harvest(page, setup, store, sources, limit, log=print):
    out, src = [], "naukri"
    for item, st in POSTS[setup.profile.role]:
        await asyncio.sleep(0.55)
        if st is None:
            src = item[1:item.index("]")]; await log(item); continue
        l = Lead(item, src, "u", "Hiring team", "", st)
        out.append((l, store.record(l))); await log(f"  + {item}  ({st})")
    await asyncio.sleep(0.4)
    return out
cli.harvest = fake_harvest

OVERLAY = """
(() => {
  const c = document.createElement('div'); c.id='__cap';
  c.style.cssText='position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:#111827;color:#fff;'+
    'font:600 17px system-ui,sans-serif;padding:10px 20px;border-radius:999px;box-shadow:0 6px 20px rgba(0,0,0,.25);z-index:99;transition:opacity .2s';
  document.body.appendChild(c);
  const k = document.createElement('div'); k.id='__cur';
  k.innerHTML='<svg width="22" height="22" viewBox="0 0 24 24"><path d="M3 2l7 19 2.5-7.5L20 11z" fill="#111" stroke="#fff" stroke-width="1.5"/></svg>';
  k.style.cssText='position:fixed;left:640px;top:420px;z-index:100;pointer-events:none;transition:left .45s ease,top .45s ease';
  document.body.appendChild(k);
})()"""

async def cap(page, text):
    await page.evaluate("t => { const c=document.getElementById('__cap'); c.textContent=t; c.style.opacity=t?1:0; }", text)

async def move(page, sel):
    box = await page.locator(sel).first.bounding_box()
    await page.evaluate("([x,y]) => { const k=document.getElementById('__cur'); k.style.left=x+'px'; k.style.top=y+'px'; }",
                        [box["x"] + min(box["width"] * 0.5, 60), box["y"] + box["height"] * 0.6])
    await asyncio.sleep(0.55)

async def click(page, sel):
    await move(page, sel); await page.click(sel); await asyncio.sleep(0.25)

async def type_in(page, sel, text):
    await move(page, sel); await page.click(sel)
    await page.type(sel, text, delay=70); await asyncio.sleep(0.2)

async def recorder():
    while not state.get("go"): await asyncio.sleep(0.05)
    page = state["ctx"].pages[0]
    while state["rec"]:
        t = time.monotonic()
        try:
            png = await page.screenshot(type="png")
            state["frames"].append((t, png))
        except Exception:
            pass
        await asyncio.sleep(max(0, 0.12 - (time.monotonic() - t)))

async def scroll_to(page, y):
    await page.evaluate("y => window.scrollTo({top:y, behavior:'smooth'})", y); await asyncio.sleep(1.0)

async def driver():
    while "ctx" not in state: await asyncio.sleep(0.05)
    await asyncio.sleep(1.2)
    page = state["ctx"].pages[0]
    await page.evaluate(OVERLAY)
    await cap(page, "Run  harvest  — a setup screen opens"); state["go"] = True; await asyncio.sleep(2.4)
    await cap(page, "1 · Fill in your details once")
    await type_in(page, "[name=name]", "Priya")
    await type_in(page, "[name=role]", "Accountant")
    await type_in(page, "[name=experience_years]", "2")
    await type_in(page, "[name=locations]", "Delhi, Noida")
    await move(page, "[name=posted_within]"); await page.select_option("[name=posted_within]", "week")
    await asyncio.sleep(0.8)
    await cap(page, "2 · Press Save & find emails")
    await click(page, "#runBtn")
    await scroll_to(page, 420)
    await cap(page, "It searches LinkedIn and Naukri and filters every post")
    await page.wait_for_selector("#result", state="visible", timeout=30000)
    await asyncio.sleep(0.6)
    await cap(page, "3 · Only new, matching addresses — copy them in one click")
    await scroll_to(page, 900); await asyncio.sleep(0.8)
    await click(page, "#copyBtn"); await asyncio.sleep(1.4)
    await cap(page, "Every skipped address says why")
    await click(page, "details summary"); await scroll_to(page, 5000); await asyncio.sleep(2.6)
    await scroll_to(page, 0)
    await cap(page, "4 · Add someone else — any job, IT or not")
    await click(page, "#newBtn")
    await type_in(page, "[name=name]", "Rahul")
    await type_in(page, "[name=role]", "Sales Executive")
    await type_in(page, "[name=experience_years]", "1")
    await type_in(page, "[name=locations]", "Mumbai")
    await click(page, "#runBtn")
    await page.wait_for_function("document.querySelector('#progressTitle').textContent==='Finished'", timeout=30000)
    await scroll_to(page, 0)
    await cap(page, "Next time: just tick a name and run — details are saved")
    await click(page, "#people .person:first-child"); await asyncio.sleep(3.0)
    state["rec"] = False
    await asyncio.sleep(0.3)
    await page.close()

async def main():
    await asyncio.gather(ui.run_screen(Path(__file__).resolve().parent.parent / "config.toml"), driver(), recorder())
    fr = state["frames"]
    for i, (t, png) in enumerate(fr):
        Path(f"frames/{i:04d}_{int((t - fr[0][0]) * 1000):06d}.png").write_bytes(png)
    print("frames:", len(fr), "duration: %.1fs" % (fr[-1][0] - fr[0][0]))
asyncio.run(main())
