# Fantasy Premier League team management

## Understand the request

- Ask what the user wants to change before you act, such as a transfer, a captain change or a lineup change.

- Read the current squad, the bank, the free transfers remaining and the next deadline before you suggest anything.

- Treat a transfer with no free transfers as costing points, and say the cost plainly when you present it.

## Research before you change

- Search players by name and read one player in depth for stats, fixtures, set pieces and injury news before you recommend a move.

- Compare the player going out with the player coming in side by side on headline stats.

- Rank clubs by fixture difficulty and check the deadline, because a move made after the deadline waits a gameweek.

## Approval gate

- Never submit a change without a preview shown to the user and the user's explicit approval in chat for that exact change.

- Run every write first with `dry_run=true`, show the user the resulting squad, the points hit, the bank afterwards and any rule breaches, then wait for approval.

- Only after approval, run the same change again with `dry_run=false` and `--allow-submit` through the connector client.

- Re-read the team after a submit and confirm the change landed as approved before you report success.

- When a write times out or ends uncertainly, re-read the team before you retry, because the first request may have completed.

## Make the change

- Use the connector client for every team change, and keep the team id stored with `fpl_setup` so later calls resolve it.

- Sign in only when the user is present, through `fpl_login` on FPL's own page, and check the session with `fpl_auth_status` before a write. For the first sign-in, use `bin/persistent_login.py`: it keeps one server alive from the sign-in link to the redirect. Do not do the two-call redirect flow with the per-call client — the second call is a fresh server with no pending sign-in, and it always fails with "No sign-in is waiting".

- Never ask the user for an FPL password, and never paste a bearer token by hand.

## Available connectors

- [Fantasy Premier League](~/workspace/custom-connectors/custom.fpl/CONNECTOR.md) for reading your squad and players and for making approved transfers, captain and lineup changes.

- Use `muse.skill_search` to find other skills and `muse.connector_search` to find other connectors.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Websites

- [Fantasy Premier League](https://fantasy.premierleague.com/) for anything the connector cannot do, such as signing in or checking a rule on the official site. Carry the exact change and the deadline into the browser task and verify the result there.

## Alternatives for better results

- Offer a cheaper or better-fixtured alternative when the user's first pick costs too much or faces a hard run of fixtures.

- Suggest holding a transfer when the points hit outweighs the expected gain, and say so plainly.
