#!/usr/bin/env python3

"""Test script to verify specific heyhi modules can be imported."""

print("Testing importing heyhi.conf specifically:")
try:
    from heyhi import conf
    print("Successfully imported heyhi.conf!")
    print(f"CONF_ROOT = {conf.CONF_ROOT}")
except Exception as e:
    print(f"Error importing heyhi.conf: {e}")

print("\nTesting importing direct from heyhi.conf:")
try:
    from heyhi.conf import CONF_ROOT, PROJ_ROOT
    print(f"CONF_ROOT = {CONF_ROOT}")
    print(f"PROJ_ROOT = {PROJ_ROOT}")
    print("Successfully imported from heyhi.conf directly!")
except Exception as e:
    print(f"Error importing from heyhi.conf directly: {e}")