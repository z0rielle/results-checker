#!/usr/bin/env python3
"""
Results Checker - simple Windows app (Python + tkinter, stdlib only).

Shows lottery results from the same sources as the Muse checker:
  * Telegram MBAK group   (https://t.me/s/ROOMRESULTMBAKGROUP)   - fast primary
  * Telegram Kingdom group (https://t.me/s/ROOMRESULTKINGDOMGROUP3) - fast primary
  * jagonyaortu.com/riwayat-nomor - recheck source (adds the period number)

Rows that appear on Telegram first are labelled with their Telegram source.
When ortu later posts the same market + result, that row is marked (RECHECK!)
and shows the ortu period. Rows only on ortu show without a Telegram label.

No account, no login, no API key needed - all three pages are public.
Auto-refreshes every 60 seconds. Press Refresh for an instant update.
History: results the app has seen are saved to results_history.json
next to the app, so every registered market stays listed with its last
known result even after it scrolls off ortu's 30-row page.

Note on the realtime Telegram listener: the checker's listener uses a
personal Telegram login (API app + session file). That cannot be shipped
in a shared app - it would hand out the owner's Telegram account, and one
session can only run in one place at a time. This app instead polls the
public Telegram preview pages, which need no login and work for anyone.

Run on Windows: double-click Run.bat, or:  python ResultsChecker.py
Make a real .exe on Windows: run BuildExe.bat (needs PyInstaller, one time).
"""

import datetime
import html as htmlmod
import json
import os
import re
import threading
import tkinter as tk
from tkinter import ttk
from urllib.request import Request, urlopen

# Local history: every result the app has ever seen is saved here, next to
# the app, so a market stays visible with its last known result even after
# it scrolls off ortu's 30-row page and off the Telegram preview pages.
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "results_history.json")


def base_market(market):
    """'TXSEVENING - 1239' -> 'TXSEVENING'; 'TOTOMACAU 19:00' unchanged."""
    if " - " in market:
        head, tail = market.rsplit(" - ", 1)
        if tail.strip().isdigit():
            return head.strip()
    return market.strip()


def load_history():
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=1, sort_keys=True)
    except OSError:
        pass

ORTU_URL = "https://jagonyaortu.com/riwayat-nomor"
MBAK_URL = "https://t.me/s/ROOMRESULTMBAKGROUP"
KINGDOM_URL = "https://t.me/s/ROOMRESULTKINGDOMGROUP3"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

MONTHS = {"JANUARI": 1, "FEBRUARI": 2, "MARET": 3, "APRIL": 4, "MEI": 5,
          "JUNI": 6, "JULI": 7, "AGUSTUS": 8, "SEPTEMBER": 9, "OKTOBER": 10,
          "NOVEMBER": 11, "DESEMBER": 12,
          "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "MAY": 5, "JUNE": 6,
          "JULY": 7, "AUGUST": 8, "OCTOBER": 10, "DECEMBER": 12}
MACAU = {1: "TOTOMACAU 00:00", 2: "TOTOMACAU 13:00", 3: "TOTOMACAU 16:00",
         4: "TOTOMACAU 19:00", 5: "TOTOMACAU 22:00", 6: "TOTOMACAU 23:00"}
OREGON = {1: "OREGON 03:00", 2: "OREGON 06:00", 3: "OREGON 09:00", 4: "OREGON 12:00"}
ORTU_BASES = {
    "TENNESSE MORNING", "TENNESSE MIDDAY", "TENNESSE EVENING",
    "GEORGIA MID", "GEORGIA EVENING", "GEORGIA NIGHT",
    "FLORIDA MIDDAY", "FLORIDA EVENING", "KENTUCKY MIDDAY",
    "MICHIGAN MID", "MICHIGAN EVENING",
    "NEW YORK MIDDAY", "NEW YORK EVENING", "NEWJERSEY EVENING",
    "TXSMORNING", "TXSDAY", "TXSEVENING", "TXS NIGHT",
    "CAROLINA DAY", "CAROLINA EVE", "PCSO", "BULLSEYE", "SINGAPORE",
    "SYDNEY LOTTO", "HONGKONG LOTTO", "MAGNUM 4D", "CALIFORNIA",
    "GERMANY PLUS5",
}
# Telegram title -> ortu market name (verified by matching number + date).
ALIASES = {
    "NORTH CAROLINA DAY": "CAROLINA DAY",
    "NORTH CAROLINA EVENING": "CAROLINA EVE",
    "NEW JERSEY EVENING": "NEWJERSEY EVENING",
    "TEXAS NIGHT": "TXS NIGHT",
    "TEXAS MORNING": "TXSMORNING",
    "TEXAS DAY": "TXSDAY",
    "TEXAS EVENING": "TXSEVENING",
    "GEORGIA MIDDAY": "GEORGIA MID",
    "MICHIGAN MIDDAY": "MICHIGAN MID",
    "MAGNUM4D": "MAGNUM 4D",
}


