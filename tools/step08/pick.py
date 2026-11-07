import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from ui import tap, wait, dump, find
name = sys.argv[1]
if not find(dump(), "Show roots"):
    tap("^Импорт$")
wait("Show roots", 20); time.sleep(1)
tap("Show roots"); wait("^Downloads$", 10); time.sleep(1)
tap("^Downloads$"); wait("Files in Downloads", 15); time.sleep(1)
tap("^" + name.replace(".", r"\.") + "$", 20)
print("picked", name)
