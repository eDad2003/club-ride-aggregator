"""Route name extraction from ride descriptions.

Tries several heuristics in order:
  1. Explicit "Route: <name>" pattern
  2. Known route keywords (loop, out-and-back, gran fondo, etc.)
  3. RapidFuzz best match against a corpus of known route names
"""

import logging
import re

from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)

# Patterns that suggest a route name follows
_ROUTE_LABEL_RE = re.compile(
    r"(?:route|course|map|ride):\s*(.+?)(?:\.|,|\n|$)",
    re.IGNORECASE,
)

# Words that often appear in route names — used to find candidate spans
_ROUTE_KEYWORDS_RE = re.compile(
    r"\b(?:loop|lollipop|out[- ]and[- ]back|gran\s+fondo|century|brevet|populaire)\b",
    re.IGNORECASE,
)

# Minimum fuzzy score (0-100) to accept a match
FUZZY_THRESHOLD = 72


class RouteMatcher:
    """Extract a route name from free-text ride descriptions."""

    def __init__(self, known_routes: list[str] | None = None) -> None:
        # Optionally seed with a list of known route names from your club.
        # These can be loaded from the DB or a static YAML file.
        self.known_routes: list[str] = known_routes or []

    def extract_route_name(self, description: str) -> str | None:
        """Return the best-guess route name from a ride description."""
        if not description:
            return None

        # 1. Explicit label
        m = _ROUTE_LABEL_RE.search(description)
        if m:
            candidate = m.group(1).strip()
            log.debug("Label match: '%s'", candidate)
            return candidate

        # 2. Keyword anchor — grab the surrounding phrase
        m = _ROUTE_KEYWORDS_RE.search(description)
        if m:
            # Take up to 60 chars before the keyword as the route name context
            start = max(0, m.start() - 60)
            candidate = description[start : m.end()].strip()
            log.debug("Keyword match: '%s'", candidate)
            return candidate

        # 3. Fuzzy match against known route corpus
        if self.known_routes:
            result = process.extractOne(
                description,
                self.known_routes,
                scorer=fuzz.partial_ratio,
                score_cutoff=FUZZY_THRESHOLD,
            )
            if result:
                log.debug("Fuzzy match: '%s' (score=%d)", result[0], result[1])
                return result[0]

        return None

    def add_known_route(self, name: str) -> None:
        """Register a route name so it can be fuzzy-matched in future."""
        if name not in self.known_routes:
            self.known_routes.append(name)
