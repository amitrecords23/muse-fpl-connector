# Fantasy Premier League

- `custom.fpl` connects Muse to Fantasy Premier League through the local MCP server `fantasy-premier-league-mcp` version 0.3.2. It reads your squad, players, fixtures and deadlines, and it changes transfers, captain and lineup only after your approval in chat.

- The server runs locally over stdio and nothing is exposed off the machine. Sign in happens once in a browser window on FPL's own page, and the server keeps only a refresh token in `~/.fpl-mcp/credentials.json`.

- Helpers live in `~/workspace/custom-connectors/custom.fpl/bin/`. The helper `client.py` spawns the pinned server, lists its tools and calls one tool at a time.

## Connect

- Store your FPL team id first. Your id is the number in your team URL at `fantasy.premierleague.com/entry/<TEAM_ID>/event/1`.

```text
echo '{"team_id": 0}' > /tmp/fpl-setup.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_setup --arguments-file /tmp/fpl-setup.json
```

- Sign in only when you are present and ready. Run `fpl_login` and sign in yourself in the browser window it opens. The server never sees your password.

```text
echo '{}' > /tmp/fpl-empty.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_login --arguments-file /tmp/fpl-empty.json
```

- Check the session before any write, and renew it if needed.

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_auth_status --arguments-file /tmp/fpl-empty.json
```

- Prove access with a harmless read before the first change in a conversation.

```text
echo '{"query": "Wirtz", "limit": 5}' > /tmp/fpl-search.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_search_players --arguments-file /tmp/fpl-search.json
```

## Approval gate

- Never run a write with `dry_run=false` without a prior `dry_run=true` preview shown to the user and the user's explicit approval in chat for that exact change.

- Run every write first as a preview with `dry_run=true`. Show the user the resulting squad, the points hit, the bank afterwards and any rule breaches.

- Only after the user approves that exact preview, run the same call again with `dry_run=false` and `--allow-submit`. The client refuses a `dry_run=false` write without `--allow-submit`.

- A write that times out or ends uncertainly must be checked by re-reading the team before any retry, because the first request may have completed.

## Credentials

- The FPL session lives in the server's own owner-only file at `~/.fpl-mcp/credentials.json`. It holds a refresh token, not a password, and it is readable only by the user.

- Never put a key, token, password or cookie in this doc, a helper, a command argument, an environment variable or a log. Never ask the user to paste one in chat.

- Never use `fpl_set_token`. That tool takes a hand-pasted bearer token, it lasts about an hour, it cannot renew itself, and it is not in the client's allowed tools.

- The stdio client makes no HTTP requests of its own, so it follows no redirects. The server talks only to `fantasy.premierleague.com`, `account.premierleague.com` and `footballapi.pulselive.com`.

- On a 401 or 403, check the session first with `fpl_auth_status`. Sign in again with `fpl_login` when the session has lapsed.

## List tools

- List every tool the server offers, following the cursor until none remains.

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py list-tools
```

- The client allows only the tool names verified in that list. A tool the server adds later stays blocked until you review it and add its exact name to `ALLOWED_TOOLS` in `bin/client.py`.

## Read your squad

- Show the starting XI, bench, captain, formation, bank and free transfers remaining. This read needs a signed-in session and a stored team id.

```text
echo '{}' > /tmp/fpl-empty.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_my_squad --arguments-file /tmp/fpl-empty.json
```

- Read the season summary for points, overall rank, rank by gameweek, chips and hits.

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_season_summary --arguments-file /tmp/fpl-empty.json
```

- Read one gameweek report for per-player scoring, bench and auto-subs.

```text
echo '{"gameweek": 12}' > /tmp/fpl-gw.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_gameweek_report --arguments-file /tmp/fpl-gw.json
```

## Research players and fixtures

- Search players by name to get id, price, club, points and form.

```text
echo '{"query": "Wirtz", "limit": 5}' > /tmp/fpl-search.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_search_players --arguments-file /tmp/fpl-search.json
```

- Read one player in depth for stats, fixtures, set pieces and injury news.

```text
echo '{"player": 366}' > /tmp/fpl-player.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_player --arguments-file /tmp/fpl-player.json
```

- Compare two or more players side by side on headline stats.

```text
echo '{"players": [366, 411]}' > /tmp/fpl-compare.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_compare_players --arguments-file /tmp/fpl-compare.json
```

- Rank the best players in the game, filtered by position, club and price.

```text
echo '{"limit": 5}' > /tmp/fpl-top.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_top_players --arguments-file /tmp/fpl-top.json
```

- Rank clubs by how easy their next few fixtures are, with a lower score meaning easier fixtures.

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_fixture_ticker --arguments-file /tmp/fpl-empty.json
```

