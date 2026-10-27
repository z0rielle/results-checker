#!/usr/bin/env python3
"""
Results Checker - Material 3 Expressive edition (Windows).

Why a web UI inside a window, not tkinter?
Tkinter cannot do real Material 3 Expressive: its widgets are square,
it has no large rounded shapes, no tonal elevation, no expressive
typography. This edition renders a true MD3 Expressive page (large
28px shapes, tonal containers, expressive display type, pill chips,
FAB) in the system's web view on Windows (Edge WebView2, built into
Windows 10/11), while Python still does all the fetching - same
sources, same mapping, same history as the checker. The page is
served from a local server on 127.0.0.1 and fetches /results.json
from it, so the UI never depends on the pywebview JS bridge.

Run on Windows: double-click RunMD3.bat (installs pywebview once).
Make a single .exe: run BuildExeMD3.bat on a Windows PC.
"""

import datetime
import json

__version__ = "1.3.0"

# --- OTA update -------------------------------------------------------
# How friends get updates without redownloading from you:
# 1. Put a version.json file at a stable public URL you control
#    (easiest: a public GitHub repo, raw file, e.g.
#    https://raw.githubusercontent.com/YOURNAME/results-checker/main/version.json)
# 2. Set UPDATE_MANIFEST_URL below to that URL, rebuild once, share it.
# 3. To ship a new version, upload the new .py files (or the new .exe)
#    to that same place and bump "version" in version.json.
# The app only ever CHECKS on startup and when the Update button is
# pressed. It never installs anything on its own: if a newer version
# is found it shows an "Update available" banner, and only installs
# when the user clicks Update. Manifest format:
#   {"version": "1.3.0",
#    "files": {"ResultsCheckerMD3.py": "https://.../ResultsCheckerMD3.py",
#              "ResultsChecker.py": "https://.../ResultsChecker.py"},
#    "exe_url": "https://.../ResultsCheckerMD3.exe"}
# Leave UPDATE_MANIFEST_URL empty and the Update button will simply
# say OTA is not configured yet.
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/z0rielle/results-checker/main/version.json"

_update_cache = {"at": 0, "data": None}


def _version_tuple(version):
    try:
        return tuple(int(part) for part in str(version).split("."))
    except ValueError:
        return (0,)


def check_update(force=False):
    """Return a dict about the newest version, or an error/not-configured note."""
    import time
    now = time.time()
    if not force and _update_cache["data"] is not None and now - _update_cache["at"] < 3600:
        return _update_cache["data"]
    if not UPDATE_MANIFEST_URL:
        result = {"configured": False, "update_available": False,
                  "message": "OTA not configured yet - set UPDATE_MANIFEST_URL in the app."}
        _update_cache.update(at=now, data=result)
        return result
    try:
        from urllib.request import Request, urlopen
        req = Request(UPDATE_MANIFEST_URL, headers={"User-Agent": "ResultsChecker"})
        with urlopen(req, timeout=15) as resp:
            manifest = json.loads(resp.read().decode("utf-8"))
        latest = str(manifest.get("version", ""))
        available = _version_tuple(latest) > _version_tuple(__version__)
        result = {"configured": True, "update_available": available,
                  "current": __version__, "latest": latest,
                  "manifest": manifest,
                  "message": ("Update available: %s" % latest) if available
                             else "You are on the latest version (%s)." % __version__}
    except Exception as exc:
        result = {"configured": True, "update_available": False,
                  "message": "Update check failed: %s" % exc}
    _update_cache.update(at=now, data=result)
    return result


