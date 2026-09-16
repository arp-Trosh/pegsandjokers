"""Standalone entry point used to build the PyInstaller executable.

PyInstaller runs this as a plain script rather than `python -m pegsandjokers`,
so it needs an absolute import instead of __main__.py's relative one.
"""
from pegsandjokers.main import main

if __name__ == "__main__":
    main()
