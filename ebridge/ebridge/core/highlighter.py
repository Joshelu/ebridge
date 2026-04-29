"""
Resaltador de texto mediante expresiones regulares.

La configuración de colores viene del archivo YAML del dispositivo:

  highlights:
    - pattern: "\\bOK\\b"
      color: green
    - pattern: "\\bERROR\\b"
      color: red
"""

import re
from typing import List, Dict, Tuple


# Códigos ANSI de color disponibles en la configuración
ANSI_COLORS: Dict[str, str] = {
    "red":        "\033[91m",
    "green":      "\033[92m",
    "yellow":     "\033[93m",
    "blue":       "\033[94m",
    "magenta":    "\033[95m",
    "cyan":       "\033[96m",
    "white":      "\033[97m",
    "orange":     "\033[33m",
    "bold_red":   "\033[1;91m",
    "bold_green": "\033[1;92m",
    "bold":       "\033[1m",
    "dim":        "\033[2m",
    "reset":      "\033[0m",
}

RESET = ANSI_COLORS["reset"]


class Highlighter:
    """
    Aplica colores ANSI a fragmentos de texto que coincidan con patrones regex.

    Ejemplo de uso:
        h = Highlighter([{"pattern": "ERROR", "color": "red"}])
        print(h.highlight("respuesta: ERROR al ejecutar"))
    """

    def __init__(self, highlight_rules: List[Dict]):
        """
        Args:
            highlight_rules: lista de dicts con claves 'pattern' y 'color'.
        """
        self._rules: List[Tuple[re.Pattern, str]] = []
        for rule in highlight_rules:
            try:
                pattern = re.compile(rule["pattern"])
                color_code = ANSI_COLORS.get(rule.get("color", "white"), ANSI_COLORS["white"])
                self._rules.append((pattern, color_code))
            except re.error as e:
                print(f"[HIGHLIGHT] Patrón regex inválido '{rule.get('pattern')}': {e}")

    def highlight(self, text: str) -> str:
        """Devuelve el texto con códigos ANSI insertados en las coincidencias."""
        for pattern, color in self._rules:
            text = pattern.sub(lambda m: f"{color}{m.group()}{RESET}", text)
        return text

    def strip(self, text: str) -> str:
        """Elimina todos los códigos ANSI de un texto (para el log en fichero)."""
        return re.sub(r"\033\[[0-9;]*m", "", text)
