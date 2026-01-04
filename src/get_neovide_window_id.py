from Quartz import (
    CGWindowListCopyWindowInfo,
    kCGWindowListOptionOnScreenOnly,
    kCGNullWindowID,
)

windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)

for w in windows:
    owner = w.get("kCGWindowOwnerName", "")
    name = w.get("kCGWindowName", "")
    if owner == "Neovide":
        print(w["kCGWindowNumber"])
        break
