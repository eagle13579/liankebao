"""LegionEmployee — Adapter connecting 记忆宫殿 legion employees to BaseAgent system.

Each employee from the 174-person legion gets:
    1. Personality & soul from soul-injection.yaml
    2. Persistent memory from memory.db (dual-write to own DB + Gaia Brain)
    3. Agent tools (from our 9 agent classes) as capabilities
    4. Mental models from their Daoist wisdom training
    5. Learns back to Gaia Brain AND own memory

Architecture:
    LegionEmployee wraps a legion employee file with soul-injection, memory.db,
    and mental models. It is used by create_legion_agent() which pairs the
    employee with a BaseAgent subclass, giving the agent the employee's
    personality, memory, and identity while keeping the agent's tools and lifecycle.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── Legion root path ───────────────────────────────────────────────

LEGION_PATH = "D:/向海容的知识库/wiki/wiki/记忆宫殿/employees"


# ── Safe YAML loader (handles custom !tag types gracefully) ────────


class _SafeLoader(yaml.SafeLoader):
    """Extended SafeLoader that preserves unknown YAML tags as strings."""


def _tag_constructor(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> Any:
    """Handle unknown YAML tags (!tag) by returning raw scalar or dict."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


# Register a catch-all handler for any unknown tag
_SafeLoader.add_multi_constructor("tag:yaml.org,2002:", _tag_constructor)
# Also handle bare !tags (no URI prefix) by patching construct_object
original_construct_object = _SafeLoader.construct_object


def _safe_construct_object(loader, node, **kwargs):
    """Patch construct_object to handle unknown tags gracefully."""
    try:
        return original_construct_object(loader, node, **kwargs)
    except (yaml.constructor.ConstructorError, TypeError):
        if isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        return None


_SafeLoader.construct_object = _safe_construct_object


def _fix_yaml_text(text: str) -> str:
    """Fix malformed YAML patterns found in legion soul-injection files.

    The soul-injection.yaml files have a recurring pattern where quoted
    strings are concatenated without YAML-legal separators:
        "coordinator"xecutor"uilder
        "forecaster"rchitect"uilder
        "领航者"nnovator"nnovator

    These are fixed by inserting hyphens between the fragments.
    """

    # Pattern: "word1"word2"word3" (quoted fragments with text between)
    # Replace the space between closing " and the next word with a hyphen + space
    # Only within YAML values (not keys or structure)
    def fix_malformed_quotes(match):
        inner = match.group(1)
        # inner is like: coordinator"xecutor"uilder
        # Replace inner quotes with hyphens
        fixed = re.sub(r'"([^"]*)"', r"-\1-", inner)
        # Remove leading/trailing hyphens (the original outer quotes handle them)
        if fixed.startswith("-") and fixed.endswith("-"):
            fixed = fixed[1:-1]
        elif fixed.startswith("-"):
            fixed = fixed[1:]
        elif fixed.endswith("-"):
            fixed = fixed[:-1]
        return f'"{fixed}"'

    # Find patterns where a quoted value has embedded quotes within the value
    # Pattern: starts with ", has some text, then "word" inside, then maybe more
    text = re.sub(
        r'"([^"]*"[^"]*"[^"]*)"',
        fix_malformed_quotes,
        text,
    )
    return text


