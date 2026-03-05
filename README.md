# FreePLC

FreePLC is a Linux program for programming and simulating relays (Programmable Logic Controllers).

## Features

- **AND, OR, NOT gates** — standard logic gate elements
- **RS Trigger** — set-reset latch with state retention
- **Multiple relays** — create and manage several named relays, each with its own LD program
- **Manual I/O control** — toggle individual input channels while the program runs
- **Background scan cycle** — logic executes every 200 ms in a background thread
- **Owen Logic-style GTK GUI** — function block palette, drag-and-drop rung reordering,
  input pins on the left of the canvas, output pins on the right
- **Windowed GUI** (Python/tkinter) and a console UI (C++/ncurses) both included

---

## Python GTK-style GUI with visual Ladder Diagram (recommended)

The main interface is a cross-platform windowed GUI written in Python using the standard
`tkinter` library — no extra dependencies required. It uses a GTK/GNOME (Adwaita) visual
style and features a **visual Ladder Diagram (LD) canvas** styled after professional PLC
editors like Owen Logic / Codesys.

### Key features

- **Owen Logic-style function blocks** — each rung displays a graphical function block
  (rectangle with colored header) with input pins on the **left side** and output pins on the **right side**.
- **Left power rail with input pins** — all relay inputs (I1..In) are labeled and shown
  on the **left side** of the canvas, wired into the left power rail.
- **Right power rail with output pins** — all relay outputs (Q1..Qn) are labeled and shown
  on the **right side** of the canvas, wired out of the right power rail.
- **Dark toolbox panel** — a left-hand panel (Owen Logic style) lists all available function
  block types (AND, OR, NOT, RS) with descriptions and one-click add buttons.
- **Drag-and-drop rung reordering** — drag any rung up or down on the canvas to change the
  execution order. Use the ⬆/⬇ buttons in the toolbox as an alternative.
- **Live I/O state visualization** — active input pins and energized output pins are
  highlighted in real time during simulation.

### Requirements

- Python 3.7+
- `tkinter` (included in standard CPython distributions; on Debian/Ubuntu install with `sudo apt install python3-tk`)

### Run

```bash
python3 freeplc_gui_gtk.py
```

### Layout overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│ FreePLC                                   ▶ Run   ⏹ Stop  ● STOPPED    │  ← Header bar
├───────────────┬────────────────────────────────────────────┬────────────┤
│ FUNCTION      │  INPUTS │                     │ OUTPUTS   │ Relays     │
│ BLOCKS        │  ──I1── │    [ AND block ]    │ ──Q1──    │            │
│               │  ──I2── │  I1 ┤AND├ Q1        │ ──Q2──    │ I/O Status │
│  [AND]  +Add  │  ──I3── │  I2 ┤   ├           │           │            │
│  [OR]   +Add  │  ...    │                     │ ...       │            │
│  [NOT]  +Add  │         │   Left rail     Right rail      │            │
│  [RS]   +Add  │         │                                 │            │
│               │         │  ← Ladder Diagram canvas →      │            │
│  ✕ Remove     │─────────┴────────────────────────────────┤            │
│  ⬆ Move Up    │    Manual Input Control (I1 I2 I3 ...)    │            │
│  ⬇ Move Down  │                                           │            │
└───────────────┴───────────────────────────────────────────┴────────────┘
```

### Usage

1. **Function block toolbox** (left dark panel) — click **+ Add AND/OR/NOT/RS** to open a
   dialog, configure input/output channel numbers, and add the block to the program.
2. **Ladder Diagram canvas** (center) — each rung shows a graphical function block:
   - Input pins are on the **left side** of the block, wired to the left power rail (inputs)
   - Output pins are on the **right side** of the block, wired to the right power rail (outputs)
   - **Drag a rung** up or down to reorder the execution sequence
   - **Click a rung** to select it (highlighted in blue)
3. **Header bar — ▶ Run / ⏹ Stop** — start or stop the 200 ms scan cycle. The status pill
   shows **RUNNING** (green) / **STOPPED** (red).
4. **Manual Input Control strip** (below canvas) — click an input button to toggle it ON/OFF
   in real time. Active pins on the canvas light up in color.
5. **Right sidebar — I/O Status** — live ON/OFF indicator for every input and output channel.
6. **Toolbox — ✕ Remove / ⬆⬇ Move** — remove the selected rung or reorder it with the arrow buttons.

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
