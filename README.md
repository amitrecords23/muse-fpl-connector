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
- For the one-time sign-in, use `bin/persistent_login.py` (see
  "First-time setup — sign in" below). It does not need a browser on
  the machine running the connector. Installing Playwright Chromium
  (`uvx --from playwright playwright install chromium`) is only
  needed if you want the server itself to open a browser window, which
  does not work on a headless machine.

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
one-liner, which clones the repo for you. For the first sign-in, use
`bin/persistent_login.py` as described below — do not rely on the
server opening a browser window on a headless machine.
(The `chmod +x` step is needed because GitHub's file push does not
preserve the executable bit.)

### Manual install

Copy the files into your Muse workspace:

```text
# Connector (from this repo root)
cp CONNECTOR.md connector.yaml ~/workspace/custom-connectors/custom.fpl/
cp bin/client.py bin/persistent_login.py ~/workspace/custom-connectors/custom.fpl/bin/

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

## First-time setup — sign in

Do this once, when you are present and ready. After it, the saved
session renews itself, and you do not need to sign in again for
normal reads and writes unless FPL logs the session out.

FPL's identity provider rejects password grants, so there is no way to
sign in by handing over an email and password. The supported flow is
authorization-code + PKCE in a real browser. The server catches the
redirect, exchanges the code, and saves only a refresh token in
`~/.fpl-mcp/credentials.json`, readable only by you. The server never
sees your password: you sign in yourself, on FPL's own page, in your
own browser.

### The trap: do not do the two-call redirect flow

`fpl_login` keeps its pending sign-in (the state and the PKCE secret)
only in the memory of the server process that created it, and it
expires after 20 minutes. The normal client, `bin/client.py`, starts
a fresh server for every call and kills it afterwards. So this will
**always fail**:

1. Call `fpl_login` once to get a sign-in link.
2. Sign in in your browser.
3. Call `fpl_login` again with the redirect address you landed on.

The second call is a new server with no pending sign-in, and it
answers: "No sign-in is waiting for that address; it may have
expired. Run `fpl_login` to start again." That is not a timeout and
not a problem with the address — the `/en/` form of the redirect
address is accepted. The pending sign-in simply died with the first
server process.

Do not try to fix this by installing a browser on a headless machine
either: the server's headed browser window is invisible to you there,
so you cannot sign in in it.

### The working way: one server, kept alive

Use `bin/persistent_login.py`. It starts the server **once**, asks it
for a sign-in link without opening a browser, waits for the redirect
address, and hands that address back to the **same** live server,
where the pending sign-in still exists. It then checks the session.

1. Start the driver in the background. It waits up to 19 minutes
   (the pending sign-in expires after 20).

```text
cd ~/workspace/custom-connectors/custom.fpl
nohup python3 bin/persistent_login.py > persistent-login-live.log 2>&1 &
```

2. Read the log and take the fresh `sign_in_url` it prints (step
   STEP1). Give that link to the person signing in. Do not use a link
   from an earlier run — every run makes a new one, and the old ones
   are dead.

3. Open the link in a real browser and sign in on FPL's own page.
   Use a browser that can capture the address you land on: on a
   phone the code in the address flashes by too fast to copy by hand,
   so use a desktop or cloud browser that records the address.
   Make no team changes in that browser — just sign in.

4. Capture the full address you land on. It starts with
   `https://fantasy.premierleague.com/` and contains `?code=` and
   `&state=` (the `/en/` form is fine). Write it, exactly as it is,
   into the file the driver is watching:

```text
printf '%s' '<the full address you landed on>' > ~/workspace/custom-connectors/custom.fpl/.login-redirect.txt
```

   The driver picks it up within a few seconds. It deletes the file
   after reading it, so a stale code cannot be replayed.

5. Read the log again. Success looks like this:

```text
STEP2 fpl_login redirect_url (same server process):
{"signed_in": true, "status": "complete", "logged_in_as": "...", "entry_id": ...}
STEP3 fpl_auth_status:
{"authenticated": true, "logged_in_as": "...", "entry_id": ...}
LOGIN COMPLETE
```

6. Verify with a normal one-shot read — this now works, because the
   session is saved:

```text
echo '{}' > /tmp/fpl-empty.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_my_squad --arguments-file /tmp/fpl-empty.json
```

   That should return your team, live and authenticated.

### Troubleshooting the sign-in

- "No sign-in is waiting for that address" — the server that issued
  the link is no longer running. Start a **fresh** driver for a
  fresh link and sign in again; the old link and code are dead.
- The driver times out (19 minutes) or the machine restarts while it
  is waiting — same fix: start a fresh driver, use its new link.
- The code is used once and expires within minutes, so hand the
  redirect address back promptly, in the same run.
- After a successful login, the refresh token in
  `~/.fpl-mcp/credentials.json` renews automatically. Normal
  one-shot `client.py` calls work from then on. If `fpl_auth_status`
  later says you are not signed in, run the persistent driver again
  from step 1.

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
- `bin/persistent_login.py` — first-time sign-in driver: keeps one
  server alive so the pending sign-in survives from the sign-in link
  to the redirect. See "First-time setup — sign in" above. It never
  opens a browser and never attempts a team change.
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
- The server runs locally only. It cannot work from another machine.
  First-time sign-in must use `bin/persistent_login.py` — the
  per-call client kills the pending sign-in, and a headed browser
  window on a headless machine is invisible to the user. See
  "First-time setup — sign in" above.
- Verified by running them: `list-tools` returned 24 tools,
  `fpl_search_players` for Wirtz returned one match, `fpl_top_players`
  returned the pool with the Gameweek 12 deadline, `fpl_setup`
  stored a team id, `fpl_login` completed through
  `bin/persistent_login.py` (signed in, authenticated, token renews
  automatically), and `fpl_my_squad` returned the team live and
  authenticated. All write tools are still untested without an
  approved change — see `CONNECTOR.md` for the full untested list.
