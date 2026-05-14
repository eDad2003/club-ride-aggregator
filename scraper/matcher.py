"""Route name extraction from ride descriptions.

Tries heuristics in order:
  1. Explicit "Route: <name>" label
  2. RapidFuzz match against known route corpus (if provided)
  3. Keyword anchor (loop, century, etc.) as last resort
"""

import logging
import re

from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)

_ROUTE_LABEL_RE = re.compile(
    r"(?:route|course|map|ride):\s*(.+?)(?:\.|,|\n|$)",
    re.IGNORECASE,
)

_ROUTE_KEYWORDS_RE = re.compile(
    r"\b(?:loop|lollipop|out[- ]and[- ]back|gran\s+fondo|century|brevet|populaire)\b",
    re.IGNORECASE,
)

FUZZY_THRESHOLD = 72


class RouteMatcher:

    def __init__(self, known_routes: list[str] | None = None) -> None:
        self.known_routes: list[str] = known_routes or []

    def extract_route_name(self, description: str) -> str | None:
        if not description:
            return None

        # 1. Explicit label — highest confidence
        m = _ROUTE_LABEL_RE.search(description)
        if m:
            candidate = m.group(1).strip()
            log.debug("Label match: '%s'", candidate)
            return candidate

        # 2. Fuzzy match against known corpus — preferred over keyword anchor
        #    because it returns a clean known route name, not a raw text span
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

        # 3. Keyword anchor — fallback when no known routes corpus exists
        m = _ROUTE_KEYWORDS_RE.search(description)
        if m:
            start = max(0, m.start() - 60)
            candidate = description[start : m.end()].strip()
            log.debug("Keyword match: '%s'", candidate)
            return candidate

        return None

    def add_known_route(self, name: str) -> None:
        if name not in self.known_routes:
            self.known_routes.append(name)
