import os
import sys
import json
import random
import threading
import webbrowser
import subprocess
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REDIRECT_URI  = os.environ["REDIRECT_URI"]
TOKEN_FILE    = os.path.join(os.path.dirname(__file__), ".token.json")
SCOPE         = "user-top-read user-modify-playback-state user-read-playback-state streaming user-read-private"
SPOTIFYD_BIN  = os.path.join(os.path.dirname(__file__), "spotifyd")

# ── Auth ──────────────────────────────────────────────────────────────────────

_auth_code = None

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        global _auth_code
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _auth_code = qs.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Auth complete. You can close this tab.")
        threading.Thread(target=self.server.shutdown).start()

def _get_auth_code():
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID, "response_type": "code",
        "redirect_uri": REDIRECT_URI, "scope": SCOPE,
    })
    webbrowser.open(f"https://accounts.spotify.com/authorize?{params}")
    HTTPServer(("127.0.0.1", 8000), _Handler).serve_forever()
    return _auth_code

def _exchange_code(code):
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT_URI,
    }).encode()
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data)
    import base64
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    req.add_header("Authorization", f"Basic {creds}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as r:
        token = json.loads(r.read())
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f)
    return token["access_token"]

def _refresh_token(refresh_token):
    import base64
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token", "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data)
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    req.add_header("Authorization", f"Basic {creds}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as r:
        token = json.loads(r.read())
    saved = json.load(open(TOKEN_FILE)) if os.path.exists(TOKEN_FILE) else {}
    saved.update(token)
    with open(TOKEN_FILE, "w") as f:
        json.dump(saved, f)
    return token["access_token"]

def get_access_token():
    if os.path.exists(TOKEN_FILE):
        token = json.load(open(TOKEN_FILE))
        try:
            return _refresh_token(token["refresh_token"])
        except Exception:
            pass
    code = _get_auth_code()
    return _exchange_code(code)

# ── API ───────────────────────────────────────────────────────────────────────

def api_get(path, access_token):
    req = urllib.request.Request(f"https://api.spotify.com/v1{path}")
    req.add_header("Authorization", f"Bearer {access_token}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def get_top_tracks(access_token, limit=10, time_range="medium_term", artist_filter=None):
    # fetch more so filter has enough to work with
    fetch = limit * 3 if artist_filter else limit
    data = api_get(f"/me/top/tracks?limit={min(fetch, 50)}&time_range={time_range}", access_token)
    tracks = data["items"]
    if artist_filter:
        f = artist_filter.lower()
        tracks = [t for t in tracks if any(f in a["name"].lower() for a in t["artists"])]
    return tracks[:limit]

def search_tracks(access_token, query, limit=5):
    q = urllib.parse.quote(query)
    data = api_get(f"/search?q={q}&type=track&limit={limit * 2}", access_token)
    seen, tracks = set(), []
    for t in data["tracks"]["items"]:
        if t["uri"] not in seen:
            seen.add(t["uri"])
            tracks.append(t)
        if len(tracks) == limit:
            break
    return tracks

# ── Playback ──────────────────────────────────────────────────────────────────

def ensure_spotifyd():
    subprocess.run(["pkill", "-x", "spotifyd"], capture_output=True)
    import time; time.sleep(1)
    subprocess.Popen(
        [SPOTIFYD_BIN, "--no-daemon", "--device-name", "spoty-cli"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(4)

def get_device_id(access_token, device_name="spoty-cli"):
    data = api_get("/me/player/devices", access_token)
    for d in data.get("devices", []):
        if d["name"] == device_name:
            return d["id"]
    return None

def play_track(access_token, track_uri, device_id):
    data = json.dumps({"uris": [track_uri]}).encode()
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/me/player/play?device_id={device_id}",
        data=data, method="PUT"
    )
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f"  ⚠  Playback error: {e.status} {e.reason}")

def enable_autoplay(access_token, device_id):
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/me/player/repeat?state=context&device_id={device_id}",
        data=b"", method="PUT"
    )
    req.add_header("Authorization", f"Bearer {access_token}")
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError:
        pass

def queue_recommendations(access_token, seed_tracks, device_id, limit=20):
    queued = 0
    seen_uris = {t["uri"] for t in seed_tracks}
    pool = []
    for t in seed_tracks[:3]:
        artist_id = t["artists"][0]["id"]
        albums = api_get(f"/artists/{artist_id}/albums?include_groups=album,single&limit=5&market=UY", access_token)
        for album in albums.get("items", []):
            album_tracks = api_get(f"/albums/{album['id']}/tracks?limit=10", access_token)
            for rt in album_tracks.get("items", []):
                if rt["uri"] not in seen_uris:
                    seen_uris.add(rt["uri"])
                    pool.append(rt)
    random.shuffle(pool)
    for rt in pool[:limit]:
        req = urllib.request.Request(
            f"https://api.spotify.com/v1/me/player/queue?uri={urllib.parse.quote(rt['uri'])}&device_id={device_id}",
            data=b"", method="POST"
        )
        req.add_header("Authorization", f"Bearer {access_token}")
        try:
            urllib.request.urlopen(req)
            queued += 1
        except urllib.error.HTTPError:
            pass

def progress_bar(elapsed, total, width=30):
    pct = min(elapsed / total, 1.0)
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    elapsed_s = f"{int(elapsed)//60}:{int(elapsed)%60:02d}"
    total_s   = f"{int(total)//60}:{int(total)%60:02d}"
    print(f"\r  [{bar}] {elapsed_s}/{total_s}", end="", flush=True)

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse, time
    parser = argparse.ArgumentParser(description="Your Spotify top tracks CLI")
    parser.add_argument("query", nargs="?", help="Search query: song name, artist, or both")
    parser.add_argument("--limit", type=int, default=10, help="Number of tracks (default: 10)")
    parser.add_argument("--range", choices=["short_term", "medium_term", "long_term"],
                        default="medium_term", help="short=4w  medium=6mo  long=all-time")
    parser.add_argument("--play", action="store_true", help="Play tracks")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle playback order")
    parser.add_argument("--artist", help="Filter top tracks by artist name (partial match)")
    args = parser.parse_args()

    token = get_access_token()

    if args.query:
        tracks = search_tracks(token, args.query, limit=args.limit)
        print(f"\n🔍  Results for '{args.query}':\n")
    else:
        tracks = get_top_tracks(token, limit=args.limit, time_range=args.range, artist_filter=args.artist)
        range_label = {"short_term": "last 4 weeks", "medium_term": "last 6 months", "long_term": "all time"}
        label = f"top {args.limit} tracks ({range_label[args.range]})"
        if args.artist:
            label += f" · artist filter: '{args.artist}'"
        print(f"\n🎵  Your {label}:\n")

    if args.shuffle:
        random.shuffle(tracks)

    for i, t in enumerate(tracks, 1):
        artists = ", ".join(a["name"] for a in t["artists"])
        print(f"  {i:>2}. {t['name']} — {artists}")

    if args.play:
        ensure_spotifyd()
        device_id = get_device_id(token)
        if not device_id:
            print("  ⚠  spotifyd device 'spoty-cli' not found. Is spotifyd running?")
            sys.exit(1)
        print("\nStarting playback (Ctrl+C to skip, Ctrl+C twice to quit)...\n")
        for i, t in enumerate(tracks):
            artists = ", ".join(a["name"] for a in t["artists"])
            duration = t["duration_ms"] / 1000
            print(f"▶  {t['name']} — {artists}")
            try:
                play_track(token, t["uri"], device_id)
                if i == 0:
                    threading.Thread(
                        target=queue_recommendations, args=(token, tracks, device_id), daemon=True
                    ).start()
                if i == len(tracks) - 1:
                    enable_autoplay(token, device_id)
                start = time.time()
                while True:
                    elapsed = time.time() - start
                    if elapsed >= duration:
                        break
                    progress_bar(elapsed, duration)
                    time.sleep(0.5)
                print()  # newline after progress bar
            except KeyboardInterrupt:
                print("\n  ⏭  Skipped")

if __name__ == "__main__":
    main()
