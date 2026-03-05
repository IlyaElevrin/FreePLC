#!/usr/bin/env python3
"""
FreePLC - Programmable Relay Simulator with GUI
A Python/tkinter-based GUI for programming and simulating PLC relays.
Replaces the ncurses console UI with a proper windowed interface.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
from typing import Dict, List, Optional, Any


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
        return f"AND  I{self.input1} & I{self.input2} -> Q{self.output}"


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
        return f"OR   I{self.input1} | I{self.input2} -> Q{self.output}"


class NotGate(LogicElement):
    def __init__(self, in_ch: int, out: int):
        self.input = in_ch
        self.output = out

    def evaluate(self, io: PlcIO) -> bool:
        result = not io.get_input(self.input)
        io.set_output(self.output, result)
        return result

    def __str__(self) -> str:
        return f"NOT  I{self.input} -> Q{self.output}"


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
        # Both false → state unchanged (latch behaviour)
        io.set_output(self.output, self._state)
        return self._state

    def __str__(self) -> str:
        return f"RS   I{self.set_input}(S) / I{self.reset_input}(R) -> Q{self.output}"


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
            time.sleep(0.2)  # 200ms scan cycle

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
        # Create a default relay
        self.create_relay("test", 6, 6)
        self.select_relay("test")

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
# GUI Dialogs
# ============================================================

class GateDialog(tk.Toplevel):
    """Dialog for adding a logic gate element."""

    def __init__(self, parent, gate_type: str, max_inputs: int, max_outputs: int):
        super().__init__(parent)
        self.result: Optional[LogicElement] = None
        self.gate_type = gate_type
        self.title(f"Add {gate_type} Gate")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)

        pad = {"padx": 8, "pady": 4}

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=f"Configure {gate_type} Gate",
                  font=("TkDefaultFont", 11, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 10))

        self._entries: Dict[str, tk.StringVar] = {}

        if gate_type in ("AND", "OR"):
            fields = [("Input 1 channel:", "in1"), ("Input 2 channel:", "in2"),
                      ("Output channel:", "out")]
        elif gate_type == "NOT":
            fields = [("Input channel:", "in1"), ("Output channel:", "out")]
        else:  # RS
            fields = [("SET input channel:", "set"), ("RESET input channel:", "reset"),
                      ("Output channel:", "out")]

        for row, (label, key) in enumerate(fields, start=1):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky=tk.W, **pad)
            var = tk.StringVar()
            self._entries[key] = var
            ttk.Entry(frame, textvariable=var, width=8).grid(
                row=row, column=1, sticky=tk.W, **pad)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(fields) + 2, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btn_frame, text="Add", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())

        # Center dialog over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
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
                in1 = self._get_int("in1")
                in2 = self._get_int("in2")
                out = self._get_int("out")
                if in1 and in2 and out:
                    self.result = AndGate(in1, in2, out)
            elif self.gate_type == "OR":
                in1 = self._get_int("in1")
                in2 = self._get_int("in2")
                out = self._get_int("out")
                if in1 and in2 and out:
                    self.result = OrGate(in1, in2, out)
            elif self.gate_type == "NOT":
                in1 = self._get_int("in1")
                out = self._get_int("out")
                if in1 and out:
                    self.result = NotGate(in1, out)
            elif self.gate_type == "RS":
                set_ch = self._get_int("set")
                reset_ch = self._get_int("reset")
                out = self._get_int("out")
                if set_ch and reset_ch and out:
                    self.result = RSTrigger(set_ch, reset_ch, out)

            if self.result is None:
                messagebox.showerror("Invalid Input",
                                     "All channel numbers must be positive integers.",
                                     parent=self)
                return
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return

        self.destroy()


class CreateRelayDialog(tk.Toplevel):
    """Dialog for creating a new relay."""

    def __init__(self, parent):
        super().__init__(parent)
        self.result: Optional[tuple] = None  # (name, inputs, outputs)
        self.title("Create New Relay")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Create New Relay",
                  font=("TkDefaultFont", 11, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 10))

        pad = {"padx": 8, "pady": 4}

        ttk.Label(frame, text="Relay name:").grid(row=1, column=0, sticky=tk.W, **pad)
        self._name = tk.StringVar(value="relay1")
        ttk.Entry(frame, textvariable=self._name, width=16).grid(
            row=1, column=1, sticky=tk.W, **pad)

        ttk.Label(frame, text="Number of inputs:").grid(row=2, column=0, sticky=tk.W, **pad)
        self._inputs = tk.StringVar(value="6")
        ttk.Entry(frame, textvariable=self._inputs, width=8).grid(
            row=2, column=1, sticky=tk.W, **pad)

        ttk.Label(frame, text="Number of outputs:").grid(row=3, column=0, sticky=tk.W, **pad)
        self._outputs = tk.StringVar(value="6")
        ttk.Entry(frame, textvariable=self._outputs, width=8).grid(
            row=3, column=1, sticky=tk.W, **pad)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btn_frame, text="Create", command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())

        # Center over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
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
# Main Application Window
# ============================================================

class FreePLCApp(tk.Tk):
    """Main FreePLC GUI window."""

    # Colours for ON/OFF states
    COLOR_ON = "#2ecc71"
    COLOR_OFF = "#e74c3c"
    COLOR_ON_FG = "#ffffff"
    COLOR_OFF_FG = "#ffffff"
    COLOR_TITLE_BG = "#2c3e50"
    COLOR_TITLE_FG = "#ecf0f1"
    COLOR_STATUS_BG = "#27ae60"
    COLOR_STATUS_FG = "#ffffff"
    COLOR_STATUS_ERR_BG = "#c0392b"

    def __init__(self):
        super().__init__()
        self.manager = RelayManager()
        self._update_job: Optional[str] = None

        self.title("FreePLC - Programmable Relay Simulator")
        self.geometry("900x620")
        self.minsize(800, 500)

        self._build_ui()
        self._refresh_relay_selector()
        self._refresh_program_list()
        self._refresh_io_panel()
        self._start_io_refresh()

    # ----------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------

    def _build_ui(self) -> None:
        # ---- Title bar ----
        title_bar = tk.Frame(self, bg=self.COLOR_TITLE_BG, pady=8)
        title_bar.pack(fill=tk.X)
        tk.Label(title_bar, text="FreePLC  —  Programmable Relay Simulator",
                 font=("TkDefaultFont", 14, "bold"),
                 bg=self.COLOR_TITLE_BG, fg=self.COLOR_TITLE_FG).pack(side=tk.LEFT, padx=12)
        tk.Label(title_bar, text="v2.0",
                 font=("TkDefaultFont", 10),
                 bg=self.COLOR_TITLE_BG, fg="#95a5a6").pack(side=tk.RIGHT, padx=12)

        # ---- Status bar ----
        self._status_var = tk.StringVar(
            value="Welcome to FreePLC — select a relay and start programming!")
        self._status_bar = tk.Label(self, textvariable=self._status_var,
                                    bg=self.COLOR_STATUS_BG, fg=self.COLOR_STATUS_FG,
                                    anchor=tk.W, padx=10, pady=4,
                                    font=("TkDefaultFont", 9))
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # ---- Main content (left panel + right I/O panel) ----
        content = tk.Frame(self)
        content.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Right I/O panel
        io_frame = ttk.LabelFrame(content, text="I/O Status", padding=8)
        io_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 8), pady=8)
        io_frame.pack_propagate(False)
        io_frame.configure(width=220)
        self._build_io_panel(io_frame)

        # Left panel (notebook with tabs)
        left_panel = ttk.Frame(content)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 4), pady=8)
        self._build_left_panel(left_panel)

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        # ---- Tab 1: Relays ----
        relay_tab = ttk.Frame(notebook, padding=8)
        notebook.add(relay_tab, text="  Relays  ")
        self._build_relay_tab(relay_tab)

        # ---- Tab 2: LD Program ----
        prog_tab = ttk.Frame(notebook, padding=8)
        notebook.add(prog_tab, text="  LD Program  ")
        self._build_program_tab(prog_tab)

        # ---- Tab 3: Run / Control ----
        run_tab = ttk.Frame(notebook, padding=8)
        notebook.add(run_tab, text="  Run / Control  ")
        self._build_run_tab(run_tab)

    # ---- Relay Tab ----

    def _build_relay_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Available Relays",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor=tk.W, pady=(0, 6))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._relay_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                         font=("TkFixedFont", 10),
                                         selectmode=tk.SINGLE, height=8,
                                         activestyle="dotbox")
        self._relay_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._relay_listbox.yview)
        self._relay_listbox.bind("<<ListboxSelect>>", self._on_relay_select)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_frame, text="Create Relay", command=self._create_relay).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Select Relay", command=self._select_relay).pack(
            side=tk.LEFT, padx=2)

        # Current relay info
        info_frame = ttk.LabelFrame(parent, text="Current Relay", padding=8)
        info_frame.pack(fill=tk.X, pady=(10, 0))
        self._relay_info_var = tk.StringVar(value="(none selected)")
        ttk.Label(info_frame, textvariable=self._relay_info_var,
                  font=("TkFixedFont", 9)).pack(anchor=tk.W)

    # ---- LD Program Tab ----

    def _build_program_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Logic Diagram Elements",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor=tk.W, pady=(0, 6))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._prog_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                        font=("TkFixedFont", 10),
                                        selectmode=tk.SINGLE, height=10,
                                        activestyle="dotbox")
        self._prog_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._prog_listbox.yview)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(6, 0))

        ttk.Label(btn_frame, text="Add:").pack(side=tk.LEFT, padx=(0, 4))
        for gate in ("AND", "OR", "NOT", "RS"):
            ttk.Button(btn_frame, text=gate,
                       command=lambda g=gate: self._add_gate(g)).pack(
                side=tk.LEFT, padx=2)

        btn_frame2 = ttk.Frame(parent)
        btn_frame2.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_frame2, text="Remove Selected",
                   command=self._remove_element).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame2, text="Clear All",
                   command=self._clear_program).pack(side=tk.LEFT, padx=2)

    # ---- Run Tab ----

    def _build_run_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Program Control",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor=tk.W, pady=(0, 10))

        ctrl_frame = ttk.Frame(parent)
        ctrl_frame.pack(anchor=tk.W)

        self._run_btn = ttk.Button(ctrl_frame, text="▶  Start Program",
                                   command=self._start_program)
        self._run_btn.pack(side=tk.LEFT, padx=4, pady=4)

        self._stop_btn = ttk.Button(ctrl_frame, text="■  Stop Program",
                                    command=self._stop_program, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=4, pady=4)

        # Run status indicator
        status_frame = ttk.LabelFrame(parent, text="Status", padding=8)
        status_frame.pack(fill=tk.X, pady=(12, 0))

        self._run_status_label = tk.Label(status_frame, text="STOPPED",
                                          font=("TkDefaultFont", 16, "bold"),
                                          bg=self.COLOR_OFF, fg=self.COLOR_OFF_FG,
                                          padx=16, pady=8)
        self._run_status_label.pack(anchor=tk.W)

        # Manual I/O section
        sep = ttk.Separator(parent, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, pady=(16, 8))

        ttk.Label(parent, text="Manual Input Control",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor=tk.W, pady=(0, 6))

        self._manual_io_frame = ttk.Frame(parent)
        self._manual_io_frame.pack(fill=tk.X)

    # ---- I/O Panel (right side) ----

    def _build_io_panel(self, parent) -> None:
        self._io_relay_label = ttk.Label(parent, text="No relay selected",
                                         font=("TkDefaultFont", 9, "bold"))
        self._io_relay_label.pack(anchor=tk.W, pady=(0, 4))

        self._io_running_label = tk.Label(parent, text="STOPPED",
                                          bg=self.COLOR_OFF, fg=self.COLOR_OFF_FG,
                                          font=("TkDefaultFont", 9, "bold"),
                                          padx=6, pady=2)
        self._io_running_label.pack(anchor=tk.W, pady=(0, 6))

        # Scrollable canvas for I/O indicators
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._io_canvas = tk.Canvas(canvas_frame, yscrollcommand=vsb.set,
                                    bg="#f8f9fa", highlightthickness=0)
        self._io_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=self._io_canvas.yview)

        self._io_inner = tk.Frame(self._io_canvas, bg="#f8f9fa")
        self._io_canvas.create_window((0, 0), window=self._io_inner, anchor=tk.NW)
        self._io_inner.bind("<Configure>",
                            lambda e: self._io_canvas.configure(
                                scrollregion=self._io_canvas.bbox("all")))

    # ----------------------------------------------------------
    # Relay tab actions
    # ----------------------------------------------------------

    def _refresh_relay_selector(self) -> None:
        self._relay_listbox.delete(0, tk.END)
        names = self.manager.get_relay_names()
        current = self.manager.current_relay
        for name in names:
            suffix = " ← active" if (current and current.name == name) else ""
            self._relay_listbox.insert(tk.END, f"  {name}{suffix}")
        # Update info label
        if current:
            inp_count = len(current.inputs)
            out_count = len(current.outputs)
            self._relay_info_var.set(
                f"Name: {current.name}\n"
                f"Inputs: {inp_count}   Outputs: {out_count}"
            )
        else:
            self._relay_info_var.set("(none selected)")

    def _on_relay_select(self, event: Any) -> None:
        # Single-click highlight only, double-click or button to select
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
            self._refresh_relay_selector()
            self._refresh_program_list()
            self._refresh_io_panel()
            self._rebuild_manual_io()
            self._set_status(f"Relay '{name}' created and selected ({inp} in, {out} out).")

    def _select_relay(self) -> None:
        sel = self._relay_listbox.curselection()
        if not sel:
            self._set_status("Please select a relay from the list first.", error=True)
            return
        idx = sel[0]
        names = self.manager.get_relay_names()
        if idx < len(names):
            name = names[idx]
            # Stop current program before switching
            if self.manager.current_program and self.manager.current_program.is_running():
                self.manager.current_program.stop()
            self.manager.select_relay(name)
            self._refresh_relay_selector()
            self._refresh_program_list()
            self._refresh_io_panel()
            self._rebuild_manual_io()
            self._set_status(f"Relay '{name}' selected.")

    # ----------------------------------------------------------
    # LD Program tab actions
    # ----------------------------------------------------------

    def _refresh_program_list(self) -> None:
        self._prog_listbox.delete(0, tk.END)
        prog = self.manager.current_program
        if not prog:
            self._prog_listbox.insert(tk.END, "  (no relay selected)")
            return
        elements = prog.get_elements()
        if not elements:
            self._prog_listbox.insert(tk.END, "  (program is empty — add elements below)")
            return
        for i, elem in enumerate(elements, start=1):
            self._prog_listbox.insert(tk.END, f"  {i:2d}. {elem}")

    def _add_gate(self, gate_type: str) -> None:
        relay = self.manager.current_relay
        prog = self.manager.current_program
        if not relay or not prog:
            self._set_status("No relay selected — please select a relay first.", error=True)
            return
        max_in = len(relay.inputs)
        max_out = len(relay.outputs)
        dlg = GateDialog(self, gate_type, max_in, max_out)
        self.wait_window(dlg)
        if dlg.result:
            prog.add_element(dlg.result)
            self._refresh_program_list()
            self._set_status(f"{gate_type} gate added to program.")

    def _remove_element(self) -> None:
        sel = self._prog_listbox.curselection()
        if not sel:
            self._set_status("Select an element to remove.", error=True)
            return
        prog = self.manager.current_program
        if not prog:
            return
        idx = sel[0]
        if idx < len(prog.get_elements()):
            prog.remove_element(idx)
            self._refresh_program_list()
            self._set_status(f"Element {idx + 1} removed.")

    def _clear_program(self) -> None:
        prog = self.manager.current_program
        if not prog:
            return
        if messagebox.askyesno("Confirm", "Clear entire program?", parent=self):
            prog.clear_elements()
            self._refresh_program_list()
            self._set_status("Program cleared.")

    # ----------------------------------------------------------
    # Run tab actions
    # ----------------------------------------------------------

    def _start_program(self) -> None:
        prog = self.manager.current_program
        if not prog:
            self._set_status("No relay selected.", error=True)
            return
        if not prog.get_elements():
            self._set_status("Program is empty — add logic elements first.", error=True)
            return
        if prog.is_running():
            return
        prog.start()
        self._run_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._run_status_label.config(text="RUNNING", bg=self.COLOR_ON)
        self._io_running_label.config(text="RUNNING", bg=self.COLOR_ON)
        self._set_status("Program started.")

    def _stop_program(self) -> None:
        prog = self.manager.current_program
        if prog and prog.is_running():
            prog.stop()
        self._run_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._run_status_label.config(text="STOPPED", bg=self.COLOR_OFF)
        self._io_running_label.config(text="STOPPED", bg=self.COLOR_OFF)
        self._set_status("Program stopped.")

    # ----------------------------------------------------------
    # Manual I/O controls (in Run tab)
    # ----------------------------------------------------------

    def _rebuild_manual_io(self) -> None:
        """Rebuild the manual input toggle buttons for the current relay."""
        for widget in self._manual_io_frame.winfo_children():
            widget.destroy()

        relay = self.manager.current_relay
        if not relay:
            ttk.Label(self._manual_io_frame, text="(no relay selected)").pack(anchor=tk.W)
            return

        # Create a toggle button for each input channel
        self._input_vars: Dict[int, tk.BooleanVar] = {}
        row_frame = None
        for i, (ch, val) in enumerate(sorted(relay.inputs.items())):
            if i % 3 == 0:
                row_frame = ttk.Frame(self._manual_io_frame)
                row_frame.pack(fill=tk.X, pady=2)
            var = tk.BooleanVar(value=val)
            self._input_vars[ch] = var
            btn = tk.Checkbutton(
                row_frame,
                text=f"I{ch}",
                variable=var,
                indicatoron=False,
                font=("TkFixedFont", 9),
                bg=self.COLOR_OFF, fg=self.COLOR_OFF_FG,
                selectcolor=self.COLOR_ON,
                activebackground=self.COLOR_ON,
                padx=8, pady=4,
                command=lambda c=ch, v=var: self._toggle_input(c, v)
            )
            btn.pack(side=tk.LEFT, padx=3)

    def _toggle_input(self, channel: int, var: tk.BooleanVar) -> None:
        relay = self.manager.current_relay
        prog = self.manager.current_program
        if not relay:
            return
        val = var.get()
        relay.set_input(channel, val)
        # If program is running, execute one cycle immediately
        if prog and prog.is_running():
            prog.execute()
        self._refresh_io_panel()
        self._set_status(f"Input I{channel} set to {'ON' if val else 'OFF'}")

    # ----------------------------------------------------------
    # I/O Panel refresh
    # ----------------------------------------------------------

    def _refresh_io_panel(self) -> None:
        # Clear old widgets
        for widget in self._io_inner.winfo_children():
            widget.destroy()

        relay = self.manager.current_relay
        prog = self.manager.current_program

        if not relay:
            tk.Label(self._io_inner, text="No relay selected",
                     bg="#f8f9fa", font=("TkDefaultFont", 9)).pack(pady=10)
            return

        # Update relay name label
        self._io_relay_label.config(text=f"Relay: {relay.name}")

        # Running status
        running = prog and prog.is_running()
        status_text = "RUNNING" if running else "STOPPED"
        status_bg = self.COLOR_ON if running else self.COLOR_OFF
        self._io_running_label.config(text=status_text, bg=status_bg)

        row = 0

        # ---- Inputs ----
        tk.Label(self._io_inner, text="Inputs",
                 font=("TkDefaultFont", 9, "bold", "underline"),
                 bg="#f8f9fa").grid(row=row, column=0, columnspan=2,
                                   sticky=tk.W, padx=4, pady=(4, 2))
        row += 1

        for ch in sorted(relay.inputs.keys()):
            val = relay.inputs[ch]
            color = self.COLOR_ON if val else self.COLOR_OFF
            tk.Label(self._io_inner, text=f"I{ch}",
                     font=("TkFixedFont", 9),
                     bg="#f8f9fa").grid(row=row, column=0, sticky=tk.W, padx=(8, 2))
            tk.Label(self._io_inner, text="ON " if val else "OFF",
                     font=("TkFixedFont", 9, "bold"),
                     bg=color, fg="white",
                     padx=4, pady=1,
                     width=4).grid(row=row, column=1, sticky=tk.W, padx=2, pady=1)
            row += 1

        # ---- Outputs ----
        tk.Label(self._io_inner, text="Outputs",
                 font=("TkDefaultFont", 9, "bold", "underline"),
                 bg="#f8f9fa").grid(row=row, column=0, columnspan=2,
                                   sticky=tk.W, padx=4, pady=(8, 2))
        row += 1

        for ch in sorted(relay.outputs.keys()):
            val = relay.outputs[ch]
            color = self.COLOR_ON if val else self.COLOR_OFF
            tk.Label(self._io_inner, text=f"Q{ch}",
                     font=("TkFixedFont", 9),
                     bg="#f8f9fa").grid(row=row, column=0, sticky=tk.W, padx=(8, 2))
            tk.Label(self._io_inner, text="ON " if val else "OFF",
                     font=("TkFixedFont", 9, "bold"),
                     bg=color, fg="white",
                     padx=4, pady=1,
                     width=4).grid(row=row, column=1, sticky=tk.W, padx=2, pady=1)
            row += 1

        # Update scroll region
        self._io_inner.update_idletasks()
        self._io_canvas.configure(scrollregion=self._io_canvas.bbox("all"))

        # Sync manual I/O buttons with current input state
        if hasattr(self, "_input_vars"):
            for ch, var in self._input_vars.items():
                current_val = relay.inputs.get(ch, False)
                if var.get() != current_val:
                    var.set(current_val)

    # ----------------------------------------------------------
    # Periodic I/O refresh (while program is running)
    # ----------------------------------------------------------

    def _start_io_refresh(self) -> None:
        self._rebuild_manual_io()
        self._schedule_io_refresh()

    def _schedule_io_refresh(self) -> None:
        self._do_io_refresh()
        self._update_job = self.after(250, self._schedule_io_refresh)

    def _do_io_refresh(self) -> None:
        prog = self.manager.current_program
        if prog:
            running = prog.is_running()
            # Sync button states with running status
            if running:
                self._run_btn.config(state=tk.DISABLED)
                self._stop_btn.config(state=tk.NORMAL)
                self._run_status_label.config(text="RUNNING", bg=self.COLOR_ON)
                self._io_running_label.config(text="RUNNING", bg=self.COLOR_ON)
            # Refresh I/O indicators
            self._refresh_io_panel()

    # ----------------------------------------------------------
    # Status bar helper
    # ----------------------------------------------------------

    def _set_status(self, msg: str, error: bool = False) -> None:
        self._status_var.set(msg)
        bg = self.COLOR_STATUS_ERR_BG if error else self.COLOR_STATUS_BG
        self._status_bar.config(bg=bg)

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------

    def on_close(self) -> None:
        # Stop any running program before exit
        if self.manager.current_program:
            self.manager.current_program.stop()
        if self._update_job:
            self.after_cancel(self._update_job)
        self.destroy()


# ============================================================
# Entry point
# ============================================================

def main():
    app = FreePLCApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