def _safe_load_yaml(path: str) -> dict[str, Any]:
    """Load a YAML file, returning {} on parse error or missing file.

    Handles the legion's custom YAML tags (!tag) gracefully by
    falling back to plain string/dict parsing when the tag is unknown.
    Also handles malformed YAML (like concatenated quoted strings)
    by falling back to manual key-value extraction.
    """
    if not os.path.exists(path):
        logger.debug("YAML file not found: %s", path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw_text = f.read()
        data = yaml.load(raw_text, Loader=_SafeLoader)
        if data is None:
            return {}
        if not isinstance(data, dict):
            logger.warning("YAML root is not a dict in %s: got %s", path, type(data).__name__)
            return data if isinstance(data, dict) else {}
        return data
    except Exception as exc:
        logger.debug("YAML parse failed for %s, trying fallback parser: %s", path, exc)
        # raw_text may not be defined if open() failed
        if "raw_text" in dir():
            return _fallback_yaml_parse(path, raw_text)
        return {}


def _fallback_yaml_parse(path: str, raw_text: str) -> dict[str, Any]:
    """Fallback parser for YAML-like files with syntax errors.

    Does a line-by-line extraction of top-level keys and nested structures.
    Handles:
    - Top-level key: value pairs
    - Simple list items (- value)
    - Dict list items (- key: value)
    - Nested indented dicts
    - Multiline quoted values
    """
    result: dict[str, Any] = {}

    # State machine
    current_top_key: str | None = None  # Current top-level key
    current_list: list[Any] | None = None  # Building a list under current_key
    current_nested: dict[str, Any] | None = None  # Building a nested dict

    in_multiline = False
    multiline_buffer: list[str] = []
    multiline_key: str | None = None

    lines = raw_text.split("\n")

    def _flush():
        """Flush any pending nested/list state into result."""
        nonlocal current_list, current_nested, current_top_key
        if current_list is not None and current_top_key:
            result[current_top_key] = current_list
            current_list = None
            current_nested = None  # Cleared: list takes priority
        if current_nested is not None and current_top_key:
            result[current_top_key] = current_nested
            current_nested = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip pure comments and blank lines
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue

        # Check indentation level
        indent = len(line) - len(line.lstrip())
        is_top_level = indent == 0

        # Handle multiline continuation (indented text after |)
        if in_multiline and is_top_level:
            in_multiline = False
            if multiline_key:
                result[multiline_key] = "\n".join(multiline_buffer)
            multiline_buffer = []
            multiline_key = None

        if in_multiline:
            multiline_buffer.append(stripped)
            continue

        # ── Top-level key: value ──────────────────────────────────
        if is_top_level and ":" in stripped:
            # Parse top-level key: value
            colon_pos = stripped.index(":")
            key = stripped[:colon_pos].strip()
            value = stripped[colon_pos + 1 :].strip()

            # Flush any pending state
            _flush()
            current_top_key = key

            # Check for multiline value (| or >)
            if value in ("|", ">"):
                in_multiline = True
                multiline_key = key
                multiline_buffer = []
                continue

            # Handle empty value (start of nested block)
            if value == "":
                # Will be filled by nested keys on next lines
                current_nested = {}
                continue

            # Parse the value
            parsed = _parse_yaml_value(value)
            if parsed is not None:
                result[key] = parsed
            else:
                result[key] = value

        # ── List items ────────────────────────────────────────────
        elif stripped.startswith("- ") and current_top_key:
            item_text = stripped[2:].strip()

            # Check if this is a dict-style list item: - key: value
            if ":" in item_text and not item_text.startswith('"'):
                # Could be a dict item in the list
                colon_pos = item_text.index(":")
                item_key = item_text[:colon_pos].strip()
                item_value = item_text[colon_pos + 1 :].strip()

                parsed_val = _parse_yaml_value(item_value)
                item_dict = {item_key: parsed_val if parsed_val is not None else item_value}

                # Initialize list if needed
                if current_list is None:
                    current_list = []
                current_list.append(item_dict)
            else:
                # Simple string list item
                parsed_val = _parse_yaml_value(item_text)
                text = parsed_val if parsed_val is not None else item_text
                if current_list is None:
                    current_list = []
                current_list.append(text)

        # ── Nested dict keys under a parent ───────────────────────
        elif indent > 0 and ":" in stripped and current_top_key:
            colon_pos = stripped.index(":")
            sub_key = stripped[:colon_pos].strip()
            sub_value = stripped[colon_pos + 1 :].strip()

            # Skip if it looks like a comment inside a value
            if sub_key.startswith("#"):
                continue

            # Parse value
            parsed = _parse_yaml_value(sub_value)

            # Determine parent: if we're in a list, the last item might be a dict
            if current_list and current_list and isinstance(current_list[-1], dict):
                current_list[-1][sub_key] = parsed if parsed is not None else sub_value
            elif current_nested is not None:
                current_nested[sub_key] = parsed if parsed is not None else sub_value
            else:
                # Top-level nested dict
                if current_top_key not in result:
                    result[current_top_key] = {}
                if isinstance(result[current_top_key], dict):
                    result[current_top_key][sub_key] = parsed if parsed is not None else sub_value

    # Final flush
    _flush()
    if in_multiline and multiline_key:
        result[multiline_key] = "\n".join(multiline_buffer)

    return result


def _parse_yaml_value(value: str) -> Any:
    """Parse a YAML-like value string into its Python type.

    Handles:
    - Quoted strings: "hello" -> 'hello'
    - Booleans: true/false -> True/False
    - Numbers: 42 -> 42, 3.14 -> 3.14
    - None: null/None/~ -> None
    """
    if not value:
        return ""

    if value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        # Remove any stray quotes from malformed values like "coordinator"xecutor"uilder
        inner = inner.replace('"', "-")
        return inner

    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]

    if value.lower() in ("true", "yes", "on"):
        return True
    if value.lower() in ("false", "no", "off"):
        return False
    if value.lower() in ("null", "none", "~"):
        return None

    # Try numeric
    try:
        if "." in value:
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        pass

    return value


