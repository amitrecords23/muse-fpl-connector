# muse-fpl-connector

A Muse-specific Fantasy Premier League connector — read your team and,
after your approval in chat, change transfers, captain and lineup.

This is a wrapper around `fantasy-premier-league-mcp` version 0.3.2. That
server is already published in the official MCP Registry as
`io.github.anubabajide/fpl` and on PyPI as `fantasy-premier-league-mcp`.
This repo does **not** copy its code. It depends on it via PyPI / `uvx`,
and adds a Muse stdio client, a connector doc, and a skill with an
approval gate for writes.

## What it does

- Read your squad, season summary, gameweek reports, players, fixtures,
  differentials and mini-league standings.
- Preview transfers, captain changes and lineup changes with
  `dry_run=true` first.
- Submit a change only after you approve that exact preview in chat.

The server runs locally over stdio. Nothing is exposed off the machine.

## Requirements

- Python 3.12+
- `uv` / `uvx` (recommended), or a local virtual environment
- For the one-time sign-in, a local Chromium installation for Playwright:
  `uvx --from playwright playwright install chromium`

Install the server without installing this repo:

```text
uvx fantasy-premier-league-mcp@0.3.2
```

Or install it with `uv`:

```text
uv tool install fantasy-premier-league-mcp
```

## Install this connector in Muse

### One-command install

```text
curl -fsSL https://raw.githubusercontent.com/amitrecords23/muse-fpl-connector/main/install.sh | bash
```

Or, from a local clone:

```text
git clone https://github.com/amitrecords23/muse-fpl-connector
cd muse-fpl-connector
chmod +x install.sh
./install.sh
```

`install.sh` copies the connector into
`~/workspace/custom-connectors/custom.fpl/` and the skill into
`~/workspace/custom-skills/fpl/`. It is safe to re-run, and it never
touches your FPL login, credentials, or team config. It needs Python
3.12+, `uv`/`uvx` (it warns if they are missing), and `git` for the
one-liner, which clones the repo for you. For `fpl_login` you also need
Playwright Chromium: `uvx --from playwright playwright install chromium`.
(The `chmod +x` step is needed because GitHub's file push does not
preserve the executable bit.)

### Manual install

Copy the files into your Muse workspace:

```text
# Connector (from this repo root)
cp CONNECTOR.md connector.yaml ~/workspace/custom-connectors/custom.fpl/
cp bin/client.py ~/workspace/custom-connectors/custom.fpl/bin/client.py

# Skill
cp skills/fpl/SKILL.md skills/fpl/skill.yaml ~/workspace/custom-skills/fpl/
```

The client in `bin/client.py` spawns the pinned server
`fantasy-premier-league-mcp==0.3.2` as a child process over stdio. If a
`venv/bin/python` exists under `custom.fpl/`, it uses that; otherwise it
falls back to `uvx fantasy-premier-league-mcp@0.3.2`.

Verify it:

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py list-tools
```

That should list 24 tools in one page.

## Set your team ID

Your team ID is the number in your team URL at
`fantasy.premierleague.com/entry/<TEAM_ID>/event/1`.

```text
echo '{"team_id": 0}' > /tmp/fpl-setup.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_setup --arguments-file /tmp/fpl-setup.json
```

Replace `0` with your real team ID.

## Sign in once (fpl_login)

Sign in only when you are present and ready. Run `fpl_login` and sign in
yourself in the browser window it opens, on FPL's own page. The server
never sees your password.

FPL's identity provider rejects password grants, so there is no way to
sign in by handing over an email and password. The supported flow is
authorization-code + PKCE in a real browser. The server catches the
redirect, exchanges the code, and saves only a refresh token in
`~/.fpl-mcp/credentials.json`, readable only by you.

```text
echo '{}' > /tmp/fpl-empty.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_login --arguments-file /tmp/fpl-empty.json
```

Check the session before any write:

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_auth_status --arguments-file /tmp/fpl-empty.json
```

Reads that do not need your team work without a login. The three write
tools need a session: `fpl_set_captain`, `fpl_set_lineup`,
`fpl_make_transfers`.

## Approval gate — how changes work

Never submit a change without a preview shown to you and your explicit
approval in chat for that exact change.

1. Preview first with `dry_run=true`. Show the resulting squad, the
   points hit, the bank afterwards, and any rule breaches.

```text
echo '{"captain": "Wirtz", "dry_run": true}' > /tmp/fpl-captain-preview.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_set_captain --arguments-file /tmp/fpl-captain-preview.json
```

2. Only after you approve that exact preview, run the same call again
   with `dry_run=false` and `--allow-submit`. The client refuses a
   `dry_run=false` write without `--allow-submit`, and the server itself
   defaults every write to `dry_run=true`.

```text
echo '{"captain": "Wirtz", "dry_run": false}' > /tmp/fpl-captain-submit.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_set_captain --arguments-file /tmp/fpl-captain-submit.json --allow-submit
```

3. Re-read the team and confirm the change landed as approved.

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_my_squad --arguments-file /tmp/fpl-empty.json
```

If a write times out or ends uncertainly, re-read the team before any
retry, because the first request may have completed.

Do not use `fpl_set_token`. It takes a hand-pasted bearer token, lasts
about an hour, cannot renew itself, and is deliberately not in the
client's allowed tools.

## Files in this repo

- `install.sh` — one-command installer: copies the connector and skill
  into your Muse workspace (see "One-command install" above).
- `CONNECTOR.md` — full connector doc: connect, approval gate,
  credentials, every operation, recovery and limits.
- `connector.yaml` — `custom.fpl` descriptor for Muse.
- `bin/client.py` — stdio MCP client wrapper (23 of 24 server tools
  allowed; `fpl_set_token` excluded).
- `skills/fpl/SKILL.md` and `skills/fpl/skill.yaml` — the Muse skill
  for managing a team with the approval gate.
- `LICENSE` — MIT for the wrapper files in this repo only.

## Limits

- FPL offers no official API key or OAuth flow. The server uses the
  public API for reads and a browser sign-in with authorization code and
  PKCE for writes. Its API shapes can change between seasons.
- The upstream `fantasy-premier-league-mcp` package has no license file
  in its PyPI metadata. It is not copied here; it is depended on via
  PyPI / `uvx`.
- The server runs locally only. It cannot work from another machine, and
  `fpl_login` needs a browser window on the machine running it.
- Verified by running them: `list-tools` returned 24 tools,
  `fpl_search_players` for Wirtz returned one match, `fpl_top_players`
  returned the pool with the Gameweek 12 deadline, and
  `fpl_auth_status` returned not signed in. Login, `fpl_setup`,
  `fpl_my_squad` and all write tools are untested without a signed-in
  session — see `CONNECTOR.md` for the full untested list.