def apply_update():
    """Download the update from the manifest and stage an updater that
    replaces the app and restarts it. Only called after the user
    clicks Update. Returns a status dict; the app exits after the
    updater is launched, so the caller should not try to keep running."""
    import os
    import subprocess
    import sys
    info = check_update(force=True)
    if not info.get("update_available"):
        return {"ok": False, "message": info.get("message", "No update available.")}
    manifest = info["manifest"]
    app_dir = os.path.dirname(os.path.abspath(__file__))
    stage = os.path.join(app_dir, ".update_stage")
    os.makedirs(stage, exist_ok=True)
    from urllib.request import Request, urlopen
    try:
        if getattr(sys, "frozen", False) and manifest.get("exe_url"):
            exe_name = os.path.basename(sys.executable)
            target = os.path.join(stage, exe_name)
            req = Request(manifest["exe_url"], headers={"User-Agent": "ResultsChecker"})
            with urlopen(req, timeout=120) as resp, open(target, "wb") as f:
                f.write(resp.read())
            updater = os.path.join(stage, "update.bat")
            with open(updater, "w", encoding="utf-8") as f:
                f.write('@echo off\ntimeout /t 2 /nobreak >nul\n'
                        'copy /y "%s" "%s" >nul\n'
                        'start "" "%s"\n' % (target, sys.executable, sys.executable))
            subprocess.Popen([updater], cwd=stage,
                             creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0)
            return {"ok": True, "message": "Updating to %s - the app will restart." % info["latest"]}
        for filename, file_url in (manifest.get("files") or {}).items():
            # Only ever replace files inside the app's own folder.
            safe = os.path.basename(filename)
            req = Request(file_url, headers={"User-Agent": "ResultsChecker"})
            with urlopen(req, timeout=120) as resp, open(os.path.join(stage, safe), "wb") as f:
                f.write(resp.read())
        updater = os.path.join(stage, "update.bat")
        lines = ["@echo off", "timeout /t 2 /nobreak >nul"]
        for filename in (manifest.get("files") or {}):
            safe = os.path.basename(filename)
            lines.append('copy /y "%s" "%s" >nul' % (os.path.join(stage, safe),
                                                     os.path.join(app_dir, safe)))
        lines.append('start "" "%s" "%s"' % (sys.executable,
                                             os.path.join(app_dir, "ResultsCheckerMD3.py")))
        with open(updater, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        subprocess.Popen([updater], cwd=stage,
                         creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0)
        return {"ok": True, "message": "Updating to %s - the app will restart." % info["latest"]}
    except Exception as exc:
        return {"ok": False, "message": "Update failed: %s" % exc}


try:
    from ResultsChecker import (base_market, load_history, load_results,
                                save_history)
except ImportError:  # running from a different folder
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ResultsChecker import (base_market, load_history, load_results,
                                save_history)


def compute_results():
    """Always returns a dict, never raises - a failure in one step must
    not take the whole app down, and the UI must see the real error.
    Rows carry an 'updated' timestamp: the time that result last
    CHANGED, not the last refresh. A market keeps its old timestamp
    while its result is unchanged, so sorting by 'updated' puts the
    genuinely latest markets on top instead of shuffling everything
    every refresh."""
    try:
        rows, status = load_results()
    except Exception as exc:
        return {"rows": [], "status": "Error fetching: %s" % exc}
    try:
        history = load_history()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            base = base_market(row["market"])
            old = history.get(base) or {}
            # Only move the timestamp when the result actually changed.
            updated = now if old.get("result") != row["result"] else old.get("seen", now)
            history[base] = {"result": row["result"], "info": row["info"],
                             "seen": updated}
            row["updated"] = updated
        save_history(history)
        merged, seen = list(rows), {base_market(r["market"]) for r in rows}
        for market in sorted(history):
            if market not in seen:
                entry = history[market]
                merged.append({"market": market, "result": entry["result"],
                               "info": "Last known (%s) - %s"
                                       % (entry.get("seen", ""), entry["info"]),
                               "updated": entry.get("seen", "")})
        # Latest markets on top by default; the UI can re-sort from here.
        merged.sort(key=lambda r: r.get("updated", ""), reverse=True)
    except Exception as exc:
        # History is a bonus, not the data - show live rows without it.
        merged = list(rows)
        status = "%s (history unavailable: %s)" % (status, exc)
    return {"rows": merged,
            "status": "%s | Updated %s"
            % (status, datetime.datetime.now().strftime("%H:%M:%S"))}


# Local HTTP server instead of the pywebview JS bridge: the bridge is
# where the previous version failed ("Could not load results" with no
# detail, even though the fetcher itself works). A plain same-origin
# fetch to 127.0.0.1 is far less fragile across pywebview versions,
# and the status string from the server tells the user exactly which
# sources succeeded, so a Telegram failure shows as ortu-only rows
# instead of a blank page.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/results.json":
            body = json.dumps(compute_results()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/update-check":
            info = check_update()
            body = json.dumps({k: v for k, v in info.items()
                               if k != "manifest"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/update-apply":
            body = json.dumps(apply_update()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Results Checker</title>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto+Flex:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
  :root{
    --md-sys-color-primary:#6750A4; --md-sys-color-on-primary:#FFFFFF;
    --md-sys-color-primary-container:#EADDFF; --md-sys-color-on-primary-container:#4F378B;
    --md-sys-color-secondary-container:#E8DEF8; --md-sys-color-on-secondary-container:#1D192B;
    --md-sys-color-tertiary-container:#FFD8E4; --md-sys-color-surface:#FEF7FF;
    --md-sys-color-surface-container-high:#ECE6F0; --md-sys-color-surface-container:#F3EDF7;
    --md-sys-color-on-surface:#1D1B20; --md-sys-color-on-surface-variant:#49454F;
    --md-sys-color-outline:#79747E;
    --green-bg:#CDE8C9; --green-fg:#1E4D1A; --blue-bg:#D8E2FF; --blue-fg:#1E3A6E;
    --amber-bg:#FFE9B8; --amber-fg:#5C4300; --grey-bg:#E6E0E9; --grey-fg:#49454F;
  }
  body.dark{
    --md-sys-color-primary:#D0BCFF; --md-sys-color-on-primary:#381E72;
    --md-sys-color-primary-container:#4F378B; --md-sys-color-on-primary-container:#EADDFF;
    --md-sys-color-secondary-container:#4A4458; --md-sys-color-on-secondary-container:#E8DEF8;
    --md-sys-color-surface:#141218; --md-sys-color-surface-container-high:#2B2930;
    --md-sys-color-surface-container:#211F26; --md-sys-color-on-surface:#E6E0E9;
    --md-sys-color-on-surface-variant:#CAC4D0; --md-sys-color-outline:#938F99;
    --green-bg:#1E4D1A; --green-fg:#CDE8C9; --blue-bg:#1E3A6E; --blue-fg:#D8E2FF;
    --amber-bg:#5C4300; --amber-fg:#FFE9B8; --grey-bg:#2B2930; --grey-fg:#CAC4D0;
  }
  .toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 16px}
  .toolbtn{border:1.5px solid var(--md-sys-color-outline);background:var(--md-sys-color-surface-container-high);
    color:inherit;border-radius:999px;padding:10px 18px;font:inherit;font-weight:500;cursor:pointer}
  .toolbtn.primary{background:var(--md-sys-color-primary);color:var(--md-sys-color-on-primary);border-color:transparent}
  .sortrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:0 28px 4px;max-width:860px;margin:0 auto}
  .sortrow label{color:var(--md-sys-color-on-surface-variant);font-size:14px}
  .sortrow select{background:var(--md-sys-color-surface-container-high);color:inherit;
    border:1.5px solid var(--md-sys-color-outline);border-radius:999px;padding:10px 14px;font:inherit}
  #update-banner{display:none;max-width:860px;margin:12px auto 0;background:var(--md-sys-color-primary-container);
    color:var(--md-sys-color-on-primary-container);border-radius:28px;padding:16px 20px;
    font-weight:500;cursor:pointer}
  *{box-sizing:border-box}
  body{margin:0;background:var(--md-sys-color-surface);color:var(--md-sys-color-on-surface);
    font-family:"Google Sans","Roboto Flex","Segoe UI",system-ui,sans-serif}
  header{padding:32px 28px 8px;max-width:860px;margin:0 auto}
  h1{font-size:44px;line-height:1.05;letter-spacing:-0.5px;margin:0 0 6px;font-weight:700}
  h1 span{color:var(--md-sys-color-primary)}
  .subtitle{color:var(--md-sys-color-on-surface-variant);font-size:16px;margin:0 0 20px}
  .search{display:flex;align-items:center;gap:10px;background:var(--md-sys-color-surface-container-high);
    border-radius:28px;padding:14px 20px}
  .search input{border:0;outline:0;background:transparent;flex:1;font:inherit;font-size:16px;color:inherit}
  .chips{display:flex;gap:10px;flex-wrap:wrap;padding:16px 28px 4px;max-width:860px;margin:0 auto}
  .chip{border:1.5px solid var(--md-sys-color-outline);background:transparent;color:inherit;
    border-radius:999px;padding:10px 20px;font:inherit;font-weight:500;cursor:pointer}
  .chip.active{background:var(--md-sys-color-secondary-container);border-color:transparent}
  main{max-width:860px;margin:0 auto;padding:12px 28px 110px;display:grid;gap:16px}
  .card{display:flex;align-items:center;gap:16px;background:var(--md-sys-color-surface-container);
    border-radius:28px;padding:20px 22px;animation:fadein .6s ease}
  @keyframes fadein{from{opacity:0}to{opacity:1}}
  .card:hover{outline:2px solid var(--md-sys-color-primary-container)}
  .left{flex:1;min-width:0}
  .market{font-size:19px;font-weight:700;line-height:1.2}
  .tag{display:inline-block;margin-top:10px;border-radius:999px;padding:6px 14px;font-size:13px;font-weight:700}
  .tag.mbak{background:var(--md-sys-color-primary-container);color:var(--md-sys-color-on-primary-container)}
  .tag.kingdom{background:var(--blue-bg);color:var(--blue-fg)}
  .tag.recheck{background:var(--green-bg);color:var(--green-fg)}
  .tag.ortu{background:var(--amber-bg);color:var(--amber-fg)}
  .tag.history{background:var(--grey-bg);color:var(--grey-fg)}
  .result{background:var(--md-sys-color-primary-container);color:var(--md-sys-color-on-primary-container);
    font-size:38px;font-weight:800;letter-spacing:-1px;line-height:1;
    padding:18px 22px;border-radius:28px 28px 28px 6px;white-space:nowrap}
  .fab{position:fixed;right:28px;bottom:28px;width:64px;height:64px;border-radius:20px;border:0;
    background:var(--md-sys-color-primary);color:#fff;font-size:30px;cursor:pointer;
    box-shadow:0 4px 12px rgba(103,80,164,.30);transition:transform .4s ease, box-shadow .4s ease}
  .fab:hover{transform:translateY(-2px)}
  /* Elegant refresh: a slow, eased turn, not a fast spin. */
  .fab.spinning{animation:turn 2.4s cubic-bezier(.45,0,.2,1) infinite}
  @keyframes turn{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
  /* Thin MD3 linear progress bar at the very top while loading. */
  #progress{position:fixed;top:0;left:0;height:3px;width:0;background:var(--md-sys-color-primary);
    transition:width .8s ease;z-index:10}
  #progress.on{width:70%;animation:drift 1.6s ease-in-out infinite alternate}
  @keyframes drift{from{margin-left:0}to{margin-left:30%}}
  footer{max-width:860px;margin:0 auto;padding:0 28px 24px;color:var(--md-sys-color-on-surface-variant);font-size:13px}
  .empty{text-align:center;padding:48px 20px;color:var(--md-sys-color-on-surface-variant);font-size:18px}
</style></head><body>
<div id="progress"></div>
<header>
  <h1>Results <span>Checker</span></h1>
  <p class="subtitle">Live results from Telegram MBAK &amp; Kingdom, rechecked on ortu.</p>
  <div class="toolbar">
    <button class="toolbtn" id="dark-btn" title="Toggle dark mode">Dark mode</button>
    <button class="toolbtn" id="update-btn" title="Check for app updates">Check for updates</button>
  </div>
  <div class="search"><span>&#128269;</span><input id="q" placeholder="Search a market or number&hellip;"></div>
</header>
<div id="update-banner" onclick="doUpdate()"></div>
<div class="sortrow"><label for="sort">Sort:</label>
  <select id="sort">
    <option value="latest">Latest first</option>
    <option value="market-az">Market A to Z</option>
    <option value="market-za">Market Z to A</option>
    <option value="result-asc">Result low to high</option>
    <option value="result-desc">Result high to low</option>
  </select>
</div>
<div class="chips" id="chips"></div>
<main id="list"></main>
<footer id="status">Loading&hellip;</footer>
<button class="fab" id="fab" title="Refresh">&#8635;</button>
<script>
let ALL=[], FILTER='All';
const FILTERS=['All','Telegram','Recheck','Ortu only','Last known'];
function tagClass(info){
  if(info.includes('RECHECK!')) return 'recheck';
  if(info.includes('Last known')) return 'history';
  if(info.includes('MBAK')) return 'mbak';
  if(info.includes('Kingdom')) return 'kingdom';
  return 'ortu';
}
function tagFilter(info){
  if(FILTER==='All') return true;
  if(FILTER==='Telegram') return info.includes('Telegram');
  if(FILTER==='Recheck') return info.includes('RECHECK!');
  if(FILTER==='Ortu only') return !info.includes('Telegram') && !info.includes('Last known');
  if(FILTER==='Last known') return info.includes('Last known');
  return true;
}
function applySort(rows){
  const sort=document.getElementById('sort').value;
  const out=[...rows];
  if(sort==='market-az') out.sort((a,b)=>a.market.localeCompare(b.market));
  else if(sort==='market-za') out.sort((a,b)=>b.market.localeCompare(a.market));
  else if(sort==='result-asc') out.sort((a,b)=>parseInt(a.result,10)-parseInt(b.result,10));
  else if(sort==='result-desc') out.sort((a,b)=>parseInt(b.result,10)-parseInt(a.result,10));
  else out.sort((a,b)=>(b.updated||'').localeCompare(a.updated||''));
  return out;
}
function render(){
  const q=document.getElementById('q').value.trim().toLowerCase();
  const list=document.getElementById('list');
  const shown=applySort(ALL.filter(r=>tagFilter(r.info) && (!q || (r.market+' '+r.result).toLowerCase().includes(q))));
  if(!shown.length){
    const hint = FILTER==='Telegram'
      ? 'No Telegram results loaded yet - Telegram may be unreachable on this network, see the status below.'
      : 'No results match. Press refresh.';
    list.innerHTML='<div class="empty">'+hint+'</div>'; return; }
  list.innerHTML=shown.map(r=>
    '<article class="card"><div class="left"><div class="market">'+r.market+'</div>'+
    '<span class="tag '+tagClass(r.info)+'">'+r.info+'</span></div>'+
    '<div class="result">'+r.result+'</div></article>').join('');
}
function renderChips(){
  document.getElementById('chips').innerHTML=FILTERS.map(f=>
    '<button class="chip'+(f===FILTER?' active':'')+'" onclick="setFilter(\''+f+'\')">'+f+'</button>').join('');
}
function setFilter(f){ FILTER=f; renderChips(); render(); }
async function load(){
  const fab=document.getElementById('fab'); fab.classList.add('spinning');
  document.getElementById('progress').classList.add('on');
  try{
    const resp=await fetch('/results.json');
    if(!resp.ok) throw new Error('server said '+resp.status);
    const data=await resp.json();
    ALL=data.rows; document.getElementById('status').textContent=data.status+'  |  Auto-refresh every 60s';
    render();
  }catch(e){ document.getElementById('status').textContent='Could not load results: '+e.message+'. Press refresh.'; }
  fab.classList.remove('spinning');
  const bar=document.getElementById('progress'); bar.classList.remove('on'); bar.style.width='100%';
  setTimeout(()=>{ bar.style.width='0'; }, 400);
}
document.getElementById('q').addEventListener('input', render);
document.getElementById('sort').addEventListener('change', render);
document.getElementById('fab').addEventListener('click', load);
function applyDark(dark){
  document.body.classList.toggle('dark', dark);
  document.getElementById('dark-btn').textContent = dark ? 'Light mode' : 'Dark mode';
  try{ localStorage.setItem('results-dark', dark ? '1' : '0'); }catch(e){}
}
(function initDark(){
  let dark=false;
  try{ const saved=localStorage.getItem('results-dark'); dark = saved ? saved==='1' : window.matchMedia('(prefers-color-scheme: dark)').matches; }catch(e){}
  applyDark(dark);
})();
document.getElementById('dark-btn').addEventListener('click', ()=>applyDark(!document.body.classList.contains('dark')));
async function checkUpdate(){
  const banner=document.getElementById('update-banner');
  try{
    const resp=await fetch('/update-check'); const data=await resp.json();
    if(data.update_available){
      banner.style.display='block';
      banner.textContent='Update available: version '+data.latest+' (you have '+data.current+') - tap here to update.';
    } else {
      banner.style.display='none';
      document.getElementById('status').textContent=data.message;
    }
  }catch(e){ document.getElementById('status').textContent='Update check failed: '+e.message; }
}
async function doUpdate(){
  const banner=document.getElementById('update-banner');
  banner.textContent='Updating - the app will restart, please wait...';
  try{
    const resp=await fetch('/update-apply'); const data=await resp.json();
    banner.textContent=data.message;
    if(data.ok) setTimeout(()=>{ window.close(); }, 3000);
  }catch(e){ banner.textContent='Update failed: '+e.message; }
}
document.getElementById('update-btn').addEventListener('click', checkUpdate);
renderChips();
load();
checkUpdate();
setInterval(load, 60000);
</script></body></html>
"""


def main():
    try:
        import webview
    except ImportError:
        print("pywebview is not installed. On Windows run:")
        print("  pip install pywebview")
        print("then run this app again (or double-click RunMD3.bat).")
        raise SystemExit(1)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webview.create_window("Results Checker",
                          url="http://127.0.0.1:%d/" % port,
                          width=920, height=760)
    webview.start()


if __name__ == "__main__":
    main()
