#!/usr/bin/env python3
"""
Test the core PLC logic classes from freeplc_gui.py without starting the GUI.
Run from project root: python3 experiments/test_python_logic.py
"""
import sys
import os

# Import from the main GUI file (core logic only)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from freeplc_gui import (
    PlcIO, AndGate, OrGate, NotGate, RSTrigger, LDProgram, RelayManager
)

passed = 0
failed = 0


def check(condition: bool, msg: str) -> None:
    global passed, failed
    if condition:
        print(f"[PASS] {msg}")
        passed += 1
    else:
        print(f"[FAIL] {msg}")
        failed += 1


def test_plcio():
    print("\n--- PlcIO ---")
    io = PlcIO("relay1", 4, 4)
    io.set_input(1, True)
    check(io.get_input(1) == True,  "setInput/getInput channel 1 true")
    check(io.get_input(2) == False, "unset input channel 2 is false")
    io.set_output(1, True)
    check(io.get_output(1) == True,  "setOutput/getOutput channel 1 true")
    check(io.get_output(99) == False, "out-of-range output returns false")


def test_and_gate():
    print("\n--- AndGate ---")
    io = PlcIO("r", 4, 4)
    g = AndGate(1, 2, 1)

    io.set_input(1, False); io.set_input(2, False)
    g.evaluate(io)
    check(io.get_output(1) == False, "AND 0,0 = 0")

    io.set_input(1, True); io.set_input(2, False)
    g.evaluate(io)
    check(io.get_output(1) == False, "AND 1,0 = 0")

    io.set_input(1, True); io.set_input(2, True)
    g.evaluate(io)
    check(io.get_output(1) == True, "AND 1,1 = 1")


def test_or_gate():
    print("\n--- OrGate ---")
    io = PlcIO("r", 4, 4)
    g = OrGate(1, 2, 1)

    io.set_input(1, False); io.set_input(2, False)
    g.evaluate(io)
    check(io.get_output(1) == False, "OR 0,0 = 0")

    io.set_input(1, True); io.set_input(2, False)
    g.evaluate(io)
    check(io.get_output(1) == True, "OR 1,0 = 1")

    io.set_input(1, False); io.set_input(2, True)
    g.evaluate(io)
    check(io.get_output(1) == True, "OR 0,1 = 1")


def test_not_gate():
    print("\n--- NotGate ---")
    io = PlcIO("r", 4, 4)
    g = NotGate(1, 1)

    io.set_input(1, False)
    g.evaluate(io)
    check(io.get_output(1) == True, "NOT 0 = 1")

    io.set_input(1, True)
    g.evaluate(io)
    check(io.get_output(1) == False, "NOT 1 = 0")


def test_rs_trigger():
    print("\n--- RSTrigger ---")
    io = PlcIO("r", 4, 4)
    rs = RSTrigger(1, 2, 1)  # set=I1, reset=I2, out=Q1

    # Initial state: no set/reset
    io.set_input(1, False); io.set_input(2, False)
    rs.evaluate(io)
    check(io.get_output(1) == False, "RS initial state = 0")

    # Set
    io.set_input(1, True); io.set_input(2, False)
    rs.evaluate(io)
    check(io.get_output(1) == True, "RS after SET = 1")

    # Latch (both off)
    io.set_input(1, False); io.set_input(2, False)
    rs.evaluate(io)
    check(io.get_output(1) == True, "RS latched = 1")

    # Reset
    io.set_input(1, False); io.set_input(2, True)
    rs.evaluate(io)
    check(io.get_output(1) == False, "RS after RESET = 0")


def test_ld_program():
    print("\n--- LDProgram ---")
    io = PlcIO("r", 4, 4)
    prog = LDProgram(io, "test_prog")

    check(len(prog.get_elements()) == 0, "Program starts empty")
    check(not prog.is_running(), "Program not running initially")

    prog.add_element(AndGate(1, 2, 1))
    check(len(prog.get_elements()) == 1, "Element added")

    # Execute manually
    io.set_input(1, True)
    io.set_input(2, True)
    prog.execute()
    check(io.get_output(1) == True, "AND gate evaluated correctly via execute()")

    prog.remove_element(0)
    check(len(prog.get_elements()) == 0, "Element removed")

    prog.add_element(OrGate(1, 2, 1))
    prog.add_element(NotGate(3, 2))
    prog.clear_elements()
    check(len(prog.get_elements()) == 0, "Clear all elements")


def test_relay_manager():
    print("\n--- RelayManager ---")
    mgr = RelayManager()
    check(mgr.current_relay is not None, "Default relay created")
    check(mgr.has_relay("test"), "Default relay named 'test'")

    mgr.create_relay("r2", 4, 4)
    check(mgr.has_relay("r2"), "Create new relay r2")

    ok = mgr.select_relay("r2")
    check(ok, "Select relay r2")
    check(mgr.current_relay.name == "r2", "Current relay is r2")

    notok = mgr.select_relay("nonexistent")
    check(not notok, "Select nonexistent relay returns false")

    names = mgr.get_relay_names()
    check("test" in names and "r2" in names, "get_relay_names returns all relays")


def test_gate_str():
    print("\n--- Gate toString ---")
    check(str(AndGate(1, 2, 3)) == "AND  I1 & I2 -> Q3", "AND gate str")
    check(str(OrGate(1, 2, 3)) == "OR   I1 | I2 -> Q3", "OR gate str")
    check(str(NotGate(1, 2)) == "NOT  I1 -> Q2", "NOT gate str")
    check(str(RSTrigger(1, 2, 3)) == "RS   I1(S) / I2(R) -> Q3", "RS trigger str")


if __name__ == "__main__":
    print("=== FreePLC Python Logic Tests ===")
    test_plcio()
    test_and_gate()
    test_or_gate()
    test_not_gate()
    test_rs_trigger()
    test_ld_program()
    test_relay_manager()
    test_gate_str()
    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    sys.exit(0 if failed == 0 else 1)