def _ssl_context():
    """SSL context that trusts the Windows system certificate store,
    not just Python's bundled CA list. This is the actual fix for the
    user's PC: its network presents t.me with a certificate signed by
    a CA that the browser trusts (it is in the system store, e.g.
    installed by antivirus / network software) but Python's bundled
    CA list does not. Using the system store makes Python trust
    exactly what the browser trusts. Falls back to the default
    context when truststore is unavailable."""
    import ssl
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return ssl.create_default_context()


def _fetch_once(url):
    import ssl
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=15, context=_ssl_context()) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except ssl.SSLCertVerificationError:
        # Last resort on Windows: curl.exe uses the Windows Schannel
        # system store directly, so it trusts the same CAs as the
        # browser even if truststore is missing. Only used when
        # certificate verification itself failed, never to skip
        # verification in general.
        import shutil
        import subprocess
        curl = shutil.which("curl")
        if not curl:
            raise
        out = subprocess.run(
            [curl, "-sSL", "--max-time", "15", "-A", UA, url],
            capture_output=True, timeout=20)
        if out.returncode == 0 and out.stdout:
            return out.stdout.decode("utf-8", errors="ignore")
        raise


def fetch(url):
    """Fetch a page. Telegram is the fragile one on some PCs/networks
    (t.me is blocked on some networks even when ortu works fine), so
    for t.me URLs try direct, the telegram.me mirror, and two public
    fetch proxies that can reach t.me when the local network cannot.

    All attempts run IN PARALLEL and the first one that returns a
    page with result posts wins. The previous version tried them one
    after another, so a blocked network made every attempt sit out
    its full timeout in turn - up to minutes before ortu rows could
    show at all, which looked like the app never loading. Parallel
    attempts mean the total wait is the fastest success, or one
    timeout (15s) if everything is blocked. Ortu is fetched direct."""
    from urllib.parse import quote
    if "t.me/" not in url:
        return _fetch_once(url)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    attempts = [url, url.replace("t.me/", "telegram.me/"),
                "https://api.allorigins.win/raw?url=" + quote(url, safe=""),
                "https://api.codetabs.com/v1/proxy?quest=" + quote(url, safe="")]
    executor = ThreadPoolExecutor(max_workers=len(attempts))
    futures = {executor.submit(_fetch_once, a): a for a in attempts}
    last_error = Exception("Telegram fetch failed")
    try:
        for future in as_completed(futures):
            try:
                page = future.result()
            except Exception as exc:
                last_error = exc
                continue
            if "tgme_widget_message_text" in page or "WINNER" in page.upper():
                executor.shutdown(wait=False, cancel_futures=True)
                return page
            last_error = Exception("proxy returned a non-Telegram page")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    raise last_error


def parse_ortu(page):
    """Ortu table: day | date | 'MARKET - period' | result."""
    if not page:
        return []
    cells = re.findall(r"<td[^>]*>(.*?)</td>", page)
    rows = []
    for i in range(0, len(cells) - 3, 4):
        parts = [re.sub(r"<[^>]+>", "", c).strip() for c in cells[i:i + 4]]
        if len(parts) == 4 and parts[2] and parts[3]:
            rows.append({"day": parts[0], "date": parts[1],
                         "market": parts[2], "result": parts[3]})
    return rows


