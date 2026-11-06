#!/usr/bin/env bash
# Source from Bash after setting JAVA_HOME and ANDROID_HOME (or local.properties).
# Discovery only: no directories, caches, SDKs, or signing keys are created.
_replika_env_setup() {
    local replika_root replika_python replika_exports replika_assignment
    replika_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)" || return 1
    if command -v python3 >/dev/null 2>&1; then
        replika_python=python3
    elif command -v python >/dev/null 2>&1; then
        replika_python=python
    else
        printf '%s\n' 'Python 3.12+ is required; set JAVA_HOME and ANDROID_HOME before sourcing tools/env.sh.' >&2
        return 1
    fi
    replika_exports="$("$replika_python" "$replika_root/tools/build_portable.py" --print-env)" || return 1
    while IFS= read -r replika_assignment; do
        export "$replika_assignment" || return 1
    done <<< "$replika_exports"
}
if _replika_env_setup; then
    unset -f _replika_env_setup
else
    unset -f _replika_env_setup
    return 1 2>/dev/null || exit 1
fi
