"""Reject incompatible bytecode before marshal can crash the interpreter."""
from importlib.util import MAGIC_NUMBER


def validate_runtime_header(header):
    if len(header) != 16 or header[:4] != MAGIC_NUMBER:
        raise RuntimeError("The recovered runtime requires its matching Python interpreter (currently Python 3.12). Use .venv/Scripts/python.exe; original source recovery is still pending.")
