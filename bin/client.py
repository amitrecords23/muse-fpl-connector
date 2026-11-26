#!/usr/bin/env python3
"""Muse stdio client for the local Fantasy Premier League MCP server.

Spawns the pinned server `fantasy-premier-league-mcp==0.3.2` as a child
process over stdio and speaks JSON-RPC to it. Nothing is exposed off the
machine. No credential is passed to the child on the command line, in an
environment variable, or in an arguments file. The server keeps its own
session, a refresh token in ~/.fpl-mcp/credentials.json, after the user
signs in on FPL's own page through `fpl_login`.

Commands:
  list-tools [--cursor <cursor>]
  call-tool --name <tool> --arguments-file <path-to-json>
            [--allow-submit]

Approval gate: the three write tools (`fpl_set_captain`, `fpl_set_lineup`,
`fpl_make_transfers`) default to dry_run=true inside the server and only
preview a change. This client refuses a write call with dry_run=false
unless `--allow-submit` is also passed. Only pass that flag after a
dry_run=true preview has been shown to the user in chat and the user has
explicitly approved that exact change. A write that times out or ends
uncertainly must be checked by re-reading the team before any retry.
"""

import argparse
import json
import os
import select
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONNECTOR_DIR = HERE.parent
VENV_PYTHON = CONNECTOR_DIR / "venv" / "bin" / "python"
PINNED_PACKAGE = "fantasy-premier-league-mcp==0.3.2"

# Exact tool names verified by running list-tools against 0.3.2.
# A tool the server adds later stays blocked until it is reviewed and added.
ALLOWED_TOOLS: set[str] = {
    # Setup and auth (read-only except fpl_setup, which stores a team id).
    "fpl_setup",
    "fpl_login",
    "fpl_logout",
    "fpl_auth_status",
    # Read-only team and player research.
    "fpl_my_squad",
    "fpl_season_summary",
    "fpl_gameweek_report",
    "fpl_best_performers",
    "fpl_top_players",
    "fpl_player",
    "fpl_compare_players",
    "fpl_search_players",
    "fpl_fixture_ticker",
    "fpl_differentials",
    "fpl_league_standings",
    "fpl_export_players",
    "fpl_export_fixtures",
    "fpl_export_gameweek_history",
    "fpl_team_news",
    "fpl_predicted_lineups",
    # Writes. Approval-gated, see the module docstring.
    "fpl_set_captain",
    "fpl_set_lineup",
    "fpl_make_transfers",
}

WRITE_TOOLS: set[str] = {
    "fpl_set_captain",
    "fpl_set_lineup",
    "fpl_make_transfers",
}

# fpl_set_token is deliberately NOT in ALLOWED_TOOLS. It accepts a
# hand-pasted bearer token, which lasts about an hour, cannot renew itself,
# and is retained only until the server stops. Never use it unless the user
# explicitly asks for that fallback, and then only after reviewing it again.

PROTOCOLS = ("2025-06-18", "2025-03-26")
TIMEOUT_SECONDS = 45


class McpError(RuntimeError):
    """A transport or protocol failure with no automatic replay."""


def server_command() -> list[str]:
    """Launch the pinned server from the connector venv, else via uvx."""
    if VENV_PYTHON.exists():
        return [str(VENV_PYTHON), "-m", "fpl_mcp"]
    return ["uvx", "fantasy-premier-league-mcp@0.3.2"]


def child_env() -> dict[str, str]:
    """Environment for the server child.

    This VM's NO_PROXY contains bracketed IPv6 literals that httpx cannot
    parse, so constructing its client fails before any request. Strip those
    entries here. Everything else is inherited unchanged, including the
    egress proxy settings and SSL_CERT_FILE. No credential is added.
    """
    env = dict(os.environ)
    env["NO_PROXY"] = "localhost,127.0.0.1,::1"
    env["no_proxy"] = "localhost,127.0.0.1,::1"
    return env


class StdioClient:
    def __init__(self):
        self.proc = subprocess.Popen(
            server_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=child_env(),
        )
        self.sequence = 0
        self.protocol = PROTOCOLS[0]

    def _send(self, payload: dict) -> None:
        line = json.dumps(payload) + "\n"
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise McpError("MCP server closed its input; the operation was not replayed") from error

    def _read_message(self) -> dict:
        """Read one JSON-RPC message, waiting at most TIMEOUT_SECONDS."""
        fd = self.proc.stdout.fileno()
        ready, _, _ = select.select([fd], [], [], TIMEOUT_SECONDS)
        if not ready:
            raise McpError("MCP server did not respond in 45 seconds; check any write before retrying")
        line = self.proc.stdout.readline()
        if not line:
            raise McpError("MCP server closed its output; check any write before retrying")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            raise McpError("MCP server returned invalid JSON") from error
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
                # A server notification or request. This server does not
                # send requests the client must answer, so skip it.
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise McpError("MCP returned a JSON-RPC error; the operation was not replayed")
            result = message.get("result")
            if not isinstance(result, dict):
                raise McpError("MCP returned no result object")
            return result

    def initialize(self) -> None:
        for protocol in PROTOCOLS:
            self.protocol = protocol
            try:
                result = self._request("initialize", {
                    "protocolVersion": protocol,
                    "capabilities": {},
                    "clientInfo": {"name": "muse-custom-fpl", "version": "1"},
                })
            except McpError:
                raise
            negotiated = result.get("protocolVersion")
            capabilities = result.get("capabilities")
            if isinstance(negotiated, str) and negotiated in PROTOCOLS and isinstance(capabilities, dict):
                self.protocol = negotiated
                self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
                return
            raise McpError("MCP server did not negotiate a supported tool protocol")

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    listing = subparsers.add_parser("list-tools")
    listing.add_argument("--cursor")
    calling = subparsers.add_parser("call-tool")
    calling.add_argument("--name", required=True)
    calling.add_argument("--arguments-file", type=Path, required=True)
    calling.add_argument("--allow-submit", action="store_true",
                         help="Required for a write with dry_run=false, only after explicit user approval of the previewed change.")
    args = parser.parse_args()

    arguments: dict = {}
    if args.command == "call-tool":
        if args.name not in ALLOWED_TOOLS:
            parser.error("Inspect this operation's schema and add its exact name to ALLOWED_TOOLS")
        arguments = json.loads(args.arguments_file.read_bytes())
        if not isinstance(arguments, dict):
            parser.error("arguments must be a JSON object")
        if args.name in WRITE_TOOLS and arguments.get("dry_run") is False and not args.allow_submit:
            parser.error(
                "A write with dry_run=false needs --allow-submit. "
                "Run it first with dry_run=true, show the preview to the user, "
                "and only pass --allow-submit after the user approves that exact change."
            )
        if args.name in WRITE_TOOLS and "dry_run" not in arguments:
            # The server defaults dry_run to true, but be explicit so the
            # approval gate is visible in every call.
            arguments = dict(arguments, dry_run=True)

    client = StdioClient()
    try:
        client.initialize()
        if args.command == "list-tools":
            params = {"cursor": args.cursor} if args.cursor else {}
            result = client._request("tools/list", params)
        else:
            result = client._request("tools/call", {"name": args.name, "arguments": arguments})
    finally:
        client.close()
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get("isError") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (McpError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
