#!/usr/bin/env python3
import argparse
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request

SECRETS_PATH = os.path.expanduser("~/.openclaw/secrets.json")
AUTH_URL = "https://raindrop.io/oauth/authorize"
TOKEN_URL = "https://raindrop.io/oauth/access_token"


def load_secrets(path: str):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_secrets(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def post_form(url: str, form: dict):
    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def cmd_authorize(args):
    s = load_secrets(args.secrets)

    client_id = args.client_id or s.get("RAINDROP_CLIENT_ID")
    client_secret = args.client_secret or s.get("RAINDROP_CLIENT_SECRET")
    redirect_uri = args.redirect_uri or s.get("RAINDROP_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        print("Missing required values. Provide --client-id --client-secret --redirect-uri (or store them in secrets.json).")
        return 1

    state = secrets.token_urlsafe(24)
    auth_query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(auth_query)

    print("1) Open this URL in your browser and authorize:")
    print(url)
    print("\n2) After redirect, paste the FULL redirected URL here:")
    redirected = input().strip()

    parsed = urllib.parse.urlparse(redirected)
    q = urllib.parse.parse_qs(parsed.query)
    code = (q.get("code") or [None])[0]
    got_state = (q.get("state") or [None])[0]
    err = (q.get("error") or [None])[0]

    if err:
        print(f"OAuth error: {err}")
        return 2
    if not code:
        print("No code found in redirect URL.")
        return 3
    if got_state != state:
        print("State mismatch. Abort.")
        return 4

    token = post_form(TOKEN_URL, {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    })

    access_token = token.get("access_token")
    refresh_token = token.get("refresh_token")
    expires_in = int(token.get("expires_in") or 0)
    if not access_token:
        print("Token exchange failed:", token)
        return 5

    now = int(time.time())
    s["RAINDROP_CLIENT_ID"] = client_id
    s["RAINDROP_CLIENT_SECRET"] = client_secret
    s["RAINDROP_REDIRECT_URI"] = redirect_uri
    s["RAINDROP_ACCESS_TOKEN"] = access_token
    s["RAINDROP_SECRET"] = access_token  # compatibility alias
    if refresh_token:
        s["RAINDROP_REFRESH_TOKEN"] = refresh_token
    if expires_in:
        s["RAINDROP_TOKEN_EXPIRES_AT"] = now + expires_in

    save_secrets(args.secrets, s)
    print("Saved tokens to", args.secrets)
    print("Now run: openclaw secrets reload")
    return 0


def refresh_tokens(s: dict):
    client_id = s.get("RAINDROP_CLIENT_ID")
    client_secret = s.get("RAINDROP_CLIENT_SECRET")
    refresh_token = s.get("RAINDROP_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError("Missing RAINDROP_CLIENT_ID / RAINDROP_CLIENT_SECRET / RAINDROP_REFRESH_TOKEN")

    token = post_form(TOKEN_URL, {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    })

    access_token = token.get("access_token")
    new_refresh = token.get("refresh_token") or refresh_token
    expires_in = int(token.get("expires_in") or 0)
    if not access_token:
        raise RuntimeError(f"Refresh failed: {token}")

    s["RAINDROP_ACCESS_TOKEN"] = access_token
    s["RAINDROP_SECRET"] = access_token
    s["RAINDROP_REFRESH_TOKEN"] = new_refresh
    if expires_in:
        s["RAINDROP_TOKEN_EXPIRES_AT"] = int(time.time()) + expires_in
    return s


def cmd_refresh(args):
    s = load_secrets(args.secrets)
    s = refresh_tokens(s)
    save_secrets(args.secrets, s)
    print("Refreshed RAINDROP token.")
    print("Run: openclaw secrets reload")
    return 0


def cmd_token(args):
    s = load_secrets(args.secrets)
    token = s.get("RAINDROP_ACCESS_TOKEN") or s.get("RAINDROP_SECRET")
    exp = int(s.get("RAINDROP_TOKEN_EXPIRES_AT") or 0)
    now = int(time.time())

    if args.auto_refresh and (not token or (exp and exp - now < args.refresh_margin_sec)):
        s = refresh_tokens(s)
        save_secrets(args.secrets, s)
        token = s.get("RAINDROP_ACCESS_TOKEN")

    if not token:
        print("No RAINDROP token found.")
        return 1
    print(token)
    return 0


def main():
    p = argparse.ArgumentParser(description="Raindrop OAuth helper with refresh-token support")
    p.add_argument("--secrets", default=SECRETS_PATH)
    sp = p.add_subparsers(dest="cmd", required=True)

    a = sp.add_parser("authorize", help="Run OAuth authorize flow and save tokens")
    a.add_argument("--client-id")
    a.add_argument("--client-secret")
    a.add_argument("--redirect-uri")
    a.set_defaults(func=cmd_authorize)

    r = sp.add_parser("refresh", help="Refresh access token using refresh_token")
    r.set_defaults(func=cmd_refresh)

    t = sp.add_parser("token", help="Print current access token")
    t.add_argument("--auto-refresh", action="store_true")
    t.add_argument("--refresh-margin-sec", type=int, default=300)
    t.set_defaults(func=cmd_token)

    args = p.parse_args()
    try:
        rc = args.func(args)
    except Exception as e:
        print("ERROR:", e)
        rc = 1
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
