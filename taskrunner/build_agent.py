"""
VantaHire Agent — Build Script
Creates a standalone executable (.exe / macOS app) using PyInstaller.

Usage:
  pip install pyinstaller
  python build_agent.py

Output:
  dist/VantaHire.exe  (Windows)
  dist/VantaHire       (macOS/Linux)
"""

import PyInstaller.__main__
import sys
import os

# All automation modules to include
HIDDEN_IMPORTS = [
    "requests",
    "dotenv",
    "anthropic",
    "pdfplumber",
    "docx",
    "reportlab",
    "reportlab.lib",
    "reportlab.lib.pagesizes",
    "reportlab.pdfgen",
    "reportlab.pdfgen.canvas",
    "playwright",
    "playwright.sync_api",
    "PyPDF2",
]

# Data files — automation scripts
DATA_FILES = [
    (os.path.join("..", "automation"), "automation"),
]

args = [
    "agent_entry.py",                    # entry point
    "--name=VantaHire",
    "--onefile",                         # single .exe
    "--console",                         # show console window (needed for logs)
    "--icon=NONE",                       # add icon later
    f"--distpath={os.path.join('..', 'dist')}",
    f"--workpath={os.path.join('..', 'build')}",
    f"--specpath={os.path.join('..', 'build')}",
]

# Add hidden imports
for imp in HIDDEN_IMPORTS:
    args.append(f"--hidden-import={imp}")

# Add data files
for src, dest in DATA_FILES:
    sep = ";" if sys.platform == "win32" else ":"
    args.append(f"--add-data={src}{sep}{dest}")

print("=" * 50)
print("  Building VantaHire Agent")
print("=" * 50)

PyInstaller.__main__.run(args)

print("\nBuild complete! Find the executable in dist/")
