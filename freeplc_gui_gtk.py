#!/usr/bin/env python3
"""
FreePLC GTK-Style GUI — Programmable Relay Simulator
A Python/tkinter GUI styled after GTK/GNOME with a visual Ladder Diagram (LD) canvas.

Ladder Diagram rendering uses standard PLC notation:
  - Normally-Open Contact (NO):  --| |--   (reads an input)
  - Normally-Closed Contact (NC): --|/|--  (negated input)
  - Output Coil:                  --( )--  (writes an output)
  - Set Coil (S):                 --(S)--  (RS trigger set)
  - Reset Coil (R):               --(R)--  (RS trigger reset)
  - Each rung is a horizontal rail between left and right power rails.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
from typing import Dict, List, Optional, Any, Tuple


# ============================================================
# GTK-like colour palette (Adwaita/GNOME inspired)
# ============================================================
class Theme:
    BG             = "#f6f5f4"   # Window background (Adwaita light)
    SIDEBAR_BG     = "#e0dfe0"   # Sidebar / panel background
    HEADERBAR_BG   = "#3d3d3d"   # Header bar (dark)
    HEADERBAR_FG   = "#ffffff"
    ACCENT         = "#1c71d8"   # GTK4 blue accent
    ACCENT_HOVER   = "#1a64c4"
    ACCENT_FG      = "#ffffff"
    SUCCESS        = "#26a269"   # Green (running)
    DANGER         = "#e01b24"   # Red (stopped / error)
    WARNING        = "#c58f08"   # Amber
    BORDER         = "#c0bfbe"
    TEXT           = "#1a1a1a"
    SUBTEXT        = "#5e5c64"
    CANVAS_BG      = "#ffffff"
    RUNG_RAIL      = "#2d2d2d"
    CONTACT_FILL   = "#d0e4ff"
    CONTACT_ACTIVE = "#1c71d8"
    COIL_FILL      = "#ffd0d0"
    COIL_ACTIVE    = "#e01b24"
    COIL_SET_FILL  = "#d0ffd0"
    COIL_SET_ACTIVE= "#26a269"
    SELECTED_BG    = "#c6e2ff"
    HOVERED_BG     = "#e8f0fb"


# ============================================================
# Core PLC logic (Python port of C++ logic classes)
# ============================================================

class PlcIO:
    """Represents a PLC's I/O channels."""

    def __init__(self, name: str, num_inputs: int, num_outputs: int):
        self.name = name
        self.inputs: Dict[int, bool] = {i: False for i in range(1, num_inputs + 1)}
        self.outputs: Dict[int, bool] = {i: False for i in range(1, num_outputs + 1)}

    def set_input(self, channel: int, value: bool) -> None:
        if channel in self.inputs:
            self.inputs[channel] = value

    def get_input(self, channel: int) -> bool:
        return self.inputs.get(channel, False)

    def set_output(self, channel: int, value: bool) -> None:
        if channel in self.outputs:
            self.outputs[channel] = value

    def get_output(self, channel: int) -> bool:
        return self.outputs.get(channel, False)


class LogicElement:
    """Abstract base class for LD logic elements."""

    def evaluate(self, io: PlcIO) -> bool:
        raise NotImplementedError

    def __str__(self) -> str:
        raise NotImplementedError

    def ld_label(self) -> str:
        """Short label for LD canvas display."""
        raise NotImplementedError

    def ld_type(self) -> str:
        """One of: 'NO', 'NC', 'COIL', 'SET_COIL', 'RST_COIL', 'AND', 'OR', 'RS'."""
        raise NotImplementedError

    def rung_elements(self) -> List[Dict]:
        """
        Return a list of dicts describing how to render this element as rung cells.
        Each dict has: type (NO/NC/COIL/SET_COIL/RST_COIL), label (str)
        AND and OR gates are rendered as two contacts + one coil on a rung.
        RS trigger is rendered as two contacts (S/R) + one coil.
        """
        raise NotImplementedError


class AndGate(LogicElement):
    def __init__(self, in1: int, in2: int, out: int):
        self.input1 = in1
        self.input2 = in2
        self.output = out

    def evaluate(self, io: PlcIO) -> bool:
        result = io.get_input(self.input1) and io.get_input(self.input2)
        io.set_output(self.output, result)
        return result

    def __str__(self) -> str:
        return f"AND  I{self.input1} & I{self.input2} → Q{self.output}"

    def ld_label(self) -> str:
        return f"AND I{self.input1}&I{self.input2}→Q{self.output}"

    def ld_type(self) -> str:
        return "AND"

    def rung_elements(self) -> List[Dict]:
        return [
            {"type": "NO",   "label": f"I{self.input1}", "ch": self.input1, "kind": "input"},
            {"type": "NO",   "label": f"I{self.input2}", "ch": self.input2, "kind": "input"},
            {"type": "COIL", "label": f"Q{self.output}", "ch": self.output, "kind": "output"},
        ]


class OrGate(LogicElement):
    def __init__(self, in1: int, in2: int, out: int):
        self.input1 = in1
        self.input2 = in2
        self.output = out

    def evaluate(self, io: PlcIO) -> bool:
        result = io.get_input(self.input1) or io.get_input(self.input2)
        io.set_output(self.output, result)
        return result

    def __str__(self) -> str:
        return f"OR   I{self.input1} | I{self.input2} → Q{self.output}"

    def ld_label(self) -> str:
        return f"OR I{self.input1}|I{self.input2}→Q{self.output}"

    def ld_type(self) -> str:
        return "OR"

    def rung_elements(self) -> List[Dict]:
        return [
            {"type": "NO",   "label": f"I{self.input1}", "ch": self.input1, "kind": "input"},
            {"type": "OR_JOIN", "label": f"I{self.input2}", "ch": self.input2, "kind": "input"},
            {"type": "COIL", "label": f"Q{self.output}", "ch": self.output, "kind": "output"},
        ]


