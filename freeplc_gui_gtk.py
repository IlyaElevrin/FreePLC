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

Canvas layout (Owen Logic style):
  - Left power rail with input pins (I1..In) on the left side
  - Right power rail with output pins (Q1..Qn) on the right side
  - Rungs span between the rails
  - Function blocks can be dragged from the toolbox onto the canvas
  - Blocks show inputs on their left side and outputs on their right side
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
    CANVAS_BG      = "#f8f9fa"
    RUNG_RAIL      = "#2d2d2d"
    CONTACT_FILL   = "#d0e4ff"
    CONTACT_ACTIVE = "#1c71d8"
    COIL_FILL      = "#ffd0d0"
    COIL_ACTIVE    = "#e01b24"
    COIL_SET_FILL  = "#d0ffd0"
    COIL_SET_ACTIVE= "#26a269"
    SELECTED_BG    = "#c6e2ff"
    HOVERED_BG     = "#e8f0fb"
    BLOCK_BG       = "#ffffff"
    BLOCK_BORDER   = "#3d3d3d"
    BLOCK_SELECTED = "#1c71d8"
    RAIL_LEFT_BG   = "#dbe8ff"
    RAIL_RIGHT_BG  = "#ffe8e8"
    PIN_INPUT      = "#1c71d8"
    PIN_OUTPUT     = "#e01b24"
    WIRE_COLOR     = "#2d2d2d"
    WIRE_ACTIVE    = "#1c71d8"
    TOOLBOX_BG     = "#2b2b2b"
    TOOLBOX_FG     = "#ffffff"
    TOOLBOX_BTN_BG = "#3d3d3d"
    TOOLBOX_BTN_HOVER = "#4a4a4a"
    TOOLBOX_ACCENT = "#4a9eff"


# ============================================================
# Core PLC logic (Python port of C++ logic classes)
# ============================================================

class PlcIO:
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
    def evaluate(self, io: PlcIO) -> bool:
        raise NotImplementedError

    def __str__(self) -> str:
        raise NotImplementedError

    def ld_label(self) -> str:
        raise NotImplementedError

    def ld_type(self) -> str:
        raise NotImplementedError

    def rung_elements(self) -> List[Dict]:
        raise NotImplementedError

    def get_inputs(self) -> List[int]:
        """Return list of input channel numbers used by this element."""
        raise NotImplementedError

    def get_outputs(self) -> List[int]:
        """Return list of output channel numbers used by this element."""
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

    def get_inputs(self) -> List[int]:
        return [self.input1, self.input2]

    def get_outputs(self) -> List[int]:
        return [self.output]


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
            {"type": "NO",      "label": f"I{self.input1}", "ch": self.input1, "kind": "input"},
            {"type": "OR_JOIN", "label": f"I{self.input2}", "ch": self.input2, "kind": "input"},
            {"type": "COIL",    "label": f"Q{self.output}", "ch": self.output, "kind": "output"},
        ]

    def get_inputs(self) -> List[int]:
        return [self.input1, self.input2]

    def get_outputs(self) -> List[int]:
        return [self.output]


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

    def get_inputs(self) -> List[int]:
        return [self.input]

    def get_outputs(self) -> List[int]:
        return [self.output]


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
            {"type": "NO",       "label": f"I{self.set_input}",  "ch": self.set_input,   "kind": "input"},
            {"type": "NO",       "label": f"I{self.reset_input}", "ch": self.reset_input, "kind": "input"},
            {"type": "SET_COIL", "label": f"Q{self.output}(S)",   "ch": self.output,      "kind": "output"},
        ]

    def get_inputs(self) -> List[int]:
        return [self.set_input, self.reset_input]

    def get_outputs(self) -> List[int]:
        return [self.output]


class LDProgram:
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

    def move_element(self, from_idx: int, to_idx: int) -> None:
        """Move element from one position to another (drag-and-drop reordering)."""
        with self._lock:
            n = len(self.elements)
            if 0 <= from_idx < n and 0 <= to_idx < n and from_idx != to_idx:
                elem = self.elements.pop(from_idx)
                self.elements.insert(to_idx, elem)

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
# Canvas layout constants (Owen Logic style)
# ============================================================
LEFT_RAIL_W    = 80    # Width of left power rail + input pins area
RIGHT_RAIL_W   = 80    # Width of right power rail + output pins area
RUNG_H         = 110   # Height per rung row
RUNG_TOP_PAD   = 30    # Top padding before first rung
BLOCK_W        = 120   # Function block width
BLOCK_H        = 70    # Function block height
PIN_R          = 6     # Pin circle radius
WIRE_V_OFFSET  = 20    # Vertical spacing between wires on block
RAIL_W         = 8     # Power rail bar width


