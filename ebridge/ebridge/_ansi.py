"""
Utilidad de impresión con colores ANSI compatible con Windows Terminal.

Problema:
    En Windows, print() escribe bytes crudos en stdout. Dentro del contexto
    patch_stdout de prompt_toolkit (o simplemente en consolas AzureAD con
    políticas restrictivas), los códigos \033[Xm se muestran literalmente
    en lugar de aplicar el color.

Solución:
    print_formatted_text(ANSI(texto)) delega en el sistema de output de
    prompt_toolkit, que en Windows usa la Win32 Console API o el modo VT
    según lo que soporte la consola, garantizando que los colores se rendericen
    correctamente en cualquier plataforma.

Uso:
    from ebridge._ansi import cprint

    cprint(f"\033[92m[OK]\033[0m Mensaje verde")
    cprint(f"\033[91m[ERROR]\033[0m Algo ha fallado")
"""

from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text


def cprint(text: str, end: str = "\n") -> None:
    """
    Imprime texto con códigos ANSI de forma compatible con Windows Terminal.

    Es un reemplazo directo de print() para mensajes que contengan colores.
    Para mensajes sin color, print() normal sigue siendo válido.

    Args:
        text: Texto con códigos ANSI opcionales (\\033[Xm o \\x1b[Xm).
        end:  Carácter final, igual que en print() (default: salto de línea).
    """
    print_formatted_text(ANSI(text), end=end)