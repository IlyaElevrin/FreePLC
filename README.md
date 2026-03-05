# FreePLC

FreePLC is a Linux program for programming and simulating relays (Programmable Logic Controllers).

## Features

- **AND, OR, NOT gates** — standard logic gate elements
- **RS Trigger** — set-reset latch with state retention
- **Multiple relays** — create and manage several named relays, each with its own LD program
- **Manual I/O control** — toggle individual input channels while the program runs
- **Background scan cycle** — logic executes every 200 ms in a background thread
- **Windowed GUI** (Python/tkinter) and a console UI (C++/ncurses) both included

---

## Python GTK-style GUI with visual Ladder Diagram (recommended)

The main interface is a cross-platform windowed GUI written in Python using the standard
`tkinter` library — no extra dependencies required. It uses a GTK/GNOME (Adwaita) visual
style and features a **visual Ladder Diagram (LD) canvas** that renders each program rung
using standard PLC notation (contacts and coils), similar to professional PLC editors like
Owen Logic / Codesys.

### Requirements

- Python 3.7+
- `tkinter` (included in standard CPython distributions; on Debian/Ubuntu install with `sudo apt install python3-tk`)

### Run

```bash
python3 freeplc_gui_gtk.py
```

### LD Canvas — standard symbols

| Symbol | Notation | Meaning |
|--------|----------|---------|
| Normally-Open contact | `--\| \|--` | Reads an input; passes power when input is ON |
| Normally-Closed contact | `--\|/\|--` | Negated input (NOT); passes power when input is OFF |
| Output coil | `--(  )--` | Writes an output; energised when rung evaluates TRUE |
| Set coil | `--(S)--` | RS latch Set; output stays ON until Reset |
| Parallel branch | OR join | Second contact shown as a parallel branch on the rung |

### Usage

1. **Sidebar — Relays** — click **＋ New Relay** to create a relay with configurable input/output
   channels, then **✓ Select** (or double-click) to make it active.
2. **Sidebar — Add Element** — click **AND**, **OR**, **NOT**, or **RS** to open a GTK-style
   dialog and configure channel numbers. The element appears immediately on the LD canvas as a
   graphical rung.
3. **Header bar — ▶ Run / ⏹ Stop** — start or stop the 200 ms scan cycle. The status pill
   shows **RUNNING** (green) / **STOPPED** (red).
4. **Manual Input Control strip** (below the canvas) — click an input button to toggle it ON/OFF
   in real time. Active contacts on the canvas light up in blue; energised coils light up in red
   or green.
5. **Sidebar — I/O Status** — live ON/OFF indicator for every input and output channel.
6. **Click a rung** on the canvas to select it, then click **✕ Remove Selected** to delete it.

## Python GUI (classic tkinter, alternative)

The original tkinter-based interface is still available:

### Run

```bash
python3 freeplc_gui.py
```

### Usage

1. **Relays tab** — create a new relay or select an existing one. Each relay has a configurable number of input and output channels.
2. **LD Program tab** — add logic elements (AND / OR / NOT gates, RS trigger) to the selected relay's Ladder Diagram program. Elements execute in order top-to-bottom each scan cycle.
3. **Run / Control tab** — start or stop the scan cycle and toggle input channels manually. The I/O panel on the right shows live input/output states.

---

## C++ ncurses UI (alternative)

A terminal-based interface is also available for environments without a display server.

### Requirements

- C++17 compiler (g++ or clang++)
- CMake >= 3.14
- ncurses development headers (`sudo apt install libncurses-dev`)

### Build

```bash
mkdir build && cd build
cmake ..
make
```

### Run

```bash
./build/freeplc
```

---

## Running tests

**Python logic tests** (no display required):

```bash
# Test original tkinter GUI logic
python3 experiments/test_python_logic.py

# Test GTK-style GUI logic and LD rendering helpers
python3 experiments/test_gtk_gui_logic.py
```

**C++ logic tests:**

```bash
cd experiments
g++ -std=c++17 -I../include test_logic.cpp ../src/plcio.cpp ../src/gates.cpp \
    ../src/ld_program.cpp ../src/relay_manager.cpp -pthread -o test_logic
./test_logic
```

---

## Project structure

```
freeplc_gui_gtk.py      # Python GTK-style GUI with visual LD canvas (recommended)
freeplc_gui.py          # Python classic tkinter GUI (alternative)
main.cpp                # C++ ncurses UI entry point
CMakeLists.txt          # CMake build for C++ version
include/                # C++ header files
src/                    # C++ source files
experiments/            # Unit tests and experimental scripts
  test_python_logic.py  # Headless tests for freeplc_gui.py logic
  test_gtk_gui_logic.py # Headless tests for freeplc_gui_gtk.py logic
  test_logic.cpp        # C++ logic unit tests
```
