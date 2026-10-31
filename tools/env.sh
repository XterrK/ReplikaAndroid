#!/usr/bin/env bash
export JAVA_HOME=/mnt/f/ReplikaToolchain/jdk-17.0.17+10
export ANDROID_HOME=/mnt/f/ReplikaToolchain/sdk
export ANDROID_USER_HOME=/mnt/f/ReplikaToolchain/android-user
export GRADLE_USER_HOME=/mnt/f/ReplikaToolchain/gradle-cache
export TMPDIR=/mnt/f/ReplikaToolchain/tmp
mkdir -p "$TMPDIR"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:/mnt/f/ReplikaToolchain/gradle-8.13/bin:$PATH"