# ── Employee directory resolution ──────────────────────────────────


def _resolve_employee_dir(employee_id: str) -> str:
    """Resolve an employee_id to the actual filesystem directory.

    Employee directories follow the pattern:
        emp-{name}          (e.g., emp-烛龙)
        emp-{name}-{suffix} (e.g., emp-白泽-3c6ee223)

    We match by prefix: find the directory that starts with 'emp-{name}'.
    If multiple match (e.g., variants), return the shortest match (the base).

    Args:
        employee_id: Canonical ID like 'emp-烛龙' or 'emp-白泽'.

    Returns:
        Absolute path to the employee directory, or empty string if not found.
    """
    # Extract the name part from employee_id (everything after 'emp-')
    prefix = employee_id  # e.g., "emp-烛龙"

    # Normalize path separators
    legion = LEGION_PATH.replace("\\", "/")
    if not os.path.isdir(legion):
        logger.error("Legion path does not exist: %s", legion)
        return ""

    try:
        entries = os.listdir(legion)
    except PermissionError:
        logger.error("Permission denied reading legion path: %s", legion)
        return ""

    candidates = []
    for entry in entries:
        full = os.path.join(legion, entry)
        if os.path.isdir(full) and entry.startswith(prefix):
            candidates.append(entry)

    if not candidates:
        logger.warning("No employee directory found for '%s' under %s", employee_id, legion)
        return ""

    # Shortest name = base employee (no suffix)
    candidates.sort(key=len)
    best = candidates[0]
    resolved = os.path.join(legion, best)
    logger.debug("Resolved %s → %s", employee_id, resolved)
    return resolved.replace("\\", "/")


# ── Memory DB schema helpers ──────────────────────────────────────


MEMORY_TABLES = {
    "memories": {
        "content_col": "content",
        "created_col": "created_at",
    },
    "memory_entries": {
        "content_col": "value",
        "created_col": "created_at",
    },
}


async def _query_memory_db(db_path: str, key: str, limit: int = 5) -> list[dict[str, Any]]:
    """Query a legion employee's memory.db for entries matching key.

    Handles multiple possible table schemas present in different
    employees' databases. Uses LIKE matching on content columns.
    """
    import aiosqlite

    if not db_path or not os.path.exists(db_path):
        return []

    results: list[dict[str, Any]] = []
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # Discover available tables
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in await cursor.fetchall()}

            for table_name, schema in MEMORY_TABLES.items():
                if table_name not in existing_tables:
                    continue
                content_col = schema["content_col"]
                created_col = schema["created_col"]
                try:
                    cursor = await db.execute(
                        f"SELECT {content_col} AS content, {created_col} AS created_at "
                        f'FROM "{table_name}" WHERE {content_col} LIKE ? '
                        f"ORDER BY {created_col} DESC LIMIT ?",
                        (f"%{key}%", limit),
                    )
                    rows = await cursor.fetchall()
                    for row in rows:
                        results.append(
                            {
                                "content": row["content"],
                                "created_at": row["created_at"],
                                "table": table_name,
                            }
                        )
                except Exception:
                    logger.debug(
                        "Table %s in %s not queryable with expected schema",
                        table_name,
                        db_path,
                    )
    except Exception as exc:
        logger.warning("Failed to query memory db %s: %s", db_path, exc)

    return results[:limit]


