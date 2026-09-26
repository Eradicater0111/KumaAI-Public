#!/usr/bin/env python3
from __future__ import annotations
import argparse
from app.tools.location_tools import live_location_enabled, set_live_location_enabled

def main():
    parser = argparse.ArgumentParser(description="Manage KUMA live-location opt-in.")
    parser.add_argument("command", choices=("status", "enable", "disable"))
    args = parser.parse_args()
    if args.command == "enable":
        set_live_location_enabled(True)
    elif args.command == "disable":
        set_live_location_enabled(False)
    print("KUMA live location: " + ("ENABLED" if live_location_enabled() else "DISABLED"))
    print("Persistent location history: DISABLED")

if __name__ == "__main__":
    main()
