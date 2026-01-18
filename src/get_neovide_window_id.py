import sys
from Quartz import (
    CGWindowListCopyWindowInfo,
    kCGWindowListOptionOnScreenOnly,
    kCGNullWindowID,
)

windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)

found = False
for w in windows:
    owner = w.get("kCGWindowOwnerName", "")
    # Match "Neovide" or "neovide" (case-insensitive check)
    if owner.lower() == "neovide":
        print(w["kCGWindowNumber"])
        found = True
        break

if not found:
    # Print diagnostic info to stderr
    print("DEBUG: Neovide window not found. Available windows:", file=sys.stderr)
    for w in windows:
        owner = w.get("kCGWindowOwnerName", "")
        wid = w.get("kCGWindowNumber", "?")
        if owner:  # Skip windows with no owner
            print(f"  - {owner}: {wid}", file=sys.stderr)
