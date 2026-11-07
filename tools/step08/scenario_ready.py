"""Reference-mode file -> automatic speakers -> READY -> playback. My emulator only."""
import sys, time, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from ui import tap, wait, dump, find, nodes, shot, adb

def texts():
    return [n.get("text") or n.get("content-desc") or "" for n, _ in nodes(dump())]

def pick(name):
    if find(dump(), 'Files in Downloads'):
        tap('^' + re.escape(name) + '$', 20); return
    adb("shell", "input", "keyevent", "KEYCODE_BACK")  # close any open picker
    time.sleep(1)
    for label in ("^Библиотека$",):
        if find(dump(), label): tap(label); time.sleep(1)
    if find(dump(), "^Запись$"): tap("^Запись$"); time.sleep(1)
    tap("^Импорт$"); wait("Show roots", 20); time.sleep(2)
    tap("Show roots"); wait("^Downloads$", 10); time.sleep(2)
    tap("^Downloads$"); wait("Files in Downloads", 20); time.sleep(2)
    tap("^" + re.escape(name) + "$", 20)

name = sys.argv[1]; mode = sys.argv[2] if len(sys.argv) > 2 else "^Автоматически$"
pick(name)
wait("^Готово к обработке$", 60)
print("imported:", [t for t in texts() if "REPLIKA" in t or "МБ" in t or "ГБ" in t][:3])
tap(mode); tap("^Создать стенограмму$")
start = time.time(); shots = 0
while time.time() - start < 1800:
    time.sleep(10)
    t = texts()
    line = " | ".join(x for x in t if re.match(r"(Декод|Поиск|Говорящ|Распозн|Осталось|Обработано|Диаризация|Уточнение|Подготовка|Загрузка)", x))
    print(time.strftime("%H:%M:%S"), line, flush=True)
    if any("Говорящие" in x for x in t) and shots < 1: shot("shots/progress-speakers.png"); shots += 1
    if any(x in ("Диалог", "Чтение") for x in t) or any(x.startswith("Не удалось") for x in t): break
shot("shots/ready.png")
print("final:", [x for x in t if x][:12])