def parse_telegram(page, source):
    """Telegram /s/ preview page, same mapping/filtering as the checker."""
    if not page:
        return []
    blocks = re.findall(r"tgme_widget_message_text[^>]*>(.*?)</div>", page, re.S)
    rows = []
    for block in blocks:
        text = re.sub(r"<br[^>]*>", "\n", block)
        text = re.sub(r"<[^>]+>", "", text)
        text = htmlmod.unescape(text)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        title = re.split(r"[,/]", lines[0], maxsplit=1)[0].strip().upper()
        title = re.sub(r"\s+", " ", title)
        body = "\n".join(lines)
        m = re.search(r"(?:WINNER|W1NN3R)\s*:\s*(\d{4})", body, re.I)
        if not m:
            m = re.search(r"PRIZE\s*:\s*(\d{4})", body, re.I)
        if not m:
            m = re.search(r"PRIZE\s*1\s*:\s*(\d{4})", body, re.I)
        if not m:
            continue
        result = m.group(1)
        dm = re.search(r"(\d{1,2})\s+([A-Z]+)\s+(\d{4})", body.upper())
        date = ""
        if dm and dm.group(2) in MONTHS:
            date = "%02d %s %s" % (int(dm.group(1)), dm.group(2).title(), dm.group(3))
        norm = None
        macau = re.search(r"TOTO\s*MACAU\s*(\d)", title)
        code = re.search(r"\bMA\s*(\d)\b", body.upper())
        oregon = re.search(r"OREGON\s*(\d)", title)
        og = re.search(r"\bOG\s*(\d)\b", body.upper())
        if macau:
            norm = MACAU.get(int(macau.group(1)))
        elif code:
            norm = MACAU.get(int(code.group(1)))
        elif oregon:
            norm = OREGON.get(int(oregon.group(1)))
        elif og:
            norm = OREGON.get(int(og.group(1)))
        elif title in ALIASES:
            norm = ALIASES[title]
        elif title in ORTU_BASES:
            norm = title
        if not norm:
            continue  # not one of the ortu markets - filtered out
        rows.append({"market": norm, "result": result,
                     "source": source, "date": date})
    seen, out = set(), []
    for row in rows:
        key = row["market"] + "|" + row["result"]
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def load_results():
    """Return (display_rows, status_text). display_rows are dicts with
    market / result / info columns, newest Telegram primaries first."""
    # Fetch all three sources in parallel too, so a slow/blocked
    # Telegram channel cannot delay the ortu rows behind it.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ortu, mbak, king, ok, failed = [], [], [], [], []
    pages = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch, url): target
                   for url, target in ((ORTU_URL, "ortu"), (MBAK_URL, "mbak"),
                                       (KINGDOM_URL, "king"))}
        for future in as_completed(futures):
            target = futures[future]
            try:
                pages[target] = future.result()
                ok.append(target)
            except Exception as exc:
                pages[target] = ""
                failed.append("%s (%s)" % (target, type(exc).__name__))
    for target in ("ortu", "mbak", "king"):
        page = pages.get(target, "")
        if target == "ortu":
            ortu = parse_ortu(page)
        elif target == "mbak":
            mbak = parse_telegram(page, "Telegram MBAK")
        else:
            king = parse_telegram(page, "Telegram Kingdom")

    # Ortu market base name (strip " - period") -> full ortu row.
    ortu_by_base = {}
    for row in ortu:
        base = row["market"].rsplit(" - ", 1)[0].strip().upper()
        ortu_by_base.setdefault(base, row)

    display, seen = [], set()
    for tg in mbak + king:
        key = tg["market"] + "|" + tg["result"]
        if key in seen:
            continue
        seen.add(key)
        ortu_row = ortu_by_base.get(tg["market"])
        if ortu_row:
            info = "RECHECK! %s (%s)" % (ortu_row["market"], tg["source"])
        else:
            info = tg["source"]
        display.append({"market": tg["market"], "result": tg["result"], "info": info})
    for row in ortu:
        base = row["market"].rsplit(" - ", 1)[0].strip().upper()
        key = base + "|" + row["result"]
        if key in seen:
            continue
        seen.add(key)
        display.append({"market": row["market"], "result": row["result"],
                        "info": "%s %s" % (row["day"], row["date"])})
    status = "Sources OK: %s" % (", ".join(ok) if ok else "none - check your internet")
    if failed:
        status += " | Failed: " + ", ".join(failed)
    return display, status


# Material 3 Expressive styling: big expressive type, large rounded
# containers, bold colour, and a coloured chip per source. Tkinter has no
# real rounded corners, so cards use generous padding, large shapes and
# high-contrast colour blocks to get the same expressive feel on Windows
# (Segoe UI is the closest Windows font to Roboto).
BG = "#FEF7FF"
SURFACE = "#FFFFFF"
CARD = "#F3EDF7"
PRIMARY = "#6750A4"
PRIMARY_CONTAINER = "#EADDFF"
ON_PRIMARY_CONTAINER = "#4F378B"
TEXT = "#1D1B20"
TEXT_SOFT = "#49454F"