class NotGate(LogicElement):
    def __init__(self, in_ch: int, out: int):
        self.input = in_ch
        self.output = out

    def evaluate(self, io: PlcIO) -> bool:
        result = not io.get_input(self.input)
        io.set_output(self.output, result)
        return result

    def __str__(self) -> str:
        return f"NOT  I{self.input} → Q{self.output}"

    def ld_label(self) -> str:
        return f"NOT I{self.input}→Q{self.output}"

    def ld_type(self) -> str:
        return "NOT"

    def rung_elements(self) -> List[Dict]:
        return [
            {"type": "NC",   "label": f"I{self.input}", "ch": self.input, "kind": "input"},
            {"type": "COIL", "label": f"Q{self.output}", "ch": self.output, "kind": "output"},
        ]


class RSTrigger(LogicElement):
    def __init__(self, set_ch: int, reset_ch: int, out: int):
        self.set_input = set_ch
        self.reset_input = reset_ch
        self.output = out
        self._state = False

    def evaluate(self, io: PlcIO) -> bool:
        s = io.get_input(self.set_input)
        r = io.get_input(self.reset_input)
        if r:
            self._state = False
        elif s:
            self._state = True
        io.set_output(self.output, self._state)
        return self._state

    def __str__(self) -> str:
        return f"RS   I{self.set_input}(S) / I{self.reset_input}(R) → Q{self.output}"

    def ld_label(self) -> str:
        return f"RS I{self.set_input}(S)/I{self.reset_input}(R)→Q{self.output}"

    def ld_type(self) -> str:
        return "RS"

    def rung_elements(self) -> List[Dict]:
        return [
            {"type": "NO",       "label": f"I{self.set_input}",   "ch": self.set_input,   "kind": "input"},
            {"type": "NO",       "label": f"I{self.reset_input}",  "ch": self.reset_input, "kind": "input"},
            {"type": "SET_COIL", "label": f"Q{self.output}(S)",    "ch": self.output,      "kind": "output"},
        ]