async def _write_memory_db(db_path: str, content: str, category: str = "experience") -> bool:
    """Write a memory entry to a legion employee's memory.db.

    Tries to write to both 'memories' and 'memory_entries' tables.
    Creates the entry in whichever table is available.
    """
    import aiosqlite

    if not db_path or not os.path.exists(db_path):
        return False

    now = time.time()
    try:
        async with aiosqlite.connect(db_path) as db:
            # Discover available tables
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in await cursor.fetchall()}

            wrote = False
            if "memories" in existing_tables:
                try:
                    # Try with 'content' column
                    await db.execute(
                        "INSERT INTO memories (content, category, created_at) VALUES (?, ?, ?)",
                        (content, category, now),
                    )
                    await db.commit()
                    wrote = True
                except Exception:
                    # Try alternate schema: memories(content, memory_type, created_at, ...)
                    try:
                        await db.execute(
                            "INSERT INTO memories (content, memory_type, created_at) VALUES (?, ?, ?)",
                            (content, category, now),
                        )
                        await db.commit()
                        wrote = True
                    except Exception:
                        pass

            if "memory_entries" in existing_tables and not wrote:
                try:
                    await db.execute(
                        "INSERT INTO memory_entries (category, key, value, created_at) VALUES (?, ?, ?, ?)",
                        (category, f"agent_{int(now)}", content, now),
                    )
                    await db.commit()
                    wrote = True
                except Exception:
                    pass

            return wrote
    except Exception as exc:
        logger.warning("Failed to write to memory db %s: %s", db_path, exc)
        return False


# ── LegionEmployee class ──────────────────────────────────────────


class LegionEmployee:
    """Wraps a 记忆宫殿 legion employee with agent capabilities.

    An employee from the 174-person legion gets:
    1. Personality & soul from soul-injection.yaml
    2. Persistent memory from memory.db
    3. Agent tools (from our 9 agent classes) as capabilities
    4. Mental models from their Daoist wisdom training
    5. Learns back to Gaia Brain AND own memory
    """

    def __init__(
        self,
        employee_id: str,
        agent_tools: dict[str, Any] | None = None,
        brain: Any | None = None,
    ) -> None:
        # Resolve directory
        self.employee_id = employee_id
        self.emp_dir = _resolve_employee_dir(employee_id)
        if not self.emp_dir:
            logger.warning(
                "Employee '%s' not found in legion. Running as generic employee.",
                employee_id,
            )

        # Load configuration files
        self.config: dict[str, Any] = {}
        self.soul: dict[str, Any] = {}
        if self.emp_dir:
            self.config = self._load_yaml("employee.yaml")
            self.soul = self._load_yaml("soul-injection.yaml")
        else:
            # Fallback: minimal generic employee
            self.soul = {
                "label": employee_id,
                "personality": {"style": "generic", "traits": []},
                "mental_models": [],
                "capabilities": [],
                "identity": {},
            }

        # Memory DB path
        self.memory_db_path: str | None = self._find_memory_db()

        # Properties from soul
        self.name: str = self.soul.get("label") or self.soul.get("name") or employee_id
        raw_personality = self.soul.get("personality", {})
        # Normalize personality to dict (YAML quirks may return list)
        if isinstance(raw_personality, list):
            raw_personality = {"style": "generic", "traits": [str(x) for x in raw_personality if isinstance(x, str)]}
        self.personality: dict[str, Any] = raw_personality
        self.mental_models: list[Any] = self._collect_mental_models()
        self.capabilities: list[str] = self._collect_capabilities()
        self.identity: dict[str, Any] = self.soul.get("identity", {})

        # Attached agent tools
        self.tools: dict[str, Any] = agent_tools or {}

        # Gaia Brain reference (optional)
        self._brain: Any | None = brain

        logger.info(
            "LegionEmployee '%s' (%s) initialized | memory=%s | tools=%d | models=%d",
            self.name,
            self.employee_id,
            "yes" if self.memory_db_path else "no",
            len(self.tools),
            len(self.mental_models),
        )

    # ── File loading ─────────────────────────────────────────────

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """Load a YAML file from the employee directory."""
        if not self.emp_dir:
            return {}
        path = f"{self.emp_dir}/{filename}"
        return _safe_load_yaml(path)

    def _find_memory_db(self) -> str | None:
        """Find the memory.db path for this employee."""
        if not self.emp_dir:
            return None
        memory_dir = f"{self.emp_dir}/memory/"
        db_path = f"{memory_dir}/memory.db"
        if os.path.exists(db_path):
            return db_path
        return None

    def _collect_mental_models(self) -> list[Any]:
        """Collect mental models from soul, handling mixed formats.

        The existing soul-injection.yaml has mental_models in multiple formats:
        - Simple strings: ['烹小鲜', '奇正相生']
        - Dicts with keys: [{'name': '...', 'content': '...'}, ...]
        - Dicts with employee_id/memory_type: [{'employee_id': '...', 'content': '...'}, ...]
        """
        raw = self.soul.get("mental_models", [])
        if not isinstance(raw, list):
            return []

        collected = []
        for item in raw:
            if isinstance(item, str):
                collected.append({"name": item, "content": item})
            elif isinstance(item, dict):
                name = item.get("name") or item.get("content", "")[:50] or item.get("memory_type", "") or str(item)
                content = item.get("content", "")
                collected.append(
                    {
                        "name": name,
                        "content": content,
                        "source": item.get("source", ""),
                        "application": item.get("application", ""),
                        "tags": item.get("tags", []),
                    }
                )
        return collected

    def _collect_capabilities(self) -> list[str]:
        """Collect capabilities from both employee.yaml and soul-injection.yaml."""
        caps: list[str] = []
        for source in (self.config, self.soul):
            raw = source.get("capabilities", [])
            if isinstance(raw, list):
                for c in raw:
                    if isinstance(c, str) and c not in caps:
                        caps.append(c)
        return caps

    # ── Properties ───────────────────────────────────────────────

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return f"{self.name} ({self.employee_id})"

    @property
    def personality_traits(self) -> list[str]:
        """List of personality traits from soul-injection."""
        return self.personality.get("traits", [])

    @property
    def personality_style(self) -> str:
        """Personality style string from soul-injection."""
        return self.personality.get("style", "")

    @property
    def level(self) -> str:
        """Employee level (P6, P8, P9, etc.)."""
        return self.soul.get("level") or self.config.get("level", "")

    @property
    def worldview(self) -> str:
        """Worldview from soul-injection, if present."""
        return self.soul.get("worldview", "")

    @property
    def introduction(self) -> str:
        """Introduction/biography from soul-injection, if present."""
        return self.soul.get("introduction", "")

    # ── Memory operations ────────────────────────────────────────

    async def remember(self, key: str, limit: int = 5) -> list[dict[str, Any]]:
        """Query employee's own memory.db for relevant memories.

        This gives the employee persistent memory across sessions.
        Searches memory.db for entries matching the key across
        multiple possible table schemas.

        Args:
            key: Search term to match against memory content.
            limit: Maximum number of results to return.

        Returns:
            List of dicts with 'content' and 'created_at' keys.
        """
        return await _query_memory_db(self.memory_db_path or "", key, limit)

    async def memorize(self, content: str, category: str = "experience") -> None:
        """Store a memory in the employee's own memory.db AND feed to Gaia Brain.

        Dual-writes to:
        1. Employee's own memory.db (persistent across sessions)
        2. Gaia Evolution Brain (shared across all employees, if available)

        Args:
            content: The memory content to store.
            category: Category/type of memory (e.g., 'experience', 'insight').
        """
        now = time.time()

        # 1. Own memory.db
        await _write_memory_db(self.memory_db_path or "", content, category)

        # 2. Gaia Brain (if available)
        if self._brain is not None and hasattr(self._brain, "ingest_knowledge"):
            try:
                await self._brain.ingest_knowledge(
                    source=f"employee:{self.employee_id}",
                    source_id=f"mem_{int(now)}",
                    knowledge_type=category,
                    title=f"{self.name} remembered: {content[:50]}",
                    content=content,
                    tags=[category, self.employee_id],
                )
            except Exception:
                logger.debug(
                    "Failed to feed memory to Gaia Brain for %s",
                    self.employee_id,
                )

    async def learn(self, observation: str, metadata: dict[str, Any] | None = None) -> None:
        """Feed observation to both own memory and Gaia Brain.

        This is the standard learn() interface used by BaseAgent.
        It bridges the gap between the agent's learn() and the
        employee's memorize().

        Args:
            observation: The observation/experience to learn from.
            metadata: Optional metadata (uses 'type' as category if present).
        """
        category = "experience"
        if metadata and isinstance(metadata, dict):
            category = metadata.get("type", "experience")
        await self.memorize(observation, category=category)

    async def get_stats(self) -> dict[str, Any]:
        """Get employee statistics summary.

        Returns:
            Dict with key employee metadata and state.
        """
        return {
            "employee_id": self.employee_id,
            "name": self.name,
            "level": self.level,
            "personality_style": self.personality_style,
            "traits": self.personality_traits[:5],
            "mental_models": [
                m.get("name", str(m))[:60] if isinstance(m, dict) else str(m)[:60] for m in self.mental_models[:5]
            ],
            "capabilities": self.capabilities[:5],
            "tools": list(self.tools.keys()),
            "has_memory": self.memory_db_path is not None,
            "emp_dir": self.emp_dir,
        }

    def __repr__(self) -> str:
        return f"<LegionEmployee '{self.name}' ({self.employee_id})>"
