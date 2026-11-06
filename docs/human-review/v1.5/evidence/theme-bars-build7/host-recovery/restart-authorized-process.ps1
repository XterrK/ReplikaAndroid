$qaAvdProcess=Get-CimInstance Win32_Process -Filter 'ProcessId=16452'
if (-not $qaAvdProcess -or $qaAvdProcess.Name -ne 'qemu-system-x86_64-headless.exe' -or $qaAvdProcess.CommandLine -notlike '*-avd Replika35v11*') { throw 'Authorized Qemu process identity changed; stop without mutation' }
$qaAvdProcess | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json | Out-File -Encoding utf8 'F:\Hackathons\ReplikaAndroid\docs\human-review\v1.5\evidence\theme-bars-build7\host-recovery\before-process.json'
Stop-Process -Id 16452 -Force
Start-Sleep -Seconds 2
$env:ANDROID_AVD_HOME='F:\ReplikaToolchain\avd-windows'
$env:ANDROID_HOME='F:\ReplikaToolchain\sdk'
$env:ANDROID_SDK_ROOT=$env:ANDROID_HOME
$env:ANDROID_ADB_SERVER_PORT='5038'
Start-Process -FilePath 'F:\ReplikaToolchain\windows-sdk\emulator\emulator.exe' -ArgumentList '-avd Replika35v11 -no-snapshot -no-boot-anim -no-audio -no-window -gpu swiftshader -accel on -port 5556' -RedirectStandardOutput 'F:\ReplikaToolchain\v15-nav-recovery-emulator.log' -RedirectStandardError 'F:\ReplikaToolchain\v15-nav-recovery-emulator-error.log' -PassThru | Select-Object Id,ProcessName | ConvertTo-Json
