import os
import sys

def is_macos():
    return sys.platform == "darwin"

def is_linux():
    return sys.platform == "linux"

def is_windows():
    return os.name == "nt"
