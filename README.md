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

## Python GUI (recommended)

The main interface is a cross-platform windowed GUI written in Python using the standard `tkinter` library — no extra dependencies required.

### Requirements

- Python 3.7+
- `tkinter` (included in standard CPython distributions; on Debian/Ubuntu install with `sudo apt install python3-tk`)

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
python3 experiments/test_python_logic.py
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
freeplc_gui.py          # Python windowed GUI (main application)
main.cpp                # C++ ncurses UI entry point
CMakeLists.txt          # CMake build for C++ version
include/                # C++ header files
src/                    # C++ source files
experiments/            # Unit tests and experimental scripts
```