- Read differentials in both directions, against the global pool or one mini-league.

```text
echo '{"scope": "global"}' > /tmp/fpl-diff.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_differentials --arguments-file /tmp/fpl-diff.json
```

- Read a classic mini-league table and your position in it.

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_league_standings --arguments-file /tmp/fpl-empty.json
```

- Export the player pool, fixtures or per-gameweek history as CSV for your own modelling.

```text
echo '{"limit": 50}' > /tmp/fpl-export.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_export_players --arguments-file /tmp/fpl-export.json
```

## Preview a change

- Preview a captain change first. The preview keeps the XI as it is.

```text
echo '{"captain": "Wirtz", "dry_run": true}' > /tmp/fpl-captain-preview.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_set_captain --arguments-file /tmp/fpl-captain-preview.json
```

- Preview a full lineup change with starting XI, bench order, captain and vice-captain. It may also play Bench Boost or Triple Captain.

```text
echo '{"starting_xi": [], "bench_order": [], "captain": "Wirtz", "vice_captain": "Haaland", "dry_run": true}' > /tmp/fpl-lineup-preview.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_set_lineup --arguments-file /tmp/fpl-lineup-preview.json
```

- Preview transfers with matching lists of players out and players in. It reports the cost in points, the resulting bank balance and any rule breaches. It may also play a wildcard or free hit.

```text
echo '{"players_out": [], "players_in": [], "dry_run": true}' > /tmp/fpl-transfers-preview.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_make_transfers --arguments-file /tmp/fpl-transfers-preview.json
```

## Submit an approved change

- Submit only the exact change the user approved from its preview. Use the same arguments with `dry_run=false` and add `--allow-submit`.

```text
echo '{"captain": "Wirtz", "dry_run": false}' > /tmp/fpl-captain-submit.json
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_set_captain --arguments-file /tmp/fpl-captain-submit.json --allow-submit
```

- Read the team again after a submit and confirm the change landed as approved.

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_my_squad --arguments-file /tmp/fpl-empty.json
```

- Sign out when the user asks. It deletes the saved session from this machine and revokes it at FPL.

```text
python3 ~/workspace/custom-connectors/custom.fpl/bin/client.py call-tool --name fpl_logout --arguments-file /tmp/fpl-empty.json
```

## Recover from errors

- `isError: true` with `Error executing tool` means the server call failed. Read the tool result first, then check the session with `fpl_auth_status` and the team id with `fpl_setup`.

- A 401 or 403 on a write means no usable session. Sign in again with `fpl_login` and run the preview again from the start.

- A timed-out write means the outcome is unknown. Re-read the team with `fpl_my_squad` before trying again, because the first request may have completed.

- A failed read against the public API usually means the VM proxy settings reached the server child in a form httpx cannot parse. The client already cleans `NO_PROXY` for the child, so report the exact error instead of retrying the same call unchanged.

## Limits

- FPL offers no official API key or OAuth flow. The server uses the public API for reads and a browser sign-in with authorization code and PKCE for writes, and its API shapes can change between seasons.

- The upstream package has no license file in its PyPI metadata. It is listed in the official MCP Registry as `io.github.anubabajide/fpl` and packaged on PyPI as `fantasy-premier-league-mcp` version 0.3.2.

- The server runs locally only. It cannot work from another machine, and `fpl_login` needs a browser window on this machine.

- Verified by running them: `list-tools` returned 24 tools in one page, `fpl_search_players` for Wirtz returned one match, `fpl_top_players` returned the pool with the Gameweek 12 deadline, and `fpl_auth_status` returned not signed in.

- Untested: `fpl_login`, `fpl_setup`, `fpl_my_squad`, `fpl_season_summary`, `fpl_gameweek_report`, `fpl_best_performers`, `fpl_player`, `fpl_compare_players`, `fpl_fixture_ticker`, `fpl_differentials`, `fpl_league_standings`, `fpl_export_players`, `fpl_export_fixtures`, `fpl_export_gameweek_history`, `fpl_team_news`, `fpl_predicted_lineups`, and all three write tools. No write with `dry_run=false` has ever been run, and no login has been attempted.

- `fpl_set_token` exists on the server but is not in the client's allowed tools, so the client refuses it.

## Related skills

- [Fantasy Premier League team management](~/workspace/custom-skills/fpl/SKILL.md)

- Use `muse.skill_search` to find other skills and `muse.connector_search` to find other connectors.
