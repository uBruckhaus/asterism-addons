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
  `provider`, `extension`), summary and description, privacy level (`numbers`, `titles`, `summary`),
  capabilities (`agent`, `provider`, `installer`), and in plain words what it reads and sends;
- `addon.py`: `register(api)`, built only on Asterism's add-on API (`addon_api.py` in Asterism) and
  the Python standard library;
- `translations/<language>.json`: its own strings (same format as Asterism's);
- `icon.svg` (optional): its own icon, for its card and its agent's box on the map. Shapes only
  (`path`, `circle`, `rect`, groups, gradients): no script, image, `use`, style, link or entity, at
  most 64 KB; one colour, it is tinted like the app's icons. Without it, the app's icon for the agent
  or its kind is used. The app brings all its other icons itself (`icons/Asterism`).
- `MANIFEST.sha256` and `SIGNATURE`, written by `tools/release.sh`.

## Agent add-ons and extension add-ons

Three layers, so a better feature never needs every add-on signed again:

- **Asterism (core)** derives features from facts: usage and tokens from an agent's sessions, the
  details cards, sign-in, connecting on the map.
- **An agent add-on** (`agent-<command>`, generated from the app's `adapters/<command>.toml` by
  `tools/release-adapters.sh`) holds only facts about that one agent.
- **An extension add-on** adds facts to an agent another add-on (or the app) brings, without
  replacing it.

### Agent add-on: required

| Where | What |
| --- | --- |
| `addon.json` | `id` (`agent-<command>`), `name`, `version`, `api: 1`, `needs` (`asterism >= x.y.z`), `kind: "agent"`, `capabilities: ["agent"]` (+ `installer` / `updater` when used), `provides: [command]`, `privacy: "numbers"`, `reads`, `detect` (`commands`, `paths`) |
| `agent.toml` | the facts about the agent (format: `docs/adapter-format.md` in Asterism); nothing in it runs |
| `hooks.py` (optional) | a little code for what facts cannot say (e.g. an agent's own session database), only for the hooks `agent.toml` names; no `addon.py` then |

### Agent add-on: optional facts (`harnesses.Harness`)

| Group | Fields |
| --- | --- |
| Identity, install | `label`, `full_name`, `icon`, `icon_font`, `spec`, `package`, `detect`, `install` (ways), `installer` (needs `installer`), `data`, `homepage` |
| Map, connecting | `local_llm`, `fixed_provider`, `self_served`, `short_model_flag`, `mcp`, `skills` |
| Details page | `sessions` (Projects; usage is derived from them), `usage` (own reader, wins over sessions), `limits` (plan and limits), `security`, `access` (with `logins` / `key` for Sign in), `login_status` |
| Updates | `self_update`, `latest` (needs `updater`; built-in agents only) |

A desktop's usage record (Omarchy's) wins over all of these for usage, plan and limits.

### Provider add-on: required

| Where | What |
| --- | --- |
| `addon.json` | `id` (`llm-<key>`, or `providers-online`), `name`, `version`, `api: 1`, `needs`, `kind: "provider"`, `capabilities: ["provider"]` (+ `installer`), `provides: [key, …]`, `privacy: "numbers"`, `reads`, `detect` |
| `addon.py` | `register(api)` → `api.add_provider(api.Provider(key, name, kind="local" or "online", …))` |

### Provider add-on: optional facts (`providers.Provider`)

| Group | Fields |
| --- | --- |
| Local LLM: finding, installing | `detect(processes)` (→ `api.Runtime`), `installer` (needs `installer`), `install` (ways), `data`, `homepage` |
| Local LLM: agents and the watcher | `connect_key`, `connect_label`, `stays_up`, `unload` |
| Local LLM: details page | `usage(runtime)` (own logs or metrics; else the app derives it from what the agents sent through it) |
| Online provider | `ids` (names in agents' settings), `agents` (agents that come with it) |

### Installing, updating and removing (both kinds)

The add-on says **what** to run; Asterism runs it: it shows the exact command first, runs only plain
words (no shell, `$`, pipes or quotes), in a terminal you watch, after your click; `sudo` asks for your
password there. Commands of the wrong form refuse the whole add-on when it loads.

| Way (`install=(api.Way(...), …)`, best first) | Install | Remove | Update |
| --- | --- | --- | --- |
| `Way("mise", spec=…)` | `mise use -g` | `mise unuse` + `uninstall` | `mise upgrade` |
| `Way("tool", tool="npm"\|"pipx"\|"uv", spec=…)` | its install | its uninstall | `npm update -g` / `pipx upgrade` / `uv tool upgrade` |
| `Way("package", packages=(("pacman", …), ("apt", …), …))` | `sudo <manager> install` | `sudo <manager> remove` | with the system's updates |
| `Way("command", argv=(…), update=(…), sudo=…)` | `argv` (a desktop's installer) | — | `update` |
| `Way("manual", url=…, note=…)` | its web page | its web page | — |
| `Way("installer")` | the app's install page | its Uninstall | its Update |

Updating follows the way it is installed now (mise, a package, or the app's own install).

**A program the app downloads itself**: `download=api.Download(...)` (capability `installer`):

| Field | What |
| --- | --- |
| `repo` | `owner/name` on GitHub; the newest release whose tag matches `tag` (no pre-releases) |
| `assets` | `((build, regex), …)`: the file per build ("vulkan", "cuda", "cpu" or ""), first = default; `gpu_builds=(("amd", "vulkan"), …)` picks per GPU |
| `binary`, `command` | the program inside the release (relative path), its name in `~/.local/bin` |
| `single_file` | the asset is the program itself (else an archive, unpacked) |
| `service`, `address`, `env`, `models_env` | a user service for a local LLM: plain-word argv with `{binary} {host} {port} {models} {folder}`, `127.0.0.1:<port>`, environment `NAME=value`, which variable holds the model folder |

The release's SHA-256 (GitHub's digest) is checked before anything is unpacked; nothing of the
release runs while installing. Versions live in folders with a `current` link; Update installs the
new one beside it, Uninstall removes program, link and service (never models).

**An agent's own updater**: `self_update=(…)` with the capability `updater`; `latest(channel)` tells
the newest version for the update hint (optional: without it, Update… is still in the menu).

### Extension add-on

| Where | What |
| --- | --- |
| `addon.json` | `kind: "extension"`, `extends: [command, …]`, `privacy`, `reads`, `capabilities: []` |
| `addon.py` | `api.extend_harness(command, field=value, …)` for an agent in `extends`, `api.extend_provider(key, field=value, …)` for a provider in `extends` |

- Agents, only these facts: `sessions`, `usage`, `limits`, `security`, `access`, `login_status`,
  `skills`, `mcp`, `local_llm`, `data`, `homepage`. Never what installs, updates or names an agent.
- Providers, only these facts: `usage`, `unload`, `data`, `homepage`, `agents`. Never what installs,
  finds or names a provider.
- A fact is used only where the agent left it empty; the first extension wins. What is not used is
  listed on the extension's page in Settings › Add-ons.
- It works while the agent is on the map (its own add-on switched on).

### Details sections (any add-on)

`api.add_details_section(builder, privacy, card="topics", page="agent")` puts a section on details
pages in the card `card`: `"statistics"` (Usage and tokens), `"health"`, `"topics"` (agents only;
Privacy: what the sessions were about), or a key of its own (`[a-z0-9-]`): a card of its own that the
add-on's first `ui.heading(...)` names.

- `page="agent"`: agents' pages, `builder(ui, box, harness, sessions, since)`.
- `page="llm"`: local LLMs' pages, `builder(ui, box, provider, runtime)`.

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
