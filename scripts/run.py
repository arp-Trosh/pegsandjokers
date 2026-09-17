"""Standalone entry point used to build the PyInstaller executable.

PyInstaller runs this as a plain script rather than `python -m pegsandjokers`,
so it needs an absolute import instead of __main__.py's relative one.
"""
import os
import shutil
import subprocess
import sys


def _relaunch_in_windows_terminal() -> bool:
    """Re-exec the frozen .exe inside Windows Terminal, if available.

    Double-clicking a console .exe opens whatever Windows' default terminal
    host is, which is often the legacy conhost window rather than Windows
    Terminal. conhost's QuickEdit Mode steals mouse clicks that Textual
    needs, so we hop into `wt.exe` ourselves instead of relying on that
    system-wide setting. Only applies to the frozen build, and only when
    we're not already inside Windows Terminal (WT_SESSION is set by wt.exe
    for every process it hosts, so this can't loop).
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    if os.environ.get("WT_SESSION"):
        return False

    wt_path = shutil.which("wt.exe") or shutil.which("wt")
    if not wt_path:
        return False

    try:
        subprocess.Popen([wt_path, sys.executable])
    except OSError:
        return False
    return True


if __name__ == "__main__":
    if not _relaunch_in_windows_terminal():
        from pegsandjokers.main import main

        main()