class LDProgram:
    """Container for logic elements with run/stop support."""

    def __init__(self, io: PlcIO, name: str):
        self.io = io
        self.name = name
        self.elements: List[LogicElement] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def add_element(self, element: LogicElement) -> None:
        with self._lock:
            self.elements.append(element)

    def remove_element(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self.elements):
                self.elements.pop(index)

    def clear_elements(self) -> None:
        with self._lock:
            self.elements.clear()

    def get_elements(self) -> List[LogicElement]:
        with self._lock:
            return list(self.elements)

    def execute(self) -> None:
        with self._lock:
            for element in self.elements:
                element.evaluate(self.io)

    def run(self) -> None:
        self._running = True
        while self._running:
            self.execute()
            time.sleep(0.2)

    def start(self) -> None:
        if not self._running:
            self._thread = threading.Thread(target=self.run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def is_running(self) -> bool:
        return self._running


class RelayManager:
    """Manages multiple PLC relays."""

    def __init__(self):
        self.relays: Dict[str, PlcIO] = {}
        self.programs: Dict[str, LDProgram] = {}
        self.current_relay: Optional[PlcIO] = None
        self.current_program: Optional[LDProgram] = None
        self.create_relay("relay1", 6, 6)
        self.select_relay("relay1")

    def create_relay(self, name: str, num_inputs: int, num_outputs: int) -> None:
        relay = PlcIO(name, num_inputs, num_outputs)
        self.relays[name] = relay
        self.programs[name] = LDProgram(relay, f"{name}_program")

    def select_relay(self, name: str) -> bool:
        if name in self.relays:
            self.current_relay = self.relays[name]
            self.current_program = self.programs[name]
            return True
        return False

    def get_relay_names(self) -> List[str]:
        return list(self.relays.keys())

    def has_relay(self, name: str) -> bool:
        return name in self.relays


# ============================================================
# LD Canvas — visual ladder diagram renderer
# ============================================================

# Rung layout constants
RUNG_H         = 100   # height per rung (pixels)
RUNG_TOP_PAD   = 20    # padding above first rung
RUNG_LABEL_W   = 50    # left rail + rung number area
CELL_W         = 100   # width per rung cell
CELL_H         = 60    # height of the element area within a rung
RAIL_W         = 14    # width of power rails
RIGHT_RAIL_PAD = 20    # right padding after last cell


class LDCanvas(tk.Canvas):
    """
    Visual Ladder Diagram canvas.
    Renders each logic element as a standard rung with contacts and coils.
    Supports click-to-select.
    """

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=Theme.CANVAS_BG,
                         highlightthickness=1, highlightbackground=Theme.BORDER,
                         **kwargs)
        self._app = app
        self._selected_rung: Optional[int] = None
        self._rung_boxes: List[Tuple[int, int, int, int]] = []  # (x1,y1,x2,y2) per rung
        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", lambda e: self.redraw())

    @property
    def selected_rung(self) -> Optional[int]:
        return self._selected_rung

    def select_rung(self, index: Optional[int]) -> None:
        self._selected_rung = index
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        self._rung_boxes.clear()

        prog = self._app.manager.current_program
        io   = self._app.manager.current_relay
        elements = prog.get_elements() if prog else []

        canvas_w = max(self.winfo_width(), 500)
        total_h  = RUNG_TOP_PAD + max(len(elements), 1) * RUNG_H + 20
        self.configure(scrollregion=(0, 0, canvas_w, total_h))

        # ---- Empty state ----
        if not elements:
            self._draw_empty(canvas_w, total_h)
            return

        for rung_idx, elem in enumerate(elements):
            y_top = RUNG_TOP_PAD + rung_idx * RUNG_H
            self._draw_rung(rung_idx, elem, io, y_top, canvas_w)

    def _draw_empty(self, w: int, h: int) -> None:
        self.create_text(w // 2, h // 2,
                         text="No elements in program.\nUse toolbar to add AND / OR / NOT / RS elements.",
                         fill=Theme.SUBTEXT, font=("TkDefaultFont", 11),
                         justify=tk.CENTER)
        # Draw empty left rail
        rail_x = RUNG_LABEL_W
        self.create_rectangle(rail_x - RAIL_W, 10, rail_x, h - 10,
                               fill=Theme.RUNG_RAIL, outline="")

    def _draw_rung(self, idx: int, elem: LogicElement,
                   io: Optional[PlcIO], y_top: int, canvas_w: int) -> None:
        cells = elem.rung_elements()
        n_cells = len(cells)

        # Available width between rails
        usable_w = canvas_w - RUNG_LABEL_W - RAIL_W - RIGHT_RAIL_PAD
        cell_w = max(CELL_W, usable_w // n_cells)
        total_rung_w = cell_w * n_cells

        left_rail_x  = RUNG_LABEL_W
        right_rail_x = left_rail_x + total_rung_w + RAIL_W
        mid_y        = y_top + RUNG_H // 2

        selected = (self._selected_rung == idx)

        # ---- Background highlight ----
        if selected:
            self.create_rectangle(
                0, y_top, canvas_w, y_top + RUNG_H,
                fill=Theme.SELECTED_BG, outline=""
            )

        # ---- Rung index label ----
        self.create_text(left_rail_x - RAIL_W - 4, mid_y,
                         text=f"{idx + 1}", fill=Theme.SUBTEXT,
                         font=("TkFixedFont", 8), anchor=tk.E)

        # ---- Left power rail ----
        self.create_rectangle(left_rail_x - RAIL_W, y_top + 8,
                               left_rail_x, y_top + RUNG_H - 8,
                               fill=Theme.RUNG_RAIL, outline="")

        # ---- Horizontal rung wire ----
        self.create_line(left_rail_x, mid_y, right_rail_x, mid_y,
                         fill=Theme.RUNG_RAIL, width=2)

        # ---- Right power rail ----
        self.create_rectangle(right_rail_x, y_top + 8,
                               right_rail_x + RAIL_W, y_top + RUNG_H - 8,
                               fill=Theme.RUNG_RAIL, outline="")

        # ---- Draw each cell ----
        for cell_idx, cell in enumerate(cells):
            cx = left_rail_x + cell_idx * cell_w
            self._draw_cell(cell, io, cx, mid_y, cell_w)

        # ---- Element description text (below rung) ----
        desc_y = y_top + RUNG_H - 12
        self.create_text(left_rail_x + 4, desc_y,
                         text=str(elem), fill=Theme.SUBTEXT,
                         font=("TkFixedFont", 7), anchor=tk.W)

        # ---- Click bounding box ----
        self._rung_boxes.append((0, y_top, canvas_w, y_top + RUNG_H))

    def _draw_cell(self, cell: Dict, io: Optional[PlcIO],
                   x: int, mid_y: int, cell_w: int) -> None:
        """Draw a single rung cell (contact or coil)."""
        ctype   = cell["type"]
        label   = cell["label"]
        ch      = cell.get("ch")
        kind    = cell.get("kind", "input")

        cx = x + cell_w // 2   # centre x of the cell

        # Determine active state
        active = False
        if io and ch is not None:
            if kind == "input":
                active = io.get_input(ch)
            else:
                active = io.get_output(ch)

        if ctype == "OR_JOIN":
            self._draw_or_contact(cx, mid_y, label, active)
        elif ctype in ("NO", "NC"):
            self._draw_contact(cx, mid_y, label, active, normally_closed=(ctype == "NC"))
        elif ctype == "COIL":
            self._draw_coil(cx, mid_y, label, active, style="normal")
        elif ctype == "SET_COIL":
            self._draw_coil(cx, mid_y, label, active, style="set")
        elif ctype == "RST_COIL":
            self._draw_coil(cx, mid_y, label, active, style="reset")

    def _draw_contact(self, cx: int, mid_y: int,
                      label: str, active: bool, normally_closed: bool) -> None:
        """
        Draw a standard contact symbol:
          --| |-- (NO) or --|/|-- (NC)
        """
        GAP   = 10   # gap between contact lines
        H     = 22   # half-height of contact symbol
        W     = 8    # contact line width (visual tick)

        fill  = Theme.CONTACT_ACTIVE if active else Theme.CONTACT_FILL
        lx    = cx - GAP
        rx    = cx + GAP

        # Left contact leg
        self.create_line(lx - W, mid_y, lx, mid_y,
                         fill=Theme.RUNG_RAIL, width=2)
        # Left vertical bar
        self.create_line(lx, mid_y - H, lx, mid_y + H,
                         fill=fill if active else Theme.RUNG_RAIL, width=3)
        # Right vertical bar
        self.create_line(rx, mid_y - H, rx, mid_y + H,
                         fill=fill if active else Theme.RUNG_RAIL, width=3)
        # Right contact leg
        self.create_line(rx, mid_y, rx + W, mid_y,
                         fill=Theme.RUNG_RAIL, width=2)

        # Normally-closed diagonal slash
        if normally_closed:
            self.create_line(lx + 2, mid_y + H - 4, rx - 2, mid_y - H + 4,
                             fill=Theme.DANGER, width=2)

        # Background rect (hover/active area)
        r = 4
        self.create_rectangle(cx - GAP - W - 4, mid_y - H - 4,
                               cx + GAP + W + 4, mid_y + H + 4,
                               fill=fill, outline=Theme.ACCENT if active else Theme.BORDER,
                               width=1)
        self.tag_lower(self.find_withtag("all")[-1])  # push rect behind lines

        # Label above the contact
        self.create_text(cx, mid_y - H - 10, text=label,
                         fill=Theme.ACCENT if active else Theme.TEXT,
                         font=("TkFixedFont", 8, "bold" if active else "normal"),
                         anchor=tk.S)

    def _draw_or_contact(self, cx: int, mid_y: int, label: str, active: bool) -> None:
        """
        Draw an OR branch contact — the second input shown as a parallel branch.
        Rendered as a smaller contact symbol below the main wire with branch lines.
        """
        GAP    = 10
        H      = 22
        W      = 8
        offset = 32  # vertical offset of parallel branch

        # Branch vertical connectors
        self.create_line(cx - GAP - W, mid_y, cx - GAP - W, mid_y + offset,
                         fill=Theme.RUNG_RAIL, width=2)
        self.create_line(cx + GAP + W, mid_y, cx + GAP + W, mid_y + offset,
                         fill=Theme.RUNG_RAIL, width=2)

        branch_y = mid_y + offset
        fill = Theme.CONTACT_ACTIVE if active else Theme.CONTACT_FILL

        # Contact bars at branch level
        self.create_line(cx - GAP - W, branch_y, cx - GAP, branch_y,
                         fill=Theme.RUNG_RAIL, width=2)
        self.create_line(cx - GAP, branch_y - H, cx - GAP, branch_y + H,
                         fill=Theme.RUNG_RAIL, width=3)
        self.create_line(cx + GAP, branch_y - H, cx + GAP, branch_y + H,
                         fill=Theme.RUNG_RAIL, width=3)
        self.create_line(cx + GAP, branch_y, cx + GAP + W, branch_y,
                         fill=Theme.RUNG_RAIL, width=2)

        self.create_rectangle(cx - GAP - W - 4, branch_y - H - 4,
                               cx + GAP + W + 4, branch_y + H + 4,
                               fill=fill, outline=Theme.ACCENT if active else Theme.BORDER)
        self.tag_lower(self.find_withtag("all")[-1])

        self.create_text(cx, branch_y - H - 10, text=label,
                         fill=Theme.ACCENT if active else Theme.TEXT,
                         font=("TkFixedFont", 8))

    def _draw_coil(self, cx: int, mid_y: int,
                   label: str, active: bool, style: str = "normal") -> None:
        """
        Draw a coil symbol: --( )--
        style: 'normal', 'set', 'reset'
        """
        R = 18   # coil radius
        W = 10   # lead line length

        if style == "set":
            base_fill = Theme.COIL_SET_FILL
            act_fill  = Theme.COIL_SET_ACTIVE
            inner_text = "S"
        elif style == "reset":
            base_fill = Theme.COIL_FILL
            act_fill  = Theme.COIL_ACTIVE
            inner_text = "R"
        else:
            base_fill = Theme.COIL_FILL
            act_fill  = Theme.COIL_ACTIVE
            inner_text = ""

        fill = act_fill if active else base_fill
        outline = Theme.DANGER if active else Theme.BORDER

        # Left lead
        self.create_line(cx - R - W, mid_y, cx - R, mid_y,
                         fill=Theme.RUNG_RAIL, width=2)
        # Right lead
        self.create_line(cx + R, mid_y, cx + R + W, mid_y,
                         fill=Theme.RUNG_RAIL, width=2)
        # Circle coil body
        self.create_oval(cx - R, mid_y - R, cx + R, mid_y + R,
                         fill=fill, outline=outline, width=2)

        # Inner letter for Set/Reset
        if inner_text:
            self.create_text(cx, mid_y, text=inner_text,
                             fill=Theme.TEXT, font=("TkFixedFont", 9, "bold"))

        # Label above coil
        self.create_text(cx, mid_y - R - 10, text=label,
                         fill=Theme.DANGER if active else Theme.TEXT,
                         font=("TkFixedFont", 8, "bold" if active else "normal"),
                         anchor=tk.S)

    def _on_click(self, event: Any) -> None:
        y = self.canvasy(event.y)
        for i, (x1, y1, x2, y2) in enumerate(self._rung_boxes):
            if y1 <= y <= y2:
                self._selected_rung = i
                self._app.on_rung_select(i)
                self.redraw()
                return
        self._selected_rung = None
        self._app.on_rung_select(None)
        self.redraw()


# ============================================================
# GTK-style dialogs
# ============================================================

class _GtkDialog(tk.Toplevel):
    """Base GTK-style dialog."""

    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.configure(bg=Theme.BG)

        # Header
        header = tk.Frame(self, bg=Theme.HEADERBAR_BG, pady=8)
        header.pack(fill=tk.X)
        tk.Label(header, text=title, font=("TkDefaultFont", 11, "bold"),
                 bg=Theme.HEADERBAR_BG, fg=Theme.HEADERBAR_FG).pack(padx=12)

        # Content area
        self._content = tk.Frame(self, bg=Theme.BG, padx=16, pady=12)
        self._content.pack(fill=tk.BOTH, expand=True)

        # Button row
        self._btn_row = tk.Frame(self, bg=Theme.BG, pady=8)
        self._btn_row.pack(fill=tk.X, padx=16)

        self.bind("<Escape>", lambda e: self.destroy())

        # Centre over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _add_field(self, row: int, label_text: str, default: str = "",
                   width: int = 10) -> tk.StringVar:
        tk.Label(self._content, text=label_text, bg=Theme.BG,
                 fg=Theme.TEXT, anchor=tk.W,
                 font=("TkDefaultFont", 10)).grid(
            row=row, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        var = tk.StringVar(value=default)
        entry = tk.Entry(self._content, textvariable=var, width=width,
                         relief=tk.FLAT,
                         highlightthickness=1,
                         highlightcolor=Theme.ACCENT,
                         highlightbackground=Theme.BORDER)
        entry.grid(row=row, column=1, sticky=tk.W, pady=4)
        return var

    def _add_button(self, text: str, command, primary: bool = False) -> tk.Button:
        bg = Theme.ACCENT if primary else Theme.SIDEBAR_BG
        fg = Theme.ACCENT_FG if primary else Theme.TEXT
        btn = tk.Button(self._btn_row, text=text, command=command,
                        bg=bg, fg=fg, relief=tk.FLAT, padx=12, pady=6,
                        font=("TkDefaultFont", 10),
                        activebackground=Theme.ACCENT_HOVER,
                        activeforeground=Theme.ACCENT_FG,
                        cursor="hand2")
        btn.pack(side=tk.RIGHT, padx=4)
        return btn


class GateDialog(_GtkDialog):
    """GTK-style dialog for adding a logic gate."""

    def __init__(self, parent, gate_type: str, max_inputs: int, max_outputs: int):
        super().__init__(parent, f"Add {gate_type} Element")
        self.result: Optional[LogicElement] = None
        self.gate_type = gate_type
        self._entries: Dict[str, tk.StringVar] = {}

        # Describe element
        desc = {
            "AND": "Normally-open contacts in series → output coil",
            "OR":  "Normally-open contacts in parallel → output coil",
            "NOT": "Normally-closed contact → output coil",
            "RS":  "Set/Reset coils (latch behaviour)",
        }
        tk.Label(self._content, text=desc.get(gate_type, ""),
                 bg=Theme.BG, fg=Theme.SUBTEXT,
                 font=("TkDefaultFont", 9, "italic"),
                 wraplength=260, justify=tk.LEFT).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        row = 1
        if gate_type in ("AND", "OR"):
            self._entries["in1"] = self._add_field(row, "Input 1 channel:", "1"); row += 1
            self._entries["in2"] = self._add_field(row, "Input 2 channel:", "2"); row += 1
            self._entries["out"] = self._add_field(row, "Output channel:",  "1"); row += 1
        elif gate_type == "NOT":
            self._entries["in1"] = self._add_field(row, "Input channel:",   "1"); row += 1
            self._entries["out"] = self._add_field(row, "Output channel:",  "1"); row += 1
        else:  # RS
            self._entries["set"]   = self._add_field(row, "SET input channel:",   "1"); row += 1
            self._entries["reset"] = self._add_field(row, "RESET input channel:", "2"); row += 1
            self._entries["out"]   = self._add_field(row, "Output channel:",      "1"); row += 1

        self._add_button("Cancel", self.destroy, primary=False)
        self._add_button("Add",    self._ok,     primary=True)

        self.bind("<Return>", lambda e: self._ok())
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _get_int(self, key: str) -> Optional[int]:
        try:
            val = int(self._entries[key].get())
            return val if val > 0 else None
        except (ValueError, KeyError):
            return None

    def _ok(self) -> None:
        try:
            if self.gate_type == "AND":
                in1, in2, out = self._get_int("in1"), self._get_int("in2"), self._get_int("out")
                if in1 and in2 and out:
                    self.result = AndGate(in1, in2, out)
            elif self.gate_type == "OR":
                in1, in2, out = self._get_int("in1"), self._get_int("in2"), self._get_int("out")
                if in1 and in2 and out:
                    self.result = OrGate(in1, in2, out)
            elif self.gate_type == "NOT":
                in1, out = self._get_int("in1"), self._get_int("out")
                if in1 and out:
                    self.result = NotGate(in1, out)
            elif self.gate_type == "RS":
                s, r, out = self._get_int("set"), self._get_int("reset"), self._get_int("out")
                if s and r and out:
                    self.result = RSTrigger(s, r, out)

            if self.result is None:
                messagebox.showerror("Invalid Input",
                                     "All channel numbers must be positive integers.",
                                     parent=self)
                return
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self.destroy()


class CreateRelayDialog(_GtkDialog):
    """GTK-style dialog for creating a new relay."""

    def __init__(self, parent):
        super().__init__(parent, "Create New Relay")
        self.result: Optional[tuple] = None

        tk.Label(self._content,
                 text="Configure the relay's input and output channels.",
                 bg=Theme.BG, fg=Theme.SUBTEXT,
                 font=("TkDefaultFont", 9, "italic")).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        self._name    = self._add_field(1, "Relay name:",         "relay1", width=16)
        self._inputs  = self._add_field(2, "Number of inputs:",   "6",      width=8)
        self._outputs = self._add_field(3, "Number of outputs:",  "6",      width=8)

        self._add_button("Cancel", self.destroy,  primary=False)
        self._add_button("Create", self._ok,      primary=True)

        self.bind("<Return>", lambda e: self._ok())
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _ok(self) -> None:
        name = self._name.get().strip()
        if not name:
            messagebox.showerror("Invalid Input", "Relay name cannot be empty.", parent=self)
            return
        try:
            inp = int(self._inputs.get())
            out = int(self._outputs.get())
            if inp <= 0 or out <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Input",
                                 "Input/output counts must be positive integers.", parent=self)
            return
        self.result = (name, inp, out)
        self.destroy()


