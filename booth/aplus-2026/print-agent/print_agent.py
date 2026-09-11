#!/usr/bin/env python3
"""
APLUS+ Conference 2026 booth: print agent for the Mac at the table.

Pulls the print queue from the booth Worker and feeds the Canon Selphy through
CUPS (`lp`), one job at a time, in the order names were entered. No print
dialogs, no taps. Pauses on printer errors and resumes when the printer is back.

    python3 print_agent.py --printer "Canon_SELPHY_CP1500" [--media 4x6] [--dry-run]

Setup (once):
    1. System Settings > Printers & Scanners > add the Selphy (USB or same Wi-Fi).
    2. `lpstat -p` shows the printer name; pass it with --printer.
    3. `lpoptions -p <printer> -l | grep -i media` shows the paper names; the
       default below ("na_index-4x6_4x6in") is the CUPS name for 4x6 postcard.
       If the Selphy prints with a white margin, try `--media Postcard.Fullbleed`.
    4. `export BOOTH_URL=https://aplus-conference-booth.nameless-mountain-bafa.workers.dev`
       `export AGENT_TOKEN=<the value set with wrangler secret put AGENT_TOKEN>`
Stdlib only. No cron, no launchd: run it in a Terminal window for the day.
"""
import argparse, json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error, socket

UA = "Mozilla/5.0 (Macintosh) A+BoothPrintAgent/1.0"   # workers.dev rejects Python's default UA (1010)


def api(base, path, token, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data is not None else "GET"),
                                 headers={"User-Agent": UA, "Content-Type": "application/json", "X-Agent-Token": token or ""})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def download(base, key):
    req = urllib.request.Request(f"{base}/photo/{key}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def printer_ready(printer):
    """True when CUPS reports the printer idle or printing (not stopped/disabled)."""
    out = subprocess.run(["lpstat", "-p", printer], capture_output=True, text=True).stdout.lower()
    return ("idle" in out or "printing" in out) and "disabled" not in out and "stopped" not in out


def print_file(printer, path, media, name):
    cmd = ["lp", "-d", printer, "-o", f"media={media}", "-o", "fit-to-page", "-t", name[:40], path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"lp exit {r.returncode}")
    return r.stdout.strip()   # "request id is Canon_SELPHY_CP1500-42 (1 file(s))"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--printer", required=True, help="CUPS printer name from `lpstat -p`")
    ap.add_argument("--media", default="na_index-4x6_4x6in")
    ap.add_argument("--base", default=os.environ.get("BOOTH_URL", "https://aplus-conference-booth.nameless-mountain-bafa.workers.dev"))
    ap.add_argument("--token", default=os.environ.get("AGENT_TOKEN", ""))
    ap.add_argument("--poll", type=float, default=3.0, help="seconds between queue checks")
    ap.add_argument("--gap", type=float, default=2.0, help="seconds to wait after handing a job to CUPS")
    ap.add_argument("--dry-run", action="store_true", help="download and mark done, do not print")
    a = ap.parse_args()
    agent = socket.gethostname()
    printed = 0
    print(f"[agent] {agent} -> {a.base}  printer={a.printer} media={a.media}{'  DRY RUN' if a.dry_run else ''}")

    while True:
        try:
            if not a.dry_run and not printer_ready(a.printer):
                print(f"[paused] {a.printer} not ready (paper? ink? off?). Retrying in {a.poll:.0f}s")
                time.sleep(a.poll); continue
            q = api(a.base, "/queue?status=queued", a.token)["queue"]
            if not q:
                time.sleep(a.poll); continue
            job = q[0]
            waiting = len(q) - 1
            print(f"[next] {job['name']} ({job.get('school') or 'school not given'})  {waiting} more waiting")
            api(a.base, f"/queue/{job['id']}/claim", a.token, {"agent": agent})
            try:
                data = download(a.base, job["key"])
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                    f.write(data); path = f.name
                if a.dry_run:
                    print(f"[dry] would print {len(data)//1024} KB for {job['name']}")
                else:
                    rid = print_file(a.printer, path, a.media, f"{job['name']} {job.get('school','')}")
                    print(f"[sent] {rid}")
                api(a.base, f"/queue/{job['id']}/done", a.token, {})
                printed += 1
                print(f"[done] {job['name']}  total today: {printed}")
                time.sleep(a.gap)
            except Exception as e:
                print(f"[fail] {job['name']}: {e}")
                api(a.base, f"/queue/{job['id']}/failed", a.token, {"error": str(e)})
                # put it back at the front once the printer recovers; a human can
                # also re-print from the booth album.
                time.sleep(a.poll)
                api(a.base, f"/queue/{job['id']}/requeue", a.token, {})
        except KeyboardInterrupt:
            print("\n[agent] stopped"); return
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as e:
            print(f"[net] {e}. Retrying in {a.poll:.0f}s"); time.sleep(a.poll)
        except Exception as e:
            print(f"[error] {e}"); time.sleep(a.poll)


if __name__ == "__main__":
    main()
