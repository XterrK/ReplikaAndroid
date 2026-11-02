#!/usr/bin/env python3
"""Destructive ONLY to the isolated .aioqa test app; never touches the normal REPLIKA data.

Run after installing allInOneQa on an emulator. No models/ZIP are staged by this harness.
It clears QA data for clean/interrupted first launches. Audio/ML tests are separate instrumentation.
"""
import argparse
import json
import os
import pathlib
import subprocess
import time

PKG = "ru.replika.offline.aioqa"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new evidence directory; existing evidence is never overwritten")
    args.output.mkdir(parents=True)

    def adb(*command, check=True):
        return subprocess.run([args.adb, *command], capture_output=True, check=check, timeout=45)

    def shell(command, check=True):
        return adb("shell", command, check=check).stdout.decode().strip()

    assert shell("getprop ro.kernel.qemu") == "1", "Harness is restricted to an emulator"
    assert shell("pm path " + PKG).startswith("package:"), "Install isolated All-in-One QA APK first"
    network_before = {"airplane": shell("settings get global airplane_mode_on"),
                      "wifi": shell("settings get global wifi_on"), "data": shell("settings get global mobile_data")}
    environment = {"package": PKG, "api": shell("getprop ro.build.version.sdk"),
                   "abi": shell("getprop ro.product.cpu.abi"), "pageBytes": shell("getconf PAGESIZE"),
                   "physicalDevice": False, "networkBefore": network_before}

    def save(name, data):
        with (args.output / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)

    def capture(name):
        target = args.output / name
        if not target.exists():
            target.write_bytes(adb("exec-out", "screencap", "-p").stdout)

    def diagnostic():
        result = shell(f"run-as {PKG} cat files/provisioning-diagnostics/latest.json", check=False)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None

    def stop():
        shell(f"am force-stop {PKG}")

    def clear_qa():
        stop()
        assert shell(f"pm clear {PKG}") == "Success"
        # Keep Android's notification prompt out of Library screenshots; no mic permission granted.
        shell(f"pm grant {PKG} android.permission.POST_NOTIFICATIONS")
        existing = shell(f"run-as {PKG} ls files/models", check=False)
        assert not existing, "Clean test must have no preinstalled models"

    def launch():
        return shell(f"am start -n {PKG}/ru.replika.MainActivity")

    def wait_ready(prefix):
        phases = []
        entered = {}
        visible_progress_captured = False
        host_started = time.monotonic()
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            current = diagnostic()
            if current:
                phase = current["phase"]
                if phase not in phases:
                    phases.append(phase)
                    entered[phase] = time.monotonic()
                    capture(prefix + "-" + phase.lower() + ".png")
                    print(prefix, phase, flush=True)
                if phase in {"ERROR", "NO_SPACE", "NO_MEMORY"}:
                    raise RuntimeError(current)
                if phase == "PREPARING" and not visible_progress_captured and time.monotonic()-entered[phase] >= 2:
                    capture(prefix + "-progress-ui.png")
                    visible_progress_captured = True
                if phase == "READY":
                    time.sleep(1)
                    shell("uiautomator dump /data/local/tmp/replika-aioqa-first-launch.xml")
                    xml = shell("cat /data/local/tmp/replika-aioqa-first-launch.xml")
                    assert f'package="{PKG}"' in xml and 'text="Библиотека"' in xml and 'text="Записи"' in xml, "Verified models did not lead to the actual app Library"
                    (args.output / (prefix + "-library.xml")).write_text(xml,encoding="utf-8")
                    capture(prefix + "-library.png")
                    save(prefix + ".json", {**current, "observedPhases": phases,
                                           "hostObservedSecondsThroughLibrary": time.monotonic()-host_started})
                    return current
            time.sleep(.12)
        raise TimeoutError("Provisioning did not reach READY")

    try:
        shell("cmd connectivity airplane-mode enable")
        shell("svc wifi disable")
        shell("svc data disable")
        environment["networkDuring"] = {"airplane": shell("settings get global airplane_mode_on"),
                                        "wifi": shell("settings get global wifi_on"),
                                        "data": shell("settings get global mobile_data"),
                                        "routes": shell("ip route", check=False)}
        assert environment["networkDuring"]["airplane"] == "1"
        save("environment.json", environment)
        clear_qa()
        launch()
        first = wait_ready("01-clean-offline")
        assert first["extracted"] == first["published"] == 8 and first["validSkipped"] == 0
        before = shell(f"run-as {PKG} sh -c 'find files/models -type f -exec stat -c \"%n %s %Y\" {{}} \\;' ")
        stop()
        launch()
        # Wait for a new run ID, never treat stale READY JSON as completion of this launch.
        deadline = time.monotonic() + 60
        while (diagnostic() or {}).get("runId") == first["runId"]:
            if time.monotonic() > deadline:
                raise TimeoutError("No new provisioning attempt after force-stop")
            time.sleep(.1)
        second = wait_ready("02-cold-restart")
        after = shell(f"run-as {PKG} sh -c 'find files/models -type f -exec stat -c \"%n %s %Y\" {{}} \\;' ")
        assert before == after
        assert second["validSkipped"] == 8 and second["extracted"] == second["published"] == 0
        save("02-preserved-model-times.json", {"before": before, "after": after, "equal": True})

        clear_qa()
        launch()
        interrupted = False
        captured_preparing = False
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            current = diagnostic()
            if current and current["phase"] == "READY":
                raise RuntimeError("Preparation completed before interruption trigger; do not claim interruption")
            staged = shell(f"run-as {PKG} find files/bundled-model-staging -type f", check=False)
            if current and current["phase"] == "PREPARING" and not captured_preparing and "/encoder.int8.onnx\n" not in staged + "\n":
                capture("03-preparing-before-interruption.png")
                captured_preparing = True
            # Stop after a whole verified model was staged and before the archive is fully read.
            if "/encoder.int8.onnx\n" in staged + "\n" and ".bundled-part" in staged:
                stop()
                remaining = shell(f"run-as {PKG} find files/bundled-model-staging -type f", check=False)
                live = shell(f"run-as {PKG} find files/models -type f", check=False)
                assert not live, "No live model may be published before verification of the whole pack"
                save("03-interruption.json", {"diagnosticAtStop": current, "stagedAtStop": remaining,
                                               "liveModelsAtStop": live, "forcedProcessStop": True})
                interrupted = True
                break
            time.sleep(.08)
        assert interrupted
        launch()
        resumed = wait_ready("04-resumed-offline")
        assert resumed["published"] == 8 and resumed["reusedStage"] >= 1
        save("summary.json", {"cleanOfflinePreparation": "PASS", "coldRestartNoExtraction": "PASS",
                              "forcedInterruptionAndResume": "PASS", "physicalArm64Validation": "BLOCKED"})
    finally:
        # Restore only emulator settings changed by this test.
        if network_before["airplane"] == "0":
            shell("cmd connectivity airplane-mode disable", check=False)
        if network_before["wifi"] == "1":
            shell("svc wifi enable", check=False)
        if network_before["data"] == "1":
            shell("svc data enable", check=False)


if __name__ == "__main__":
    main()