# ============================================================
# Main Application Window — GTK/GNOME style
# ============================================================

class FreePLCGtkApp(tk.Tk):
    """
    Main FreePLC GUI window with GTK/GNOME styling.
    Features a header bar, side panel, and a visual LD canvas.
    """

    def __init__(self):
        super().__init__()
        self.manager = RelayManager()
        self._update_job: Optional[str] = None

        self.title("FreePLC")
        self.geometry("1100x680")
        self.minsize(900, 560)
        self.configure(bg=Theme.BG)

        self._build_ui()
        self._refresh_relay_list()
        self._start_io_refresh()

    # ----------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------

    def _build_ui(self) -> None:
        # ---- Header bar (GTK HeaderBar style) ----
        self._build_headerbar()

        # ---- Main area: sidebar + LD canvas ----
        main = tk.Frame(self, bg=Theme.BG)
        main.pack(fill=tk.BOTH, expand=True)

        self._build_sidebar(main)
        self._build_ld_area(main)

        # ---- Status bar ----
        self._build_statusbar()

    def _build_headerbar(self) -> None:
        bar = tk.Frame(self, bg=Theme.HEADERBAR_BG, height=46)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        # Left: app title + relay name
        left = tk.Frame(bar, bg=Theme.HEADERBAR_BG)
        left.pack(side=tk.LEFT, padx=12, pady=6)

        tk.Label(left, text="FreePLC", font=("TkDefaultFont", 13, "bold"),
                 bg=Theme.HEADERBAR_BG, fg=Theme.HEADERBAR_FG).pack(side=tk.LEFT)

        self._header_relay_lbl = tk.Label(left, text="",
                                          font=("TkDefaultFont", 11),
                                          bg=Theme.HEADERBAR_BG, fg="#b0b0b0")
        self._header_relay_lbl.pack(side=tk.LEFT, padx=(8, 0))

        # Right: run/stop buttons
        right = tk.Frame(bar, bg=Theme.HEADERBAR_BG)
        right.pack(side=tk.RIGHT, padx=12, pady=6)

        self._stop_btn = self._hdr_btn(right, "⏹  Stop",  self._stop_program,  enabled=False)
        self._stop_btn.pack(side=tk.RIGHT, padx=4)

        self._run_btn = self._hdr_btn(right, "▶  Run",   self._start_program, enabled=True)
        self._run_btn.pack(side=tk.RIGHT, padx=4)

        # Status pill
        self._run_pill = tk.Label(right, text="● STOPPED",
                                  font=("TkDefaultFont", 9, "bold"),
                                  bg=Theme.HEADERBAR_BG, fg=Theme.DANGER)
        self._run_pill.pack(side=tk.RIGHT, padx=8)

    def _hdr_btn(self, parent, text: str, cmd, enabled: bool = True) -> tk.Button:
        state = tk.NORMAL if enabled else tk.DISABLED
        btn = tk.Button(parent, text=text, command=cmd,
                        bg=Theme.ACCENT, fg=Theme.ACCENT_FG,
                        relief=tk.FLAT, padx=10, pady=4,
                        font=("TkDefaultFont", 9, "bold"),
                        activebackground=Theme.ACCENT_HOVER,
                        activeforeground=Theme.ACCENT_FG,
                        disabledforeground="#9ab0d8",
                        cursor="hand2", state=state)
        return btn

    def _build_sidebar(self, parent: tk.Frame) -> None:
        sidebar = tk.Frame(parent, bg=Theme.SIDEBAR_BG, width=230)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # ---- Relay section ----
        self._sidebar_section(sidebar, "Relays")

        self._relay_listbox = tk.Listbox(
            sidebar, font=("TkDefaultFont", 10),
            selectmode=tk.SINGLE, height=6,
            bg=Theme.CANVAS_BG, fg=Theme.TEXT,
            selectbackground=Theme.ACCENT,
            selectforeground=Theme.ACCENT_FG,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=Theme.BORDER,
            activestyle="none",
        )
        self._relay_listbox.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._relay_listbox.bind("<<ListboxSelect>>", self._on_relay_click)
        self._relay_listbox.bind("<Double-Button-1>", lambda e: self._select_relay())

        btn_row = tk.Frame(sidebar, bg=Theme.SIDEBAR_BG)
        btn_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._sidebar_btn(btn_row, "＋ New Relay",    self._create_relay).pack(side=tk.LEFT)
        self._sidebar_btn(btn_row, "✓ Select",        self._select_relay).pack(side=tk.LEFT, padx=(4, 0))

        # ---- Relay info ----
        self._relay_info = tk.Label(sidebar, text="",
                                    bg=Theme.SIDEBAR_BG, fg=Theme.SUBTEXT,
                                    font=("TkFixedFont", 8),
                                    justify=tk.LEFT, anchor=tk.W, padx=8)
        self._relay_info.pack(fill=tk.X)

        # ---- Separator ----
        tk.Frame(sidebar, bg=Theme.BORDER, height=1).pack(fill=tk.X, padx=8, pady=8)

        # ---- LD Elements toolbar ----
        self._sidebar_section(sidebar, "Add Element")

        for gate in ("AND", "OR", "NOT", "RS"):
            desc = {"AND": "Series contacts",
                    "OR":  "Parallel contacts",
                    "NOT": "Inverted contact",
                    "RS":  "Set/Reset latch"}[gate]
            row = tk.Frame(sidebar, bg=Theme.SIDEBAR_BG)
            row.pack(fill=tk.X, padx=8, pady=2)
            self._sidebar_btn(row, gate, lambda g=gate: self._add_gate(g),
                              width=6).pack(side=tk.LEFT)
            tk.Label(row, text=desc, bg=Theme.SIDEBAR_BG, fg=Theme.SUBTEXT,
                     font=("TkDefaultFont", 8)).pack(side=tk.LEFT, padx=(6, 0))

        # ---- Separator ----
        tk.Frame(sidebar, bg=Theme.BORDER, height=1).pack(fill=tk.X, padx=8, pady=8)

        # ---- Program actions ----
        self._sidebar_section(sidebar, "Program")

        act_row = tk.Frame(sidebar, bg=Theme.SIDEBAR_BG)
        act_row.pack(fill=tk.X, padx=8, pady=2)
        self._remove_btn = self._sidebar_btn(act_row, "✕ Remove Selected",
                                             self._remove_element, danger=True)
        self._remove_btn.pack(fill=tk.X)

        act_row2 = tk.Frame(sidebar, bg=Theme.SIDEBAR_BG)
        act_row2.pack(fill=tk.X, padx=8, pady=2)
        self._sidebar_btn(act_row2, "Clear All", self._clear_program,
                          danger=True).pack(fill=tk.X)

        # ---- Separator ----
        tk.Frame(sidebar, bg=Theme.BORDER, height=1).pack(fill=tk.X, padx=8, pady=8)

        # ---- I/O panel ----
        self._sidebar_section(sidebar, "I/O Status")

        io_scroll_frame = tk.Frame(sidebar, bg=Theme.SIDEBAR_BG)
        io_scroll_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        vsb = tk.Scrollbar(io_scroll_frame, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._io_canvas = tk.Canvas(io_scroll_frame, bg=Theme.SIDEBAR_BG,
                                    yscrollcommand=vsb.set,
                                    highlightthickness=0)
        self._io_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=self._io_canvas.yview)

        self._io_inner = tk.Frame(self._io_canvas, bg=Theme.SIDEBAR_BG)
        self._io_canvas.create_window((0, 0), window=self._io_inner, anchor=tk.NW)
        self._io_inner.bind("<Configure>",
                            lambda e: self._io_canvas.configure(
                                scrollregion=self._io_canvas.bbox("all")))

    def _sidebar_section(self, parent: tk.Frame, title: str) -> None:
        tk.Label(parent, text=title.upper(),
                 bg=Theme.SIDEBAR_BG, fg=Theme.SUBTEXT,
                 font=("TkDefaultFont", 7, "bold"),
                 anchor=tk.W, padx=8, pady=2).pack(fill=tk.X)

    def _sidebar_btn(self, parent: tk.Frame, text: str, cmd,
                     width: int = 0, danger: bool = False) -> tk.Button:
        bg = "#d93025" if danger else Theme.BG
        fg = "#ffffff" if danger else Theme.TEXT
        kw = dict(width=width) if width else {}
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg=fg,
                         relief=tk.FLAT, padx=8, pady=4,
                         font=("TkDefaultFont", 9),
                         activebackground=Theme.ACCENT,
                         activeforeground=Theme.ACCENT_FG,
                         cursor="hand2", **kw)

    def _build_ld_area(self, parent: tk.Frame) -> None:
        """Right area: LD canvas + manual I/O control strip at bottom."""
        right = tk.Frame(parent, bg=Theme.BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ---- LD Canvas with scrollbar ----
        ld_frame = tk.Frame(right, bg=Theme.BG)
        ld_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        tk.Label(ld_frame, text="Ladder Diagram",
                 bg=Theme.BG, fg=Theme.SUBTEXT,
                 font=("TkDefaultFont", 8, "bold")).pack(anchor=tk.W)

        canvas_frame = tk.Frame(ld_frame, bg=Theme.BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        vsb = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        self._ld_canvas = LDCanvas(canvas_frame, self,
                                   yscrollcommand=vsb.set,
                                   xscrollcommand=hsb.set)
        self._ld_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=self._ld_canvas.yview)
        hsb.config(command=self._ld_canvas.xview)

        # ---- Manual I/O strip ----
        io_strip = tk.LabelFrame(right, text="Manual Input Control",
                                 bg=Theme.BG, fg=Theme.SUBTEXT,
                                 font=("TkDefaultFont", 8, "bold"),
                                 relief=tk.FLAT,
                                 highlightthickness=1,
                                 highlightbackground=Theme.BORDER)
        io_strip.pack(fill=tk.X, padx=8, pady=(0, 8))

        self._manual_io_frame = tk.Frame(io_strip, bg=Theme.BG)
        self._manual_io_frame.pack(fill=tk.X, padx=4, pady=4)

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=Theme.SIDEBAR_BG,
                       highlightthickness=1, highlightbackground=Theme.BORDER)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_var = tk.StringVar(value="Ready — select a relay and add elements to start")
        tk.Label(bar, textvariable=self._status_var,
                 bg=Theme.SIDEBAR_BG, fg=Theme.SUBTEXT,
                 font=("TkDefaultFont", 9),
                 anchor=tk.W, padx=10, pady=4).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._scan_lbl = tk.Label(bar, text="",
                                  bg=Theme.SIDEBAR_BG, fg=Theme.SUBTEXT,
                                  font=("TkFixedFont", 8), padx=10)
        self._scan_lbl.pack(side=tk.RIGHT)

    # ----------------------------------------------------------
    # Relay actions
    # ----------------------------------------------------------

    def _refresh_relay_list(self) -> None:
        self._relay_listbox.delete(0, tk.END)
        names = self.manager.get_relay_names()
        current = self.manager.current_relay
        for name in names:
            suffix = "  ✓" if (current and current.name == name) else ""
            self._relay_listbox.insert(tk.END, f" {name}{suffix}")
        if current:
            self._relay_info.config(
                text=f"Inputs: {len(current.inputs)}   Outputs: {len(current.outputs)}")
            self._header_relay_lbl.config(text=f"/ {current.name}")
        else:
            self._relay_info.config(text="")
            self._header_relay_lbl.config(text="")

    def _on_relay_click(self, event: Any) -> None:
        pass  # highlight only; double-click or button to activate

    def _create_relay(self) -> None:
        dlg = CreateRelayDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            name, inp, out = dlg.result
            if self.manager.has_relay(name):
                self._set_status(f"Relay '{name}' already exists.", error=True)
                return
            self.manager.create_relay(name, inp, out)
            self.manager.select_relay(name)
            self._refresh_relay_list()
            self._ld_canvas.select_rung(None)
            self._ld_canvas.redraw()
            self._rebuild_manual_io()
            self._refresh_io_panel()
            self._set_status(f"Relay '{name}' created ({inp} inputs, {out} outputs).")

    def _select_relay(self) -> None:
        sel = self._relay_listbox.curselection()
        if not sel:
            self._set_status("Select a relay from the list first.", error=True)
            return
        names = self.manager.get_relay_names()
        idx = sel[0]
        if idx >= len(names):
            return
        name = names[idx]
        if self.manager.current_program and self.manager.current_program.is_running():
            self.manager.current_program.stop()
            self._update_run_ui(running=False)
        self.manager.select_relay(name)
        self._refresh_relay_list()
        self._ld_canvas.select_rung(None)
        self._ld_canvas.redraw()
        self._rebuild_manual_io()
        self._refresh_io_panel()
        self._set_status(f"Relay '{name}' selected.")

    # ----------------------------------------------------------
    # LD element actions
    # ----------------------------------------------------------

    def _add_gate(self, gate_type: str) -> None:
        relay = self.manager.current_relay
        prog  = self.manager.current_program
        if not relay or not prog:
            self._set_status("No relay selected.", error=True)
            return
        dlg = GateDialog(self, gate_type, len(relay.inputs), len(relay.outputs))
        self.wait_window(dlg)
        if dlg.result:
            prog.add_element(dlg.result)
            self._ld_canvas.redraw()
            self._set_status(f"{gate_type} element added.")

    def _remove_element(self) -> None:
        idx = self._ld_canvas.selected_rung
        prog = self.manager.current_program
        if idx is None:
            self._set_status("Click a rung on the canvas to select it first.", error=True)
            return
        if not prog:
            return
        elements = prog.get_elements()
        if idx < len(elements):
            prog.remove_element(idx)
            self._ld_canvas.select_rung(None)
            self._ld_canvas.redraw()
            self._set_status(f"Rung {idx + 1} removed.")

    def _clear_program(self) -> None:
        prog = self.manager.current_program
        if not prog:
            return
        if messagebox.askyesno("Confirm", "Clear entire ladder program?", parent=self):
            prog.clear_elements()
            self._ld_canvas.select_rung(None)
            self._ld_canvas.redraw()
            self._set_status("Program cleared.")

    def on_rung_select(self, index: Optional[int]) -> None:
        """Called by LDCanvas when a rung is selected/deselected."""
        prog = self.manager.current_program
        if index is not None and prog:
            elements = prog.get_elements()
            if index < len(elements):
                self._set_status(f"Rung {index + 1}: {elements[index]}")
            return
        self._set_status("")

    # ----------------------------------------------------------
    # Run / Stop
    # ----------------------------------------------------------

    def _start_program(self) -> None:
        prog = self.manager.current_program
        if not prog:
            self._set_status("No relay selected.", error=True)
            return
        if not prog.get_elements():
            self._set_status("Program is empty — add elements first.", error=True)
            return
        if prog.is_running():
            return
        prog.start()
        self._update_run_ui(running=True)
        self._set_status("Program running (200 ms scan cycle).")

    def _stop_program(self) -> None:
        prog = self.manager.current_program
        if prog and prog.is_running():
            prog.stop()
        self._update_run_ui(running=False)
        self._set_status("Program stopped.")

    def _update_run_ui(self, running: bool) -> None:
        if running:
            self._run_btn.config(state=tk.DISABLED)
            self._stop_btn.config(state=tk.NORMAL)
            self._run_pill.config(text="● RUNNING", fg=Theme.SUCCESS)
        else:
            self._run_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            self._run_pill.config(text="● STOPPED", fg=Theme.DANGER)

    # ----------------------------------------------------------
    # Manual I/O control strip
    # ----------------------------------------------------------

    def _rebuild_manual_io(self) -> None:
        for w in self._manual_io_frame.winfo_children():
            w.destroy()

        relay = self.manager.current_relay
        if not relay:
            tk.Label(self._manual_io_frame, text="(no relay selected)",
                     bg=Theme.BG, fg=Theme.SUBTEXT).pack()
            return

        self._input_vars: Dict[int, tk.BooleanVar] = {}
        for ch, val in sorted(relay.inputs.items()):
            var = tk.BooleanVar(value=val)
            self._input_vars[ch] = var
            btn = tk.Checkbutton(
                self._manual_io_frame,
                text=f"I{ch}",
                variable=var,
                indicatoron=False,
                font=("TkFixedFont", 9, "bold"),
                bg=Theme.DANGER, fg="#ffffff",
                selectcolor=Theme.SUCCESS,
                activebackground=Theme.SUCCESS,
                padx=8, pady=4,
                relief=tk.FLAT,
                cursor="hand2",
                command=lambda c=ch, v=var: self._toggle_input(c, v),
            )
            btn.pack(side=tk.LEFT, padx=3, pady=4)

    def _toggle_input(self, channel: int, var: tk.BooleanVar) -> None:
        relay = self.manager.current_relay
        prog  = self.manager.current_program
        if not relay:
            return
        val = var.get()
        relay.set_input(channel, val)
        if prog and prog.is_running():
            prog.execute()
        self._refresh_io_panel()
        self._ld_canvas.redraw()
        self._set_status(f"Input I{channel} → {'ON' if val else 'OFF'}")

    # ----------------------------------------------------------
    # I/O panel refresh (sidebar)
    # ----------------------------------------------------------

    def _refresh_io_panel(self) -> None:
        for w in self._io_inner.winfo_children():
            w.destroy()

        relay = self.manager.current_relay
        if not relay:
            tk.Label(self._io_inner, text="No relay",
                     bg=Theme.SIDEBAR_BG, fg=Theme.SUBTEXT,
                     font=("TkDefaultFont", 8)).pack(pady=4)
            return

        # Inputs
        self._io_section("Inputs", self._io_inner)
        for ch in sorted(relay.inputs.keys()):
            self._io_row(self._io_inner, f"I{ch}", relay.inputs[ch])

        self._io_section("Outputs", self._io_inner)
        for ch in sorted(relay.outputs.keys()):
            self._io_row(self._io_inner, f"Q{ch}", relay.outputs[ch])

        self._io_inner.update_idletasks()
        self._io_canvas.configure(scrollregion=self._io_canvas.bbox("all"))

        # Sync manual buttons
        if hasattr(self, "_input_vars"):
            for ch, var in self._input_vars.items():
                cur = relay.inputs.get(ch, False)
                if var.get() != cur:
                    var.set(cur)

    def _io_section(self, title: str, parent: tk.Frame) -> None:
        tk.Label(parent, text=title,
                 bg=Theme.SIDEBAR_BG, fg=Theme.SUBTEXT,
                 font=("TkDefaultFont", 7, "bold"),
                 anchor=tk.W).pack(fill=tk.X, pady=(4, 1))

    def _io_row(self, parent: tk.Frame, label: str, active: bool) -> None:
        row = tk.Frame(parent, bg=Theme.SIDEBAR_BG)
        row.pack(fill=tk.X, pady=1)
        tk.Label(row, text=label, width=4,
                 bg=Theme.SIDEBAR_BG, fg=Theme.TEXT,
                 font=("TkFixedFont", 8), anchor=tk.W).pack(side=tk.LEFT)
        color = Theme.SUCCESS if active else Theme.DANGER
        tk.Label(row, text="ON " if active else "OFF",
                 bg=color, fg="#ffffff",
                 font=("TkFixedFont", 7, "bold"),
                 padx=4, pady=1, width=4).pack(side=tk.LEFT)

    # ----------------------------------------------------------
    # Periodic I/O refresh
    # ----------------------------------------------------------

    def _start_io_refresh(self) -> None:
        self._rebuild_manual_io()
        self._refresh_io_panel()
        self._schedule_io_refresh()

    def _schedule_io_refresh(self) -> None:
        self._do_io_refresh()
        self._update_job = self.after(250, self._schedule_io_refresh)

    def _do_io_refresh(self) -> None:
        prog = self.manager.current_program
        if prog:
            running = prog.is_running()
            self._update_run_ui(running)
            if running:
                self._refresh_io_panel()
                self._ld_canvas.redraw()
                # Scan cycle counter
                ts = time.strftime("%H:%M:%S")
                self._scan_lbl.config(text=f"scan  {ts}")

    # ----------------------------------------------------------
    # Status bar
    # ----------------------------------------------------------

    def _set_status(self, msg: str, error: bool = False) -> None:
        self._status_var.set(msg)
        fg = Theme.DANGER if error else Theme.SUBTEXT
        # find the status label (first child of status bar)
        for w in self.pack_slaves():
            if isinstance(w, tk.Frame) and w.cget("bg") == Theme.SIDEBAR_BG:
                for child in w.winfo_children():
                    if isinstance(child, tk.Label) and child.cget("textvariable"):
                        child.config(fg=fg)
                        break

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------

    def on_close(self) -> None:
        if self.manager.current_program:
            self.manager.current_program.stop()
        if self._update_job:
            self.after_cancel(self._update_job)
        self.destroy()


# ============================================================
# Entry point
# ============================================================

def main():
    app = FreePLCGtkApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
