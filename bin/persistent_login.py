#!/usr/bin/env python3
"""Persistent FPL login driver: keep ONE MCP server alive for both halves of sign-in.

Why this exists
---------------
`fpl_login` keeps its pending sign-in (OAuth state + PKCE verifier) only in
the memory of the server process that created it, with a 20-minute TTL
(see `fpl_mcp/auth.py`: `PendingSignIn`, `PENDING_TTL_SECONDS = 20 * 60`).
The normal client (`client.py`) spawns a fresh server per call and kills it
afterwards, so a second call carrying the redirect URL back always fails with
"No sign-in is waiting for that address; it may have expired."

This driver spawns the server ONCE, calls `fpl_login` with
`open_browser=false` to get a fresh sign-in link, waits for the redirect URL
the user lands on, then calls `fpl_login` again with that `redirect_url` on
the SAME live server process, where the pending sign-in still exists. It then
verifies with `fpl_auth_status`.

It never opens a browser on this machine and never sees a password: the user
signs in on FPL's own page in their own / the cloud browser, and only the
redirect address (which contains a one-time code, useless without the PKCE
verifier held in this process) is handed back.

Usage (live run, run by the main agent):
    python3 bin/persistent_login.py
        # prints a fresh sign_in_url; give that link to the user
        # user signs in in their browser and pastes back the address they land on
        # (starts https://fantasy.premierleague.com/...?code=...&state=...)
    echo '<pasted redirect address>' > .login-redirect.txt
        # driver picks it up within ~5 s, completes the login, prints
        # fpl_auth_status, and exits 0 if authenticated.

Options:
    --redirect-file PATH   file to poll for the redirect URL
                           (default: <connector>/.login-redirect.txt)
    --redirect-url URL     complete immediately with this URL instead of polling
                           (used for testing; never pass a real code twice)
    --timeout-minutes N    how long to wait for the redirect (default 19;
                           pending TTL is 20 minutes, so never set above 19)
    --force                pass force=true to fpl_login (fresh sign-in even if
                           a saved session exists)

Exit codes: 0 authenticated, 1 login failed / not authenticated,
            2 timed out waiting for the redirect URL.

No FPL write is ever attempted here (no transfers, captain or lineup calls).
The redirect file is deleted after it is read, so a stale code cannot be
replayed by a later run.
"""

import argparse
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
CONNECTOR_DIR = HERE.parent
VENV_PYTHON = CONNECTOR_DIR / "venv" / "bin" / "python"
DEFAULT_REDIRECT_FILE = CONNECTOR_DIR / ".login-redirect.txt"
SERVER_STDERR_LOG = CONNECTOR_DIR / ".persistent-login-server-stderr.log"

PROTOCOLS = ("2025-06-18", "2025-03-26")
READ_TIMEOUT_SECONDS = 60


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class McpError(RuntimeError):
    pass


def server_command() -> list[str]:
    if VENV_PYTHON.exists():
        return [str(VENV_PYTHON), "-m", "fpl_mcp"]
    raise McpError(f"connector venv python not found at {VENV_PYTHON}")


def child_env() -> dict[str, str]:
    # Same NO_PROXY fix as bin/client.py: the VM's NO_PROXY contains bracketed
    # IPv6 literals that httpx cannot parse.
    env = dict(os.environ)
    env["NO_PROXY"] = "localhost,127.0.0.1,::1"
    env["no_proxy"] = "localhost,127.0.0.1,::1"
    return env