# ============================================================
# LD Canvas — Owen Logic style with draggable function blocks
# ============================================================

class LDCanvas(tk.Canvas):
    """
    Visual Ladder Diagram canvas inspired by Owen Logic:
    - Left rail with input pins (I1..In) on the left side of canvas
    - Right rail with output pins (Q1..Qn) on the right side
    - Function blocks (AND/OR/NOT/RS) placed between the rails
    - Blocks show their input pins on the left and output pins on the right
    - Rungs connect left rail → block inputs, block outputs → right rail
    - Blocks can be dragged to reorder rungs
    """

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=Theme.CANVAS_BG,
                         highlightthickness=1, highlightbackground=Theme.BORDER,
                         **kwargs)
        self._app = app
        self._selected_rung: Optional[int] = None

        # Drag state
        self._drag_rung: Optional[int] = None
        self._drag_start_y: Optional[int] = None
        self._drag_ghost_y: Optional[int] = None

        # Rung layout info: list of (y_top, y_bot, block_x, block_y) per rung
        self._rung_layout: List[Dict] = []

        self.bind("<Button-1>",        self._on_click)
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>",       lambda e: self.redraw())

    @property
    def selected_rung(self) -> Optional[int]:
        return self._selected_rung

    def select_rung(self, index: Optional[int]) -> None:
        self._selected_rung = index
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        self._rung_layout.clear()

        prog = self._app.manager.current_program
        io   = self._app.manager.current_relay
        elements = prog.get_elements() if prog else []

        canvas_w = max(self.winfo_width(), 600)
        n_rungs  = max(len(elements), 1)
        total_h  = RUNG_TOP_PAD + n_rungs * RUNG_H + 40
        self.configure(scrollregion=(0, 0, canvas_w, total_h))

        # Draw background grid lines for guidance
        self._draw_grid(canvas_w, total_h)

        # Draw power rails
        self._draw_rails(canvas_w, total_h, io)

        if not elements:
            self._draw_empty_hint(canvas_w, total_h)
            return

        for rung_idx, elem in enumerate(elements):
            y_top = RUNG_TOP_PAD + rung_idx * RUNG_H
            self._draw_rung(rung_idx, elem, io, y_top, canvas_w)

        # Draw drag ghost if dragging
        if self._drag_ghost_y is not None and self._drag_rung is not None:
            self._draw_drag_indicator(canvas_w)

    def _draw_grid(self, w: int, h: int) -> None:
        """Draw subtle background grid."""
        for y in range(0, h, RUNG_H):
            self.create_line(LEFT_RAIL_W, y, w - RIGHT_RAIL_W, y,
                             fill="#eeeeee", width=1, dash=(4, 8))

    def _draw_rails(self, canvas_w: int, total_h: int, io: Optional[PlcIO]) -> None:
        """Draw left (input) and right (output) power rails with labeled pins."""
        # --- Left rail (inputs) ---
        lx = LEFT_RAIL_W - RAIL_W // 2
        self.create_rectangle(lx - RAIL_W // 2, 0, lx + RAIL_W // 2, total_h,
                               fill=Theme.RUNG_RAIL, outline="")
        # Left rail header
        self.create_rectangle(0, 0, LEFT_RAIL_W, RUNG_TOP_PAD,
                               fill=Theme.RAIL_LEFT_BG, outline=Theme.BORDER)
        self.create_text(LEFT_RAIL_W // 2, RUNG_TOP_PAD // 2,
                         text="INPUTS", fill=Theme.PIN_INPUT,
                         font=("TkDefaultFont", 7, "bold"))

        # Draw input pin labels on left rail
        if io:
            for ch in sorted(io.inputs.keys()):
                active = io.get_input(ch)
                # Pin position — evenly spaced in the first portion of canvas height
                pin_y = RUNG_TOP_PAD + (ch - 1) * (RUNG_H // 2) + RUNG_H // 4
                pin_x = lx
                color = Theme.CONTACT_ACTIVE if active else Theme.WIRE_COLOR
                # Pin circle
                self.create_oval(pin_x - PIN_R, pin_y - PIN_R,
                                  pin_x + PIN_R, pin_y + PIN_R,
                                  fill=color, outline=Theme.BORDER, width=1)
                # Pin label
                self.create_text(pin_x - PIN_R - 4, pin_y,
                                 text=f"I{ch}", fill=Theme.PIN_INPUT if active else Theme.TEXT,
                                 font=("TkFixedFont", 8, "bold"), anchor=tk.E)
                # Short horizontal wire from pin to rail
                self.create_line(pin_x, pin_y, pin_x + PIN_R * 2, pin_y,
                                 fill=color, width=2)

        # --- Right rail (outputs) ---
        rx = canvas_w - RIGHT_RAIL_W + RAIL_W // 2
        self.create_rectangle(rx - RAIL_W // 2, 0, rx + RAIL_W // 2, total_h,
                               fill=Theme.RUNG_RAIL, outline="")
        # Right rail header
        self.create_rectangle(canvas_w - RIGHT_RAIL_W, 0, canvas_w, RUNG_TOP_PAD,
                               fill=Theme.RAIL_RIGHT_BG, outline=Theme.BORDER)
        self.create_text(canvas_w - RIGHT_RAIL_W // 2, RUNG_TOP_PAD // 2,
                         text="OUTPUTS", fill=Theme.PIN_OUTPUT,
                         font=("TkDefaultFont", 7, "bold"))

        # Draw output pin labels on right rail
        if io:
            for ch in sorted(io.outputs.keys()):
                active = io.get_output(ch)
                pin_y = RUNG_TOP_PAD + (ch - 1) * (RUNG_H // 2) + RUNG_H // 4
                pin_x = rx
                color = Theme.COIL_ACTIVE if active else Theme.WIRE_COLOR
                self.create_oval(pin_x - PIN_R, pin_y - PIN_R,
                                  pin_x + PIN_R, pin_y + PIN_R,
                                  fill=color, outline=Theme.BORDER, width=1)
                self.create_text(pin_x + PIN_R + 4, pin_y,
                                 text=f"Q{ch}", fill=Theme.PIN_OUTPUT if active else Theme.TEXT,
                                 font=("TkFixedFont", 8, "bold"), anchor=tk.W)
                self.create_line(pin_x - PIN_R * 2, pin_y, pin_x, pin_y,
                                 fill=color, width=2)

    def _draw_empty_hint(self, w: int, h: int) -> None:
        cx = LEFT_RAIL_W + (w - LEFT_RAIL_W - RIGHT_RAIL_W) // 2
        cy = RUNG_TOP_PAD + RUNG_H // 2
        self.create_text(cx, cy,
                         text="Drag function blocks from the toolbox\nor use the sidebar to add AND / OR / NOT / RS elements.",
                         fill=Theme.SUBTEXT, font=("TkDefaultFont", 10),
                         justify=tk.CENTER)

    def _draw_rung(self, idx: int, elem: LogicElement,
                   io: Optional[PlcIO], y_top: int, canvas_w: int) -> None:
        """Draw one rung: left rail → wires → function block → wires → right rail."""
        mid_y    = y_top + RUNG_H // 2
        selected = (self._selected_rung == idx)
        dragging = (self._drag_rung == idx)

        # Rung highlight
        if selected and not dragging:
            self.create_rectangle(LEFT_RAIL_W, y_top,
                                   canvas_w - RIGHT_RAIL_W, y_top + RUNG_H,
                                   fill=Theme.SELECTED_BG, outline="")
        elif dragging:
            # Ghost effect while dragging
            self.create_rectangle(LEFT_RAIL_W, y_top,
                                   canvas_w - RIGHT_RAIL_W, y_top + RUNG_H,
                                   fill="#e0e8ff", outline=Theme.ACCENT,
                                   width=2, dash=(6, 4))

        # Rung number label
        self.create_text(LEFT_RAIL_W + 6, y_top + 8,
                         text=f"{idx + 1}", fill=Theme.SUBTEXT,
                         font=("TkFixedFont", 8), anchor=tk.NW)

        # ---- Function block (Owen Logic style) ----
        block_area_x = LEFT_RAIL_W
        block_area_w = canvas_w - LEFT_RAIL_W - RIGHT_RAIL_W
        bx = block_area_x + (block_area_w - BLOCK_W) // 2  # Center block horizontally
        by = y_top + (RUNG_H - BLOCK_H) // 2

        # Horizontal wire: left rail to block left side
        self.create_line(block_area_x, mid_y, bx, mid_y,
                         fill=Theme.WIRE_COLOR, width=2)

        # Horizontal wire: block right side to right rail
        self.create_line(bx + BLOCK_W, mid_y, canvas_w - RIGHT_RAIL_W, mid_y,
                         fill=Theme.WIRE_COLOR, width=2)

        # Draw the function block
        self._draw_function_block(elem, io, bx, by, idx, selected)

        # Store layout for hit-testing and drag
        self._rung_layout.append({
            "y_top": y_top,
            "y_bot": y_top + RUNG_H,
            "bx": bx, "by": by,
            "bx2": bx + BLOCK_W, "by2": by + BLOCK_H,
        })

    def _draw_function_block(self, elem: LogicElement, io: Optional[PlcIO],
                              bx: int, by: int, idx: int, selected: bool) -> None:
        """
        Draw an Owen Logic style function block:
        - Rectangle with function name/type at top
        - Input pins on the left side (labeled)
        - Output pins on the right side (labeled)
        - Wires connecting pins to left/right block edges
        """
        gate_type = elem.ld_type()
        inputs_chs = elem.get_inputs()
        outputs_chs = elem.get_outputs()
        n_in  = len(inputs_chs)
        n_out = len(outputs_chs)

        # Active state: check if any output is active
        active_out = False
        if io:
            for ch in outputs_chs:
                if io.get_output(ch):
                    active_out = True
                    break

        active_in = False
        if io:
            for ch in inputs_chs:
                if io.get_input(ch):
                    active_in = True
                    break

        # Block border color
        border_color = Theme.BLOCK_SELECTED if selected else Theme.BLOCK_BORDER
        if active_out:
            border_color = Theme.SUCCESS

        # ---- Block rectangle ----
        self.create_rectangle(bx, by, bx + BLOCK_W, by + BLOCK_H,
                               fill=Theme.BLOCK_BG,
                               outline=border_color, width=2 if selected else 1)

        # ---- Type label at top of block ----
        type_colors = {
            "AND": Theme.ACCENT,
            "OR":  "#7c3aed",
            "NOT": "#d97706",
            "RS":  Theme.DANGER,
        }
        type_color = type_colors.get(gate_type, Theme.TEXT)

        # Top label bar
        self.create_rectangle(bx + 1, by + 1, bx + BLOCK_W - 1, by + 20,
                               fill=type_color, outline="")
        self.create_text(bx + BLOCK_W // 2, by + 10,
                         text=gate_type, fill="#ffffff",
                         font=("TkDefaultFont", 8, "bold"))

        # ---- Input pins (left side of block) ----
        in_pin_ys = self._pin_ys(by + 22, by + BLOCK_H - 4, n_in)
        for i, (ch, pin_y) in enumerate(zip(inputs_chs, in_pin_ys)):
            active = io.get_input(ch) if io else False
            color  = Theme.PIN_INPUT if active else Theme.BORDER

            # Horizontal wire stub from block left edge
            self.create_line(bx - 20, pin_y, bx, pin_y,
                             fill=color, width=2)
            # Pin circle on block left edge
            self.create_oval(bx - PIN_R, pin_y - PIN_R,
                              bx + PIN_R, pin_y + PIN_R,
                              fill=color, outline=Theme.BORDER)
            # Pin label inside block
            label = f"I{ch}" if elem.ld_type() != "RS" else (
                f"S:{ch}" if i == 0 else f"R:{ch}")
            self.create_text(bx + PIN_R + 2, pin_y,
                             text=label, fill=Theme.TEXT,
                             font=("TkFixedFont", 7), anchor=tk.W)

        # ---- Output pins (right side of block) ----
        out_pin_ys = self._pin_ys(by + 22, by + BLOCK_H - 4, n_out)
        for i, (ch, pin_y) in enumerate(zip(outputs_chs, out_pin_ys)):
            active = io.get_output(ch) if io else False
            color  = Theme.PIN_OUTPUT if active else Theme.BORDER

            # Horizontal wire stub to block right edge
            self.create_line(bx + BLOCK_W, pin_y, bx + BLOCK_W + 20, pin_y,
                             fill=color, width=2)
            # Pin circle on block right edge
            self.create_oval(bx + BLOCK_W - PIN_R, pin_y - PIN_R,
                              bx + BLOCK_W + PIN_R, pin_y + PIN_R,
                              fill=color, outline=Theme.BORDER)
            # Pin label inside block (right-aligned)
            label = f"Q{ch}"
            self.create_text(bx + BLOCK_W - PIN_R - 2, pin_y,
                             text=label, fill=Theme.TEXT,
                             font=("TkFixedFont", 7), anchor=tk.E)

        # ---- Active state indicators ----
        if active_out:
            # Energized glow effect
            self.create_rectangle(bx + 2, by + 2, bx + BLOCK_W - 2, by + BLOCK_H - 2,
                                   fill="", outline=Theme.SUCCESS, width=1)
            self.create_text(bx + BLOCK_W // 2, by + BLOCK_H - 8,
                             text="● ACTIVE", fill=Theme.SUCCESS,
                             font=("TkFixedFont", 6, "bold"))

    @staticmethod
    def _pin_ys(top: int, bot: int, count: int) -> List[int]:
        """Evenly space `count` pin y-positions between top and bot."""
        if count == 0:
            return []
        if count == 1:
            return [(top + bot) // 2]
        step = (bot - top) // (count + 1)
        return [top + step * (i + 1) for i in range(count)]

    def _draw_drag_indicator(self, canvas_w: int) -> None:
        """Draw a blue drop-target line while dragging a rung."""
        y = self._drag_ghost_y
        if y is not None:
            self.create_line(LEFT_RAIL_W, y, canvas_w - RIGHT_RAIL_W, y,
                             fill=Theme.ACCENT, width=3, dash=(8, 4))
            self.create_oval(LEFT_RAIL_W - 6, y - 6, LEFT_RAIL_W + 6, y + 6,
                             fill=Theme.ACCENT, outline="")
            self.create_oval(canvas_w - RIGHT_RAIL_W - 6, y - 6,
                              canvas_w - RIGHT_RAIL_W + 6, y + 6,
                             fill=Theme.ACCENT, outline="")

    # ----------------------------------------------------------
    # Mouse event handlers
    # ----------------------------------------------------------

    def _on_press(self, event: Any) -> None:
        y = self.canvasy(event.y)
        for i, layout in enumerate(self._rung_layout):
            if layout["y_top"] <= y <= layout["y_bot"]:
                self._drag_rung = i
                self._drag_start_y = y
                self._drag_ghost_y = None
                break

    def _on_drag(self, event: Any) -> None:
        if self._drag_rung is None:
            return
        y = self.canvasy(event.y)
        if abs(y - (self._drag_start_y or y)) > 5:
            # Determine drop position
            self._drag_ghost_y = y
            self.redraw()

    def _on_release(self, event: Any) -> None:
        if self._drag_rung is None:
            return

        y = self.canvasy(event.y)

        if self._drag_ghost_y is not None:
            # Find target rung index from drop y position
            prog = self._app.manager.current_program
            if prog:
                target_idx = self._y_to_rung_index(y)
                if target_idx is not None and target_idx != self._drag_rung:
                    prog.move_element(self._drag_rung, target_idx)
                    self._selected_rung = target_idx
                    self._app.on_rung_select(target_idx)
                    self._set_status_after_drop(self._drag_rung, target_idx)

        self._drag_rung = None
        self._drag_start_y = None
        self._drag_ghost_y = None
        self.redraw()

    def _y_to_rung_index(self, y: float) -> Optional[int]:
        """Return the rung index at a given canvas y position."""
        n = len(self._rung_layout)
        if n == 0:
            return None
        for i, layout in enumerate(self._rung_layout):
            mid = (layout["y_top"] + layout["y_bot"]) / 2
            if y <= mid:
                return i
        return n - 1

    def _set_status_after_drop(self, from_idx: int, to_idx: int) -> None:
        self._app._set_status(f"Moved rung {from_idx + 1} → position {to_idx + 1}.")

    def _on_click(self, event: Any) -> None:
        # Only handle click if not dragging
        if self._drag_ghost_y is not None:
            return

        y = self.canvasy(event.y)
        for i, layout in enumerate(self._rung_layout):
            if layout["y_top"] <= y <= layout["y_bot"]:
                self._selected_rung = i
                self._app.on_rung_select(i)
                self.redraw()
                return

        self._selected_rung = None
        self._app.on_rung_select(None)
        self.redraw()


# ============================================================
# Toolbox panel — drag-source for function blocks
# ============================================================

class ToolboxPanel(tk.Frame):
    """
    Owen Logic style toolbox panel.
    Shows available function block types that can be clicked to add to the canvas.
    """

    FUNCTIONS = [
        ("AND", "Series contacts\n(I1 AND I2 → Q)", Theme.ACCENT),
        ("OR",  "Parallel contacts\n(I1 OR I2 → Q)",  "#7c3aed"),
        ("NOT", "Inverted contact\n(NOT I → Q)",       "#d97706"),
        ("RS",  "Set/Reset latch\n(S/R → Q)",          Theme.DANGER),
    ]

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=Theme.TOOLBOX_BG, **kwargs)
        self._app = app
        self._build()

    def _build(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=Theme.HEADERBAR_BG)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="FUNCTION BLOCKS",
                 bg=Theme.HEADERBAR_BG, fg=Theme.TOOLBOX_FG,
                 font=("TkDefaultFont", 8, "bold"),
                 padx=8, pady=6).pack(side=tk.LEFT)

        # Help text
        tk.Label(self, text="Click to add to program:",
                 bg=Theme.TOOLBOX_BG, fg="#aaaaaa",
                 font=("TkDefaultFont", 7),
                 padx=6, pady=2).pack(anchor=tk.W)

        # Function block buttons
        for (gate, desc, color) in self.FUNCTIONS:
            self._build_block_btn(gate, desc, color)

        # Separator
        tk.Frame(self, bg=Theme.BORDER, height=1).pack(fill=tk.X, pady=8)

        # Remove / clear actions
        tk.Label(self, text="ACTIONS",
                 bg=Theme.TOOLBOX_BG, fg="#aaaaaa",
                 font=("TkDefaultFont", 7, "bold"),
                 padx=6).pack(anchor=tk.W)

        self._remove_btn = self._action_btn("✕ Remove Selected", self._app._remove_element,
                                             danger=True)
        self._remove_btn.pack(fill=tk.X, padx=6, pady=2)

        self._action_btn("⬆ Move Up",   self._app._move_selected_up).pack(
            fill=tk.X, padx=6, pady=2)
        self._action_btn("⬇ Move Down", self._app._move_selected_down).pack(
            fill=tk.X, padx=6, pady=2)
        self._action_btn("🗑 Clear All", self._app._clear_program,
                          danger=True).pack(fill=tk.X, padx=6, pady=2)

    def _build_block_btn(self, gate: str, desc: str, color: str) -> None:
        frame = tk.Frame(self, bg=Theme.TOOLBOX_BTN_BG,
                         highlightthickness=1, highlightbackground=color)
        frame.pack(fill=tk.X, padx=6, pady=4)

        top = tk.Frame(frame, bg=color)
        top.pack(fill=tk.X)
        tk.Label(top, text=gate, bg=color, fg="#ffffff",
                 font=("TkDefaultFont", 11, "bold"),
                 padx=8, pady=4).pack(side=tk.LEFT)

        tk.Label(frame, text=desc,
                 bg=Theme.TOOLBOX_BTN_BG, fg="#cccccc",
                 font=("TkDefaultFont", 7),
                 justify=tk.LEFT, padx=6, pady=4,
                 anchor=tk.W).pack(fill=tk.X)

        tk.Button(frame, text=f"+ Add {gate}",
                  bg=color, fg="#ffffff",
                  relief=tk.FLAT, padx=6, pady=3,
                  font=("TkDefaultFont", 8, "bold"),
                  activebackground=Theme.ACCENT_HOVER,
                  activeforeground="#ffffff",
                  cursor="hand2",
                  command=lambda g=gate: self._app._add_gate(g)).pack(
            fill=tk.X, padx=6, pady=(0, 6))

    def _action_btn(self, text: str, cmd, danger: bool = False) -> tk.Button:
        bg = "#8b1a1a" if danger else Theme.TOOLBOX_BTN_BG
        fg = "#ffaaaa" if danger else "#cccccc"
        return tk.Button(self, text=text, command=cmd,
                         bg=bg, fg=fg,
                         relief=tk.FLAT, padx=8, pady=4,
                         font=("TkDefaultFont", 8),
                         activebackground=Theme.ACCENT,
                         activeforeground="#ffffff",
                         cursor="hand2")


# ============================================================
# GTK-style dialogs
# ============================================================

class _GtkDialog(tk.Toplevel):
    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.configure(bg=Theme.BG)

        header = tk.Frame(self, bg=Theme.HEADERBAR_BG, pady=8)
        header.pack(fill=tk.X)
        tk.Label(header, text=title, font=("TkDefaultFont", 11, "bold"),
                 bg=Theme.HEADERBAR_BG, fg=Theme.HEADERBAR_FG).pack(padx=12)

        self._content = tk.Frame(self, bg=Theme.BG, padx=16, pady=12)
        self._content.pack(fill=tk.BOTH, expand=True)

        self._btn_row = tk.Frame(self, bg=Theme.BG, pady=8)
        self._btn_row.pack(fill=tk.X, padx=16)

        self.bind("<Escape>", lambda e: self.destroy())

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
    def __init__(self, parent, gate_type: str, max_inputs: int, max_outputs: int):
        super().__init__(parent, f"Add {gate_type} Element")
        self.result: Optional[LogicElement] = None
        self.gate_type = gate_type
        self._entries: Dict[str, tk.StringVar] = {}

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
# Main Application Window — GTK/GNOME style with Owen Logic LD
# ============================================================

class FreePLCGtkApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.manager = RelayManager()
        self._update_job: Optional[str] = None

        self.title("FreePLC")
        self.geometry("1280x760")
        self.minsize(960, 600)
        self.configure(bg=Theme.BG)

        self._build_ui()
        self._refresh_relay_list()
        self._start_io_refresh()

    def _build_ui(self) -> None:
        self._build_headerbar()
        main = tk.Frame(self, bg=Theme.BG)
        main.pack(fill=tk.BOTH, expand=True)
        self._build_toolbox(main)      # Left: dark toolbox panel
        self._build_ld_area(main)      # Center: LD canvas
        self._build_sidebar(main)      # Right: relay/IO panel
        self._build_statusbar()

    def _build_headerbar(self) -> None:
        bar = tk.Frame(self, bg=Theme.HEADERBAR_BG, height=46)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        left = tk.Frame(bar, bg=Theme.HEADERBAR_BG)
        left.pack(side=tk.LEFT, padx=12, pady=6)

        tk.Label(left, text="FreePLC", font=("TkDefaultFont", 13, "bold"),
                 bg=Theme.HEADERBAR_BG, fg=Theme.HEADERBAR_FG).pack(side=tk.LEFT)

        self._header_relay_lbl = tk.Label(left, text="",
                                          font=("TkDefaultFont", 11),
                                          bg=Theme.HEADERBAR_BG, fg="#b0b0b0")
        self._header_relay_lbl.pack(side=tk.LEFT, padx=(8, 0))

        right = tk.Frame(bar, bg=Theme.HEADERBAR_BG)
        right.pack(side=tk.RIGHT, padx=12, pady=6)

        self._stop_btn = self._hdr_btn(right, "⏹  Stop",  self._stop_program,  enabled=False)
        self._stop_btn.pack(side=tk.RIGHT, padx=4)

        self._run_btn = self._hdr_btn(right, "▶  Run",   self._start_program, enabled=True)
        self._run_btn.pack(side=tk.RIGHT, padx=4)

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

    def _build_toolbox(self, parent: tk.Frame) -> None:
        """Left dark toolbox panel (Owen Logic style function block palette)."""
        toolbox_outer = tk.Frame(parent, bg=Theme.TOOLBOX_BG, width=190)
        toolbox_outer.pack(side=tk.LEFT, fill=tk.Y)
        toolbox_outer.pack_propagate(False)

        # Scrollable toolbox
        vsb = tk.Scrollbar(toolbox_outer, orient=tk.VERTICAL,
                           bg=Theme.TOOLBOX_BG, troughcolor=Theme.TOOLBOX_BG)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        inner_canvas = tk.Canvas(toolbox_outer, bg=Theme.TOOLBOX_BG,
                                  yscrollcommand=vsb.set, highlightthickness=0)
        inner_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=inner_canvas.yview)

        self._toolbox = ToolboxPanel(inner_canvas, self)
        inner_canvas.create_window((0, 0), window=self._toolbox, anchor=tk.NW)
        self._toolbox.bind("<Configure>",
                           lambda e: inner_canvas.configure(
                               scrollregion=inner_canvas.bbox("all")))

    def _build_sidebar(self, parent: tk.Frame) -> None:
        """Right sidebar: relay selector and I/O status."""
        sidebar = tk.Frame(parent, bg=Theme.SIDEBAR_BG, width=210)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)

        self._sidebar_section(sidebar, "Relays")

        self._relay_listbox = tk.Listbox(
            sidebar, font=("TkDefaultFont", 10),
            selectmode=tk.SINGLE, height=5,
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
        btn_row.pack(fill=tk.X, padx=8, pady=(0, 6))
        self._sidebar_btn(btn_row, "＋ New",    self._create_relay).pack(side=tk.LEFT)
        self._sidebar_btn(btn_row, "✓ Select",  self._select_relay).pack(side=tk.LEFT, padx=(4, 0))

        self._relay_info = tk.Label(sidebar, text="",
                                    bg=Theme.SIDEBAR_BG, fg=Theme.SUBTEXT,
                                    font=("TkFixedFont", 8),
                                    justify=tk.LEFT, anchor=tk.W, padx=8)
        self._relay_info.pack(fill=tk.X)

        tk.Frame(sidebar, bg=Theme.BORDER, height=1).pack(fill=tk.X, padx=8, pady=6)

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
        """Center area: Ladder Diagram canvas + manual I/O strip."""
        right = tk.Frame(parent, bg=Theme.BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ld_frame = tk.Frame(right, bg=Theme.BG)
        ld_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        # Canvas label
        lbl_row = tk.Frame(ld_frame, bg=Theme.BG)
        lbl_row.pack(fill=tk.X, pady=(0, 2))
        tk.Label(lbl_row, text="Ladder Diagram",
                 bg=Theme.BG, fg=Theme.SUBTEXT,
                 font=("TkDefaultFont", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(lbl_row,
                 text="← inputs on left rail  |  outputs on right rail →  |  drag rungs to reorder",
                 bg=Theme.BG, fg="#aaaaaa",
                 font=("TkDefaultFont", 7)).pack(side=tk.LEFT, padx=8)

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

        # Manual I/O strip
        io_strip = tk.LabelFrame(right, text="Manual Input Control",
                                 bg=Theme.BG, fg=Theme.SUBTEXT,
                                 font=("TkDefaultFont", 8, "bold"),
                                 relief=tk.FLAT,
                                 highlightthickness=1,
                                 highlightbackground=Theme.BORDER)
        io_strip.pack(fill=tk.X, padx=4, pady=(0, 4))

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
    # Relay management
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
        pass

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
    # Element management
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
            # Select the newly added element
            elements = prog.get_elements()
            new_idx = len(elements) - 1
            self._ld_canvas.select_rung(new_idx)
            self._ld_canvas.redraw()
            self._set_status(f"{gate_type} element added (rung {new_idx + 1}).")

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

    def _move_selected_up(self) -> None:
        idx = self._ld_canvas.selected_rung
        prog = self.manager.current_program
        if idx is None or not prog:
            self._set_status("Select a rung first.", error=True)
            return
        if idx == 0:
            self._set_status("Already at top.", error=True)
            return
        prog.move_element(idx, idx - 1)
        self._ld_canvas.select_rung(idx - 1)
        self._ld_canvas.redraw()
        self._set_status(f"Moved rung {idx + 1} → position {idx}.")

    def _move_selected_down(self) -> None:
        idx = self._ld_canvas.selected_rung
        prog = self.manager.current_program
        if idx is None or not prog:
            self._set_status("Select a rung first.", error=True)
            return
        elements = prog.get_elements()
        if idx >= len(elements) - 1:
            self._set_status("Already at bottom.", error=True)
            return
        prog.move_element(idx, idx + 1)
        self._ld_canvas.select_rung(idx + 1)
        self._ld_canvas.redraw()
        self._set_status(f"Moved rung {idx + 1} → position {idx + 2}.")

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
    # Manual I/O controls
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
    # I/O Panel refresh
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

        self._io_section("Inputs", self._io_inner)
        for ch in sorted(relay.inputs.keys()):
            self._io_row(self._io_inner, f"I{ch}", relay.inputs[ch])

        self._io_section("Outputs", self._io_inner)
        for ch in sorted(relay.outputs.keys()):
            self._io_row(self._io_inner, f"Q{ch}", relay.outputs[ch])

        self._io_inner.update_idletasks()
        self._io_canvas.configure(scrollregion=self._io_canvas.bbox("all"))

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
    # Periodic refresh
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
                ts = time.strftime("%H:%M:%S")
                self._scan_lbl.config(text=f"scan  {ts}")

    def _set_status(self, msg: str, error: bool = False) -> None:
        self._status_var.set(msg)

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
