"""Tiny uiautomator driver for an explicitly chosen emulator (always adb -s SERIAL).

Never point it at a physical phone. SERIAL comes from REPLIKA_EMULATOR (default emulator-5580),
adb from ANDROID_HOME. Step-8 checks; see README.md next to this file."""
import re, subprocess, sys, time, os, xml.etree.ElementTree as ET
ADB = os.path.join(os.environ["ANDROID_HOME"], "platform-tools", "adb.exe" if os.name == "nt" else "adb")
SERIAL = os.environ.get("REPLIKA_EMULATOR", "emulator-5580")
if not SERIAL.startswith("emulator-"): raise SystemExit("Only emulators are allowed")

def adb(*args, check=True):
    r = subprocess.run([ADB, "-s", SERIAL, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode: raise SystemExit(r.stderr)
    return r.stdout

def dump():
    for _ in range(5):
        out = adb("exec-out", "uiautomator", "dump", "/dev/tty", check=False)
        i = out.find("<?xml")
        if i >= 0:
            xml = out[i:out.rfind(">") + 1]
            try: return ET.fromstring(xml)
            except ET.ParseError: pass
        time.sleep(1)
    raise SystemExit("dump failed")

def nodes(root):
    for n in root.iter("node"):
        b = [int(x) for x in re.findall(r"\d+", n.get("bounds", "[0,0][0,0]"))]
        yield n, ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)

def show(root):
    for n, c in nodes(root):
        t = n.get("text") or ""; d = n.get("content-desc") or ""; r = n.get("resource-id") or ""
        if t or d or r: print(c, repr(t)[:90], repr(d)[:60], r[-40:], "click" if n.get("clickable") == "true" else "")

def find(root, pattern):
    rx = re.compile(pattern)
    for n, c in nodes(root):
        for k in ("text", "content-desc", "resource-id"):
            if rx.search(n.get(k) or ""): return n, c
    return None

def tap(pattern, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        f = find(dump(), pattern)
        if f: adb("shell", "input", "tap", str(f[1][0]), str(f[1][1])); return f[1]
        time.sleep(1)
    raise SystemExit(f"not found: {pattern}")

def wait(pattern, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        root = dump()
        f = find(root, pattern)
        if f: return f[0]
        time.sleep(1)
    show(root); raise SystemExit(f"timeout waiting: {pattern}")

def shot(path):
    data = subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"], capture_output=True).stdout
    open(path, "wb").write(data)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.argv = [a.encode("ascii","backslashreplace").decode("unicode_escape") if a.isascii() else a for a in sys.argv]
    cmd = sys.argv[1]
    if cmd == "show": show(dump())
    elif cmd == "tap": print(tap(sys.argv[2]))
    elif cmd == "wait": n = wait(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 60); print(n.get("text"), n.get("content-desc"))
    elif cmd == "shot": shot(sys.argv[2])
