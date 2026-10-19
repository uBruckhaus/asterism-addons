"""Insights, an Asterism add-on: a harness's sessions under their own titles, and a written summary
of the last 30 days by the user's own Claude Code.

- Titles: the titles each harness gave its sessions itself. Claude Code: only its "type":"ai-title"
  lines in ~/.claude/projects/**/*.jsonl are parsed (bounded and incremental, own regular files, no
  links), cached owner-only in this add-on's cache folder. OpenCode and Hermes: the id and title
  columns of their own databases, read-only. Shown as plain text.
- Topics: sessions with the same title together, ranked by their tokens (input, output and cache
  writes from the harness's own session numbers, as Asterism counts them; cache reads apart).
- Summarize with Claude…: only on a click, after a preview of exactly the text that goes out: the
  titles and numbers (never the conversations) go on stdin to the user's own `claude -p`, which runs
  in plan mode, without MCP servers, without saving a session, in an empty temporary folder, with a
  bounded answer.

Uses only the add-on API (api, ui) and the standard library.
"""

import json
import os
import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path

MAX_TITLE = 120
MAX_SUMMARY_INPUT = 24 * 1024
MAX_ANSWER = 64 * 1024
TIMEOUT = 180
MAX_LINE = 8 * 1024 * 1024
MAX_FILES = 5000
MAX_DIRS = 500
MAX_BYTES = 2 * 1024 ** 3          # per run; the rest is read next time
MAX_CACHE = 16 * 1024 * 1024
MAX_ROWS = 20000
TOP_TOPICS = 8
_TITLE = b'"ai-title"'             # a quick pre-filter; json decides
_SID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")


def clean_title(text) -> str:
    """A title as plain text: no control characters, at most MAX_TITLE characters."""
    if not isinstance(text, str):
        return ""
    return "".join(c if c.isprintable() else " " for c in text).strip()[:MAX_TITLE]


def _session_id(value) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 64 and set(value) <= _SID_CHARS


# --- Claude Code: its own ai-title lines ------------------------------------------------------------

def read_titles(path: Path, state: dict, budget: int) -> int:
    """The ai-title lines of a session file from state["offset"] on into state["titles"]."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        return 0
    with os.fdopen(fd, "rb") as handle:
        st = os.fstat(handle.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            return 0
        if state.get("inode") != st.st_ino or st.st_size < state.get("offset", 0):
            state.clear()
        state["inode"] = st.st_ino
        titles = state.setdefault("titles", {})
        offset = state.get("offset", 0)
        handle.seek(offset)
        read = 0
        while read < budget:
            line = handle.readline(MAX_LINE + 1)
            if not line or not line.endswith(b"\n"):
                if line and len(line) > MAX_LINE:
                    # Too long: skip it whole, or stop where it is still being written.
                    skipped = len(line)
                    while line and not line.endswith(b"\n"):
                        line = handle.readline(MAX_LINE + 1)
                        skipped += len(line)
                    if not line:
                        break
                    read += skipped
                    offset += skipped
                    continue
                break
            read += len(line)
            offset += len(line)
            if _TITLE not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get("type") == "ai-title" and _session_id(entry.get("sessionId")):
                title = clean_title(entry.get("aiTitle"))
                if title:
                    titles[entry["sessionId"]] = title
        state["offset"] = offset
        return read


def claude_titles(root: Path, cache: Path, write) -> dict:
    """{session id: title} (incremental, bounded; blocking). write(path, text): owner-only write."""
    try:
        fd = os.open(cache, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as handle:
            files = json.loads(handle.read(MAX_CACHE + 1)[:MAX_CACHE] or b"{}")
    except (OSError, ValueError):
        files = {}
    files = files if isinstance(files, dict) else {}
    seen, budget = {}, MAX_BYTES
    try:
        dirs = sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink())[:MAX_DIRS]
    except OSError:
        dirs = []
    paths = [path for folder in dirs for path in sorted(folder.glob("*.jsonl"))][:MAX_FILES]
    for path in paths:
        state = files.get(str(path)) if isinstance(files.get(str(path)), dict) else {}
        if not isinstance(state.get("titles", {}), dict):
            state = {}
        if budget > 0:
            budget -= read_titles(path, state, budget)
        seen[str(path)] = state
    try:
        write(cache, json.dumps(seen))
    except OSError:
        pass
    return {sid: clean_title(t) for state in seen.values() for sid, t in state.get("titles", {}).items()
            if isinstance(sid, str) and clean_title(t)}


# --- OpenCode and Hermes: their own title column ----------------------------------------------------

OPENCODE_DB = Path.home() / ".local/share/opencode/opencode.db"
HERMES_DB = Path.home() / ".hermes/state.db"
OPENCODE_SQL = ("SELECT id, title FROM session_v2 WHERE parent_id IS NULL AND title IS NOT NULL"
                " ORDER BY time_created DESC LIMIT ?")
HERMES_SQL = ("SELECT id, title FROM sessions WHERE parent_session_id IS NULL AND title IS NOT NULL"
              " ORDER BY started_at DESC LIMIT ?")


def db_titles(db, sql: str) -> dict:
    """{session id: title} from a read-only database connection (closed here), or {}."""
    if db is None:
        return {}
    try:
        rows = db.execute(sql, (MAX_ROWS,)).fetchall()
    except Exception:
        return {}
    finally:
        db.close()
    return {str(sid): clean_title(title) for sid, title in rows if clean_title(title)}


# --- topics ---------------------------------------------------------------------------------------------

def session_tokens(session) -> int:
    """Input, output and cache writes (cache reads apart), as Asterism's usage card counts them."""
    return sum(c[0] + c[1] + c[3] for c in session.tokens.values())