def chip_colors(info):
    """(chip background, chip text) for a row's source label."""
    if "RECHECK!" in info:
        return "#CDE8C9", "#1E4D1A"   # confirmed - green
    if "Last known" in info:
        return "#E6E0E9", "#49454F"   # history - neutral
    if "MBAK" in info:
        return "#EADDFF", "#4F378B"   # Telegram MBAK - purple
    if "Kingdom" in info:
        return "#D8E2FF", "#1E3A6E"   # Telegram Kingdom - blue
    return "#FFE9B8", "#5C4300"       # ortu only - amber


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Results Checker")
        self.geometry("760x640")
        self.configure(bg=BG)
        self.rows = []

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=24, pady=(24, 4))
        tk.Label(header, text="Results Checker", bg=BG, fg=TEXT,
                 font=("Segoe UI", 28, "bold")).pack(side="left")
        self.refresh_btn = tk.Button(
            header, text="  Refresh  ", command=self.refresh, bg=PRIMARY,
            fg="white", activebackground="#4F378B", activeforeground="white",
            font=("Segoe UI", 12, "bold"), relief="flat", bd=0,
            padx=10, pady=10, cursor="hand2")
        self.refresh_btn.pack(side="right")

        sub = tk.Frame(self, bg=BG)
        sub.pack(fill="x", padx=24, pady=(0, 12))
        tk.Label(sub, text="Live results, same sources as the checker.",
                 bg=BG, fg=TEXT_SOFT, font=("Segoe UI", 12)).pack(side="left")

        search_frame = tk.Frame(self, bg=SURFACE, highlightthickness=1,
                                highlightbackground="#CAC4D0")
        search_frame.pack(fill="x", padx=24, pady=(0, 16))
        tk.Label(search_frame, text="  Search  ", bg=SURFACE, fg=TEXT_SOFT,
                 font=("Segoe UI", 12)).pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.render())
        tk.Entry(search_frame, textvariable=self.search, bg=SURFACE,
                 fg=TEXT, font=("Segoe UI", 12), relief="flat", bd=0,
                 highlightthickness=0).pack(side="left", fill="x",
                                            expand=True, pady=10)

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical",
                                  command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list_frame = tk.Frame(self.canvas, bg=BG)
        self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self.status = tk.StringVar(value="Loading...")
        tk.Label(self, textvariable=self.status, bg=BG, fg=TEXT_SOFT,
                 font=("Segoe UI", 11)).pack(fill="x", padx=24, pady=(8, 16))
        self.refresh()
        self.after(60000, self.auto_refresh)

    def render(self):
        query = self.search.get().strip().lower()
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        shown = [r for r in self.rows
                 if not query or query in (r["market"] + " " + r["result"]).lower()]
        if not shown:
            tk.Label(self.list_frame, text="No results yet - press Refresh.",
                     bg=BG, fg=TEXT_SOFT, font=("Segoe UI", 13)).pack(pady=24)
            return
        for row in shown:
            card = tk.Frame(self.list_frame, bg=CARD, padx=18, pady=14)
            card.pack(fill="x", padx=24, pady=6)
            left = tk.Frame(card, bg=CARD)
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=row["market"], bg=CARD, fg=TEXT,
                     font=("Segoe UI", 14, "bold"), anchor="w").pack(fill="x")
            chip_bg, chip_fg = chip_colors(row["info"])
            tk.Label(left, text=" " + row["info"] + " ", bg=chip_bg, fg=chip_fg,
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(6, 0))
            tk.Label(card, text=row["result"], bg=PRIMARY_CONTAINER,
                     fg=ON_PRIMARY_CONTAINER, font=("Segoe UI", 22, "bold"),
                     padx=16, pady=8).pack(side="right")

    def refresh(self):
        self.status.set("Refreshing...")
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            rows, status = load_results()
        except Exception as exc:
            rows, status = [], "Error: %s" % exc
        self.after(0, lambda: self._done(rows, status))

    def _done(self, rows, status):
        # Update local history with everything seen this refresh, then
        # append any market that is only in history (scrolled off the
        # live pages) with its last known result, so all registered
        # markets stay visible instead of only ortu's last 30 rows.
        history = load_history()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        for row in rows:
            history[base_market(row["market"])] = {
                "result": row["result"], "info": row["info"], "seen": now}
        save_history(history)
        merged, seen_bases = list(rows), set()
        for row in rows:
            seen_bases.add(base_market(row["market"]))
        for market in sorted(history):
            if market not in seen_bases:
                entry = history[market]
                merged.append({"market": market, "result": entry["result"],
                               "info": "Last known (%s) - %s"
                                       % (entry.get("seen", ""), entry["info"])})
        self.rows = merged
        self.render()
        self.status.set("%s  |  Updated %s  |  Auto-refresh every 60s"
                        % (status, datetime.datetime.now().strftime("%H:%M:%S")))

    def auto_refresh(self):
        self.refresh()
        self.after(60000, self.auto_refresh)


if __name__ == "__main__":
    App().mainloop()
