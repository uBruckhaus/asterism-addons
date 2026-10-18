# Asterism add-ons

Add-ons for [Asterism](https://github.com/uBruckhaus/asterism), the map of your AI agents, models
and tools. Asterism only loads add-ons **signed by its author** (Uwe Bruckhaus, key fingerprint
`SHA256:e5cC634Ke3Our5LAeSc88qs22NKZEHTncBW5Ig3amWQ`): before anything of an add-on runs, Asterism
checks the signature, every file's SHA-256 and that no file was added.

| Add-on | What it adds | Privacy |
| --- | --- | --- |
| [Insights](insights/) | Session topics per project on the details pages of Claude Code, OpenCode and Hermes, and a summary of your last 30 days by your own Claude Code (only on a click, after a preview of exactly what is sent) | titles, summary |

## How an add-on looks

A folder `<id>/` with

- `addon.json`: id, name, version, the add-on API version it needs, kind (`feature`, `agent`,
  `provider`), summary and description, privacy level (`numbers`, `titles`, `summary`),
  capabilities (`agent`, `provider`, `installer`), and in plain words what it reads and sends;
- `addon.py`: `register(api)`, built only on Asterism's add-on API (`addon_api.py` in Asterism) and
  the Python standard library;
- `translations/<language>.json`: its own strings (same format as Asterism's);
- `MANIFEST.sha256` and `SIGNATURE`, written by `tools/release.sh`.

## Releasing

```sh
tools/release.sh insights      # signs (asks for the key's passphrase), zips, rebuilds and signs catalog.json
```

Then a GitHub release `insights-<version>` with `dist/insights-<version>.zip`, and `catalog.json` +
`catalog.sig` committed to `main`: Asterism reads the catalog from there (only when *Look for add-ons
online* is on) and checks its signature before it uses anything of it.

## Tests

```sh
ASTERISM=~/Projects/asterism python3 -m unittest discover -s tests
```

MIT licensed.
