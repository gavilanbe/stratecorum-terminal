from __future__ import annotations

import os
import re
import select
import shutil
import sys
import termios
import tty
from contextlib import AbstractContextManager


CSI = "\x1b["
RESET = f"{CSI}0m"
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


PALETTE = {
    "white": (236, 241, 247),
    "muted": (104, 116, 137),
    "dim": (75, 85, 105),
    "black": (3, 7, 18),
    "panel": (9, 15, 28),
    "panel2": (15, 23, 42),
    "amber": (245, 158, 11),
    "amber2": (251, 191, 36),
    "rose": (244, 63, 94),
    "rose2": (251, 113, 133),
    "emerald": (16, 185, 129),
    "emerald2": (52, 211, 153),
    "blue": (96, 165, 250),
    "purple": (168, 85, 247),
    "orange": (249, 115, 22),
    "slate": (148, 163, 184),
}


def rgb(value: str | tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(value, tuple):
        return value
    return PALETTE[value]


def fg(value: str | tuple[int, int, int]) -> str:
    r, g, b = rgb(value)
    return f"{CSI}38;2;{r};{g};{b}m"


def bg(value: str | tuple[int, int, int]) -> str:
    r, g, b = rgb(value)
    return f"{CSI}48;2;{r};{g};{b}m"


def style(
    text: str,
    *,
    color: str | tuple[int, int, int] | None = None,
    background: str | tuple[int, int, int] | None = None,
    bold: bool = False,
    dim: bool = False,
    italic: bool = False,
) -> str:
    codes = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if italic:
        codes.append("3")
    prefix = f"{CSI}{';'.join(codes)}m" if codes else ""
    if color:
        prefix += fg(color)
    if background:
        prefix += bg(background)
    return f"{prefix}{text}{RESET}" if prefix else text


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def width(text: str) -> int:
    return len(strip_ansi(text))


def pad(text: str, target: int) -> str:
    return text + " " * max(0, target - width(text))


def center(text: str, target: int) -> str:
    left = max(0, (target - width(text)) // 2)
    right = max(0, target - width(text) - left)
    return " " * left + text + " " * right


def crop(text: str, target: int) -> str:
    if width(text) <= target:
        return text
    plain = strip_ansi(text)
    return plain[: max(0, target - 1)] + "…"


def gradient_text(text: str, colors: list[tuple[int, int, int]], *, bold: bool = False) -> str:
    if not text:
        return text
    out = []
    steps = max(1, len(text) - 1)
    for i, ch in enumerate(text):
        pos = i / steps
        scaled = pos * (len(colors) - 1)
        left = int(scaled)
        right = min(len(colors) - 1, left + 1)
        mix = scaled - left
        c1, c2 = colors[left], colors[right]
        color = tuple(round(c1[j] + (c2[j] - c1[j]) * mix) for j in range(3))
        out.append(style(ch, color=color, bold=bold))
    return "".join(out)


def box_lines(
    lines: list[str],
    *,
    inner_width: int,
    title: str = "",
    color: str | tuple[int, int, int] = "slate",
    dim_border: bool = False,
) -> list[str]:
    border_color = rgb(color)
    border = lambda s: style(s, color=border_color, dim=dim_border)
    title_plain = f" {title} " if title else ""
    if title_plain:
        title_width = len(title_plain)
        left = max(1, (inner_width - title_width) // 2)
        right = max(0, inner_width - title_width - left)
        top = border("╭" + "─" * left) + style(title_plain, color=color, bold=True) + border("─" * right + "╮")
    else:
        top = border("╭" + "─" * inner_width + "╮")
    bottom = border("╰" + "─" * inner_width + "╯")
    body = [border("│") + pad(crop(line, inner_width), inner_width) + border("│") for line in lines]
    return [top, *body, bottom]


class Terminal(AbstractContextManager):
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = None

    def __enter__(self) -> "Terminal":
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        sys.stdout.write(f"{CSI}?1049h{CSI}?25l{CSI}2J{CSI}H")
        sys.stdout.flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.old_settings:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
        sys.stdout.write(f"{RESET}{CSI}?25h{CSI}?1049l")
        sys.stdout.flush()

    def size(self) -> tuple[int, int]:
        s = shutil.get_terminal_size((120, 40))
        return s.columns, s.lines

    def draw(self, lines: list[str]) -> None:
        cols, rows = self.size()
        clipped = lines[:rows]
        out = [f"{CSI}H"]
        for i in range(rows):
            line = clipped[i] if i < len(clipped) else ""
            out.append(pad(crop(line, cols), cols))
            if i != rows - 1:
                out.append("\n")
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def read_key(self, timeout: float = 0.05) -> str | None:
        readable, _, _ = select.select([sys.stdin], [], [], timeout)
        if not readable:
            return None
        data = os.read(self.fd, 16)
        if not data:
            return None
        if data in (b"\x03", b"\x04"):
            return "q"
        if data in (b"\r", b"\n"):
            return "ENTER"
        if data == b" ":
            return "SPACE"
        if data.startswith(b"\x1b"):
            if data in (b"\x1b[D", b"\x1bOD"):
                return "LEFT"
            if data in (b"\x1b[C", b"\x1bOC"):
                return "RIGHT"
            if data in (b"\x1b[A", b"\x1bOA"):
                return "UP"
            if data in (b"\x1b[B", b"\x1bOB"):
                return "DOWN"
            return "ESC"
        try:
            return data.decode("utf-8", "ignore").lower()
        except UnicodeDecodeError:
            return None