def topics(sessions: dict, titles: dict, since: float) -> tuple:
    """(topics by tokens, all tokens) of the sessions since `since`: sessions with the same title (case
    and spaces aside) are one topic; untitled ones are one together (title None)."""
    groups: dict = {}
    for sid, s in sessions.items():
        if s.last < since:
            continue
        title = titles.get(sid) or ""
        group = groups.setdefault(" ".join(title.casefold().split()), {
            "title": title or None, "tokens": 0, "active": 0.0, "sessions": 0, "folders": set(), "last": 0.0})
        group["tokens"] += session_tokens(s)
        group["active"] += s.active
        group["sessions"] += 1
        group["folders"].add(s.cwd or "?")
        group["last"] = max(group["last"], s.last)
    ranked = sorted(groups.values(), key=lambda g: (-g["tokens"], -g["last"]))
    return ranked, sum(g["tokens"] for g in ranked)


# --- the summary -------------------------------------------------------------------------------------

def summary_text(sessions: dict, titles: dict, since: float, name: str, tilde=str) -> str:
    """What Summarize sends: per project, its sessions' titles with time and tokens. No conversation."""
    lines = [f"Below are my {name} sessions of the last 30 days: project folder, then each session's "
             f"title (as {name} named it), date, working time and tokens. Summarize in a few short "
             "paragraphs what I mainly worked on, which topics took the most time and tokens, and anything "
             "worth noticing. Plain text, no headings."]
    by_project: dict = {}
    for sid, s in sessions.items():
        if s.last >= since:
            by_project.setdefault(s.cwd or "?", []).append((sid, s))
    for cwd, items in sorted(by_project.items(), key=lambda kv: -sum(s.active for _sid, s in kv[1])):
        lines.append("")
        lines.append(f"Project {tilde(cwd)}:")
        for sid, s in sorted(items, key=lambda item: -item[1].last):
            tokens = session_tokens(s)
            day = datetime.fromtimestamp(s.last).strftime("%Y-%m-%d")
            lines.append(f"- {titles.get(sid, 'untitled')} ({day}, {round(s.active / 60)} min, {tokens} tokens)")
    return "\n".join(lines)[:MAX_SUMMARY_INPUT]


def run_summary(api, text: str) -> tuple:
    """Claude's summary of `text` (blocking): (ok, answer or error)."""
    claude = shutil.which("claude")
    if claude is None:
        return False, api.tr("Claude Code is not installed.")
    with tempfile.TemporaryDirectory(prefix="asterism-summary-") as empty:
        out, ok = api.run_bounded(
            [claude, "-p", "--output-format", "text", "--permission-mode", "plan", "--strict-mcp-config",
             "--no-session-persistence"],
            max_bytes=MAX_ANSWER, timeout=TIMEOUT, stdin=text.encode("utf-8"), cwd=empty)
    answer = out.decode("utf-8", "replace").strip()
    answer = "".join(c if c.isprintable() or c in "\n\t" else " " for c in answer)
    return (ok and bool(answer)), (answer or api.tr("No answer from Claude Code."))


# --- the details page ----------------------------------------------------------------------------------

def show(api, ui, box, harness, sessions: dict, titles: dict, since: float):
    recent = {sid: s for sid, s in sessions.items() if s.last >= since}
    if not recent:
        return
    ui.heading(box, api.tr("Topics, last 30 days"))
    ranked, total = topics(recent, titles, since)
    if total:
        ui.heading(box, api.tr("Most tokens"))
        top = ui.boxed_list()
        for topic in ranked[:TOP_TOPICS]:
            folders = sorted(topic["folders"])
            where = api.trn("1 folder", "{0} folders", len(folders)).format(len(folders)) if len(folders) > 1 \
                else ui.tilde(folders[0]) if folders[0] != "?" else api.tr("Unknown folder")
            percent = 100 * topic["tokens"] / total
            top.append(ui.share_row(
                topic["title"] or api.tr("Untitled sessions"),
                " · ".join([where, api.trn("1 session", "{0} sessions", topic["sessions"]).format(topic["sessions"]),
                            ui.duration_text(topic["active"])]),
                api.tr("{0} tokens · {1} %").format(ui.short_number(topic["tokens"]),
                                                    "<1" if 0 < percent < 1 else round(percent)),
                topic["tokens"] / ranked[0]["tokens"]))            # the bar: next to the top topic
        box.append(top)
        ui.note(box, api.tr("Tokens: input, output and cache writes, from {0}'s own session files; cache reads "
                            "are not counted. Sessions with the same title are one topic.").format(harness.name))
        ui.heading(box, api.tr("By project"))
    listbox = ui.boxed_list()
    by_project: dict = {}
    for sid, s in recent.items():
        by_project.setdefault(s.cwd or "?", []).append((sid, s))
    for cwd, items in sorted(by_project.items(), key=lambda kv: -sum(s.active for _sid, s in kv[1]))[:10]:
        expander = ui.expander_row(ui.tilde(cwd) if cwd != "?" else api.tr("Unknown folder"),
                                   api.trn("1 session", "{0} sessions", len(items)).format(len(items)))
        for sid, s in sorted(items, key=lambda item: -item[1].last)[:30]:
            tokens = session_tokens(s)
            expander.add_row(ui.plain_row(titles.get(sid) or api.tr("Untitled session"),
                                          " · ".join([ui.duration_text(s.active),
                                                      api.tr("{0} tokens").format(ui.short_number(tokens))])))
        listbox.append(expander)
    box.append(listbox)
    if shutil.which("claude") is None:
        return                              # Summarize runs the user's own Claude Code
    result = ui.label("", card=True)
    result.set_visible(False)
    text = summary_text(recent, titles, since, harness.name, ui.tilde)

    def send():
        button.set_sensitive(False)
        result.set_visible(True)
        result.set_label(api.tr("Claude is writing…"))

        def finished(found):
            button.set_sensitive(True)
            result.set_label(found[1] if found else api.tr("No answer from Claude Code."))   # plain text
        ui.run_in_background(lambda: run_summary(api, text), finished)

    button = ui.button(api.tr("Summarize with Claude…"),
                       lambda: ui.confirm(api.tr("Send this to Claude Code?"),
                                          api.tr("Only these titles and numbers go to Claude, not your conversations."),
                                          text, api.tr("Send"), send),
                       api.tr("Sends the titles and numbers above (no conversations) to Claude Code and shows "
                              "what it writes. Uses some tokens."))
    box.append(button)
    box.append(result)


def register(api):
    cache = api.cache_dir() / "claude-titles.json"
    readers = {
        "claude": lambda: claude_titles(api.claude_projects, cache, api.atomic_write),
        "opencode": lambda: db_titles(api.open_readonly(OPENCODE_DB), OPENCODE_SQL),
        "hermes": lambda: db_titles(api.open_readonly(HERMES_DB), HERMES_SQL),
    }
    for command, reader in readers.items():
        api.add_session_titles(command, reader)

    def section(ui, box, harness, sessions, since):
        if harness.command not in readers:
            return
        holder = ui.box()
        box.append(holder)

        def done(titles):
            if holder.get_parent() is not None:           # the page is still open
                show(api, ui, holder, harness, sessions, titles or {}, since)
        ui.run_in_background(lambda: api.session_titles(harness.command), done)

    api.add_details_section(section, api.SUMMARY)