class StdioClient:
    """Minimal persistent JSON-RPC client over one long-lived server process."""

    def __init__(self):
        self.proc = subprocess.Popen(
            server_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=open(SERVER_STDERR_LOG, "ab"),
            text=True,
            bufsize=1,
            env=child_env(),
        )
        self.sequence = 0

    def _send(self, payload: dict) -> None:
        try:
            self.proc.stdin.write(json.dumps(payload) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise McpError("MCP server closed its input") from error

    def _read_message(self) -> dict:
        fd = self.proc.stdout.fileno()
        ready, _, _ = select.select([fd], [], [], READ_TIMEOUT_SECONDS)
        if not ready:
            raise McpError("MCP server did not respond in 60 seconds")
        line = self.proc.stdout.readline()
        if not line:
            raise McpError("MCP server closed its output")
        message = json.loads(line)
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise McpError("MCP server returned an invalid JSON-RPC message")
        return message

    def _request(self, method: str, params: dict) -> dict:
        self.sequence += 1
        request_id = self.sequence
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = self._read_message()
            if message.get("method") is not None:
                continue  # server notification; this server sends none we must answer
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise McpError(f"MCP JSON-RPC error: {message['error']}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise McpError("MCP returned no result object")
            return result

    def initialize(self) -> None:
        for protocol in PROTOCOLS:
            result = self._request("initialize", {
                "protocolVersion": protocol,
                "capabilities": {},
                "clientInfo": {"name": "muse-custom-fpl-persistent-login", "version": "1"},
            })
            negotiated = result.get("protocolVersion")
            if isinstance(negotiated, str) and negotiated in PROTOCOLS:
                self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
                log(f"MCP server started (pid {self.proc.pid}, protocol {negotiated})")
                return
        raise McpError("MCP server did not negotiate a supported tool protocol")

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a tool and return its parsed JSON result (or its error payload)."""
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        joined = "\n".join(texts).strip()
        try:
            parsed = json.loads(joined)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass
        return {"_raw": joined, "isError": bool(result.get("isError"))}

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


def state_from_url(url: str) -> str | None:
    try:
        return parse_qs(urlsplit(url).query).get("state", [None])[0]
    except Exception:
        return None


def wait_for_redirect(redirect_file: Path, timeout_seconds: float) -> str | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if redirect_file.exists():
            text = redirect_file.read_text(encoding="utf-8").strip()
            if text:
                redirect_file.unlink(missing_ok=True)
                return text
        time.sleep(5)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redirect-file", type=Path, default=DEFAULT_REDIRECT_FILE)
    parser.add_argument("--redirect-url", default=None)
    parser.add_argument("--timeout-minutes", type=float, default=19.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.timeout_minutes > 19:
        parser.error("timeout must be <= 19 minutes: the pending sign-in expires after 20")

    redirect_file: Path = args.redirect_file
    if redirect_file.exists():
        redirect_file.unlink()
        log(f"removed stale redirect file {redirect_file}")

    client = StdioClient()
    try:
        client.initialize()

        # Step 1: start the sign-in on this same server, no browser on this machine.
        login_args: dict = {"open_browser": False}
        if args.force:
            login_args["force"] = True
        first = client.call_tool("fpl_login", login_args)
        print("STEP1 fpl_login open_browser=false:")
        print(json.dumps(first, indent=2, ensure_ascii=False), flush=True)
        if first.get("signed_in"):
            log("already signed in; no redirect needed")
        else:
            sign_in_url = first.get("sign_in_url")
            if not sign_in_url:
                log(f"no sign_in_url returned: {first}")
                return 1
            log(f"sign_in_url state: {state_from_url(sign_in_url)}")
            log("Give the sign_in_url above to the user. They sign in on FPL's own "
                "page in their browser and paste back the address they land on.")

            # Step 2: wait for the redirect URL to be supplied.
            if args.redirect_url:
                redirect_url = args.redirect_url
                log("using --redirect-url supplied on the command line")
            else:
                log(f"waiting up to {args.timeout_minutes:g} min for redirect in "
                    f"{redirect_file} (pending TTL is 20 min)")
                redirect_url = wait_for_redirect(redirect_file, args.timeout_minutes * 60)
                if not redirect_url:
                    log("TIMEOUT: no redirect URL arrived before the pending sign-in "
                        "expires. Run the driver again for a fresh sign-in link; "
                        "the old link/code is dead.")
                    return 2
            log(f"redirect received (state in it: {state_from_url(redirect_url)})")

            # Step 3: complete on the SAME live server process.
            second = client.call_tool("fpl_login", {"redirect_url": redirect_url})
            print("STEP2 fpl_login redirect_url (same server process):")
            print(json.dumps(second, indent=2, ensure_ascii=False), flush=True)

        # Step 4: verify.
        status = client.call_tool("fpl_auth_status", {})
        print("STEP3 fpl_auth_status:")
        print(json.dumps(status, indent=2, ensure_ascii=False), flush=True)
        if status.get("authenticated"):
            log("LOGIN COMPLETE: authenticated as "
                f"{status.get('logged_in_as')} (entry {status.get('entry_id')})")
            return 0
        log("NOT authenticated after login attempt")
        return 1
    except McpError as error:
        log(f"error: {error}")
        return 1
    finally:
        client.close()
        log("server process stopped")


if __name__ == "__main__":
    raise SystemExit(main())
