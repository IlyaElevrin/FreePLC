#!/usr/bin/env python3
"""
Headless test for freeplc_gui_gtk.py — verifies all PLC logic and LD rendering helpers
without requiring a display (no tkinter window is opened).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from freeplc_gui_gtk import (
    PlcIO, AndGate, OrGate, NotGate, RSTrigger,
    LDProgram, RelayManager
)

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

errors = 0

def check(name: str, got, expected) -> None:
    global errors
    if got == expected:
        print(f"  {PASS}  {name}")
    else:
        print(f"  {FAIL}  {name}: expected {expected!r}, got {got!r}")
        errors += 1


# ============================================================
print("=== PlcIO ===")
io = PlcIO("test", 4, 4)
io.set_input(1, True)
check("set/get_input True",  io.get_input(1), True)
check("get_input False",     io.get_input(2), False)
check("set/get_output",      io.get_output(1), False)
io.set_output(1, True)
check("set_output True",     io.get_output(1), True)

# ============================================================
print("\n=== AndGate ===")
io2 = PlcIO("and_test", 4, 4)
gate = AndGate(1, 2, 1)
check("__str__ contains AND",  "AND" in str(gate), True)
check("ld_type",               gate.ld_type(), "AND")
check("AND get_inputs",        gate.get_inputs(), [1, 2])
check("AND get_outputs",       gate.get_outputs(), [1])

io2.set_input(1, False); io2.set_input(2, False)
check("AND(F,F)→F", gate.evaluate(io2), False)
check("AND output Q1=F", io2.get_output(1), False)

io2.set_input(1, True); io2.set_input(2, False)
check("AND(T,F)→F", gate.evaluate(io2), False)

io2.set_input(1, True); io2.set_input(2, True)
check("AND(T,T)→T", gate.evaluate(io2), True)
check("AND output Q1=T", io2.get_output(1), True)

cells = gate.rung_elements()
check("AND has 3 cells",        len(cells), 3)
check("AND cell 0 type NO",     cells[0]["type"], "NO")
check("AND cell 1 type NO",     cells[1]["type"], "NO")
check("AND cell 2 type COIL",   cells[2]["type"], "COIL")

# ============================================================
print("\n=== OrGate ===")
io3 = PlcIO("or_test", 4, 4)
gate_or = OrGate(1, 2, 1)
check("OR ld_type",      gate_or.ld_type(), "OR")
check("OR get_inputs",   gate_or.get_inputs(), [1, 2])
check("OR get_outputs",  gate_or.get_outputs(), [1])

io3.set_input(1, False); io3.set_input(2, False)
check("OR(F,F)→F", gate_or.evaluate(io3), False)

io3.set_input(1, True); io3.set_input(2, False)
check("OR(T,F)→T", gate_or.evaluate(io3), True)

io3.set_input(1, False); io3.set_input(2, True)
check("OR(F,T)→T", gate_or.evaluate(io3), True)

cells_or = gate_or.rung_elements()
check("OR has 3 cells",           len(cells_or), 3)
check("OR cell 0 type NO",        cells_or[0]["type"], "NO")
check("OR cell 1 type OR_JOIN",   cells_or[1]["type"], "OR_JOIN")
check("OR cell 2 type COIL",      cells_or[2]["type"], "COIL")

# ============================================================
print("\n=== NotGate ===")
io4 = PlcIO("not_test", 4, 4)
gate_not = NotGate(1, 1)
check("NOT ld_type",     gate_not.ld_type(), "NOT")
check("NOT get_inputs",  gate_not.get_inputs(), [1])
check("NOT get_outputs", gate_not.get_outputs(), [1])

io4.set_input(1, False)
check("NOT(F)→T", gate_not.evaluate(io4), True)

io4.set_input(1, True)
check("NOT(T)→F", gate_not.evaluate(io4), False)

cells_not = gate_not.rung_elements()
check("NOT has 2 cells",       len(cells_not), 2)
check("NOT cell 0 type NC",    cells_not[0]["type"], "NC")
check("NOT cell 1 type COIL",  cells_not[1]["type"], "COIL")

# ============================================================
print("\n=== RSTrigger ===")
io5 = PlcIO("rs_test", 4, 4)
rs = RSTrigger(1, 2, 1)
check("RS ld_type",     rs.ld_type(), "RS")
check("RS get_inputs",  rs.get_inputs(), [1, 2])
check("RS get_outputs", rs.get_outputs(), [1])

io5.set_input(1, False); io5.set_input(2, False)
check("RS idle → F", rs.evaluate(io5), False)

io5.set_input(1, True); io5.set_input(2, False)
check("RS Set → T",  rs.evaluate(io5), True)

io5.set_input(1, False); io5.set_input(2, False)
check("RS latch → T", rs.evaluate(io5), True)

io5.set_input(1, False); io5.set_input(2, True)
check("RS Reset → F", rs.evaluate(io5), False)

io5.set_input(1, False); io5.set_input(2, False)
check("RS latched F", rs.evaluate(io5), False)

cells_rs = rs.rung_elements()
check("RS has 3 cells",          len(cells_rs), 3)
check("RS cell 2 SET_COIL",      cells_rs[2]["type"], "SET_COIL")

# ============================================================
print("\n=== LDProgram ===")
io6 = PlcIO("prog_test", 4, 4)
prog = LDProgram(io6, "prog")
check("empty elements", len(prog.get_elements()), 0)

gate_a = AndGate(1, 2, 1)
gate_b = NotGate(3, 2)
gate_c = OrGate(1, 2, 3)
prog.add_element(gate_a)
prog.add_element(gate_b)
prog.add_element(gate_c)
check("add 3 elements",   len(prog.get_elements()), 3)
check("element 0 is AND", prog.get_elements()[0].ld_type(), "AND")
check("element 1 is NOT", prog.get_elements()[1].ld_type(), "NOT")
check("element 2 is OR",  prog.get_elements()[2].ld_type(), "OR")

# Test move_element (used by drag-and-drop reordering)
prog.move_element(0, 2)  # Move AND from index 0 to index 2
check("move 0→2: element 0 is NOT", prog.get_elements()[0].ld_type(), "NOT")
check("move 0→2: element 1 is OR",  prog.get_elements()[1].ld_type(), "OR")
check("move 0→2: element 2 is AND", prog.get_elements()[2].ld_type(), "AND")

prog.move_element(2, 0)  # Move AND back to index 0
check("move 2→0: element 0 is AND", prog.get_elements()[0].ld_type(), "AND")
check("move 2→0: element 1 is NOT", prog.get_elements()[1].ld_type(), "NOT")
check("move 2→0: element 2 is OR",  prog.get_elements()[2].ld_type(), "OR")

# Test move_element with out-of-bounds (should not crash)
prog.move_element(0, 0)   # same index — no change
check("move no-op: length still 3", len(prog.get_elements()), 3)
prog.move_element(-1, 0)  # invalid — no change
check("move invalid: length still 3", len(prog.get_elements()), 3)

io6.set_input(1, True); io6.set_input(2, True); io6.set_input(3, True)
prog.execute()
check("AND output after execute", io6.get_output(1), True)
check("NOT output after execute", io6.get_output(2), False)

prog.remove_element(0)
check("remove element: length 2", len(prog.get_elements()), 2)
prog.clear_elements()
check("clear elements: length 0", len(prog.get_elements()), 0)

# ============================================================
print("\n=== LDProgram — pin layout helpers ===")
# Verify _pin_ys static method
from freeplc_gui_gtk import LDCanvas
check("pin_ys empty",  LDCanvas._pin_ys(0, 100, 0), [])
check("pin_ys 1 item", LDCanvas._pin_ys(0, 100, 1), [50])
ys2 = LDCanvas._pin_ys(0, 90, 2)
check("pin_ys 2 items count", len(ys2), 2)
check("pin_ys 2 items ordered", ys2[0] < ys2[1], True)

# ============================================================
print("\n=== RelayManager ===")
mgr = RelayManager()
check("default relay exists",       mgr.has_relay("relay1"), True)
check("current relay set",          mgr.current_relay is not None, True)
check("current program set",        mgr.current_program is not None, True)

mgr.create_relay("relay2", 4, 2)
check("relay2 created",             mgr.has_relay("relay2"), True)
check("relay names count",          len(mgr.get_relay_names()), 2)

mgr.select_relay("relay2")
check("select relay2",              mgr.current_relay.name, "relay2")

# ============================================================
print("\n=== Theme import ===")
from freeplc_gui_gtk import Theme
check("Theme.BG is string",              isinstance(Theme.BG, str), True)
check("Theme.ACCENT starts #",           Theme.ACCENT.startswith("#"), True)
check("Theme.TOOLBOX_BG exists",         hasattr(Theme, "TOOLBOX_BG"), True)
check("Theme.RAIL_LEFT_BG exists",       hasattr(Theme, "RAIL_LEFT_BG"), True)
check("Theme.RAIL_RIGHT_BG exists",      hasattr(Theme, "RAIL_RIGHT_BG"), True)
check("Theme.PIN_INPUT exists",          hasattr(Theme, "PIN_INPUT"), True)
check("Theme.PIN_OUTPUT exists",         hasattr(Theme, "PIN_OUTPUT"), True)
check("Theme.BLOCK_BG exists",           hasattr(Theme, "BLOCK_BG"), True)

# ============================================================
print("\n=== Summary ===")
if errors == 0:
    print(f"All tests {PASS}!")
else:
    print(f"{errors} test(s) {FAIL}.")
    sys.exit(1)
