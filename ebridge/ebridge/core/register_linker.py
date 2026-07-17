"""
Register linker: turns register-dump log lines into clickable terminal links.

The Smatrix 5 firmware prints register values on the debug log like:

    [DEBUG] Global Bus: th_01_th_TH_ECO = 0x4848 (18504)
    [DEBUG] Local Bus:  ct_CB_CONFIG    = 0x2101 (8449)

This component detects those lines and wraps the register name in an OSC 8
terminal hyperlink that points to the SM5 register explorer web app, with the
value pre-filled, e.g.:

    http://localhost:8000/th_eco?value=4848

Ctrl+Click (VS Code integrated terminal / Windows Terminal) opens the browser on
the decoded register.

Why OSC 8 and not a plain URL
-----------------------------
OSC 8 keeps the visible text compact (only the register name shows, the long URL
stays hidden behind the link). The catch is that prompt_toolkit's ANSI() parser
strips OSC 8 sequences, so the terminal interface must print these lines with
``output.write_raw()`` (see terminal_interface._print_raw), not with the normal
print path.

Configuration (device YAML, e.g. sm5.yaml)
------------------------------------------
    register_links:
      enabled:   true
      base_url:  "http://localhost:8000"
      color:     blue          # any color name from the highlighter, or ""
      underline: true
      # Regex with named groups 'name', 'sep' and 'value'.
      pattern: '(?P<name>[A-Za-z_]\\w*)(?P<sep>\\s*=\\s*0x)(?P<value>[0-9A-Fa-f]+)'
      # Prefixes removed from the logged name to obtain the register slug.
      # The first prefix that matches the start of the name is stripped.
      strip_prefixes:
        - 'th_\\d+_th_'
        - 'th_\\d+_'
        - 'ct_'
        - 'cm_'
        - 'sys_'
"""

import re
from typing import List, Tuple

from .highlighter import ANSI_COLORS, RESET


# OSC 8 hyperlink delimiters (ST-terminated form): ESC ] 8 ;; <url> ESC \
_OSC8_OPEN = "\x1b]8;;{url}\x1b\\"
_OSC8_CLOSE = "\x1b]8;;\x1b\\"
_UNDERLINE = "\x1b[4m"

# Sensible defaults so the feature works even with a minimal YAML block.
_DEFAULT_PATTERN = r"(?P<name>[A-Za-z_]\w*)(?P<sep>\s*=\s*0x)(?P<value>[0-9A-Fa-f]+)"
_DEFAULT_PREFIXES = [r"th_\d+_th_", r"th_\d+_", r"ct_", r"cm_", r"sys_"]


class RegisterLinker:
    """Wraps register names in OSC 8 hyperlinks to the register explorer web app."""

    def __init__(self, config: dict):
        """
        Args:
            config: the 'register_links' sub-dict from the device YAML.
        """
        config = config or {}
        self.enabled: bool = config.get("enabled", False)
        self.base_url: str = config.get("base_url", "http://localhost:8000").rstrip("/")

        try:
            self._pattern = re.compile(config.get("pattern", _DEFAULT_PATTERN))
        except re.error as e:
            print(f"[LINK] Patrón regex inválido, se desactivan los enlaces: {e}")
            self.enabled = False
            self._pattern = re.compile(_DEFAULT_PATTERN)

        # Prefix strippers, anchored at the start and case-insensitive.
        self._strip: List[re.Pattern] = []
        for prefix in config.get("strip_prefixes", _DEFAULT_PREFIXES):
            try:
                self._strip.append(re.compile("^" + prefix, re.IGNORECASE))
            except re.error as e:
                print(f"[LINK] Prefijo regex inválido '{prefix}': {e}")

        # Visual style for the (clickable) register name.
        self._color = ANSI_COLORS.get(config.get("color", "blue"), "")
        self._underline = _UNDERLINE if config.get("underline", True) else ""

    def _slug(self, name: str) -> str:
        """Derive the web-app slug from a logged register name.

        Removes the first matching owner/instance prefix (e.g. 'th_01_th_') so
        that 'th_01_th_TH_ECO' becomes 'th_eco', matching the register Element
        name used by the web app.
        """
        for rx in self._strip:
            m = rx.match(name)
            if m:
                name = name[m.end():]
                break
        return name.lower()

    def linkify(self, text: str) -> Tuple[str, bool]:
        """Return (text_with_links, found).

        'found' is True when at least one register reference was linked, which
        signals the caller to print the line via the raw (OSC 8 preserving) path.
        """
        if not self.enabled:
            return text, False

        found = False

        def repl(m: re.Match) -> str:
            nonlocal found
            found = True
            name = m.group("name")
            value = m.group("value")
            url = f"{self.base_url}/{self._slug(name)}?value={value}"

            # Style the visible name, then wrap it in the OSC 8 hyperlink. The
            # "= 0x...." part (m.group('sep') + value) is kept verbatim so the
            # colour highlighter can still colourise the hex value afterwards.
            styled = f"{self._underline}{self._color}{name}{RESET}" \
                if (self._color or self._underline) else name
            linked = _OSC8_OPEN.format(url=url) + styled + _OSC8_CLOSE
            return linked + m.group("sep") + value

        return self._pattern.sub(repl, text), found
