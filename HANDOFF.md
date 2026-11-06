# Продолжение REPLIKA на ноутбуке

Текущая версия: **V1.6 / versionCode 8**. Модели остались V1.5. Сначала прочитайте `PROJECT_STATE.md` и `TEST_REPORT_V1_6.md`. Известный нерешённый ML-дефект — automatic diarization; этот цикл посвящён UI, распознавание не переделывалось.

## Перенос

1. Скопируйте **всю эту папку**, включая скрытую `.git`, `model-pack/`, `app/src/main/jniLibs/`, `local-dev/debug.keystore`. Не ограничивайтесь clone/экспортом Git: большая часть локальных моделей и ключ намеренно игнорируется. Не публикуйте приватную копию папки целиком.
2. На ноутбуке установите Android Studio/SDK с Android 35, Build Tools 35.0.0, NDK 27.2.12479018, JDK 17 и Python 3.12+. Задайте `JAVA_HOME`, `ANDROID_HOME`. Android Studio может заново создать `local.properties` с местным SDK. Общий SDK/JDK из соседнего `F:\ReplikaToolchain` переносить не обязательно.
3. В корне проекта выполните:

```sh
python3 tools/verify_workspace.py --pack model-pack/replika-offline-pack-v1.5.zip --manifest docs/ui-v1.6/workspace-inputs.json
python3 tools/build_portable.py --check :app:assembleAllInOne
python3 tools/build_portable.py :app:assembleAllInOne
```

В Windows используйте `python` вместо `python3`. Подробности и PowerShell-примеры: `PORTABILITY.md`. Для первого Gradle-запуска нужен интернет для библиотек/Gradle, все ML-модели уже в папке. Приложение работает локально и не скачивает их при записи.

Готовый проверенный для установки arm64 APK находится в `release/REPLIKA-V1.6-AllInOne-arm64.apk`; контрольная сумма — `release/SHA256SUMS`. Результат новой сборки: `app/build/outputs/apk/allInOne/app-allInOne.apk`. Прежняя подпись сохранена — обновляйте поверх приложения, не удаляйте его с телефона.

## Что где лежит

- `app/src/main/java/ru/replika/ui/RecordingHome.kt` — композиция главной и краевая голосовая волна.
- `LiquidVoiceOrb.kt`, `OrbDynamics.kt`, `OrbFrameCadence.kt` в том же каталоге — материал/контур/движение шара.
- `Screens.kt` — выход из записи и панель сохранения/удаления; `AppViewModel.kt` — реальный рекордер и очистка таймера.
- `docs/ui-v1.6/` — веб-референсы, концепт, нативные скриншоты, тесты, SHA-входы и журнал перемещений.
- `model-pack/` и `.so` в `app/src/main/jniLibs/` — обязательные локальные build inputs.
- `benchmark/fixtures/` — прежние локальные smoke-аудио для regression-тестов; `tools/stage_android.py` теперь берёт их отсюда.
- `release/archive/`, `review/`, `docs/history/`, версионные корневые отчёты — история. Старый видеоэксперимент: `archive/video-production-fi-20261105/`.

Машинные кэши и промежуточные build outputs не являются исходниками. `tools/build_local.py` оставлен для прежней машины с F:/RAM cache; на ноутбуке используйте **build_portable.py**. Исторические ML/benchmark-скрипты могут требовать отдельно описанные внешние датасеты; они не нужны для сборки/работы текущего APK.

## Проверка после установки на телефон

Нажмите шар, запишите голос и паузу. Проверьте правую волну и центр шара. Выйдите стрелкой/жестом «Назад»: выберите удаление и убедитесь, что главная чистая. Повторите с сохранением, вернитесь на главную — старого таймера быть не должно. Проверьте обе темы и привычный размер шрифта. Новая физическая приёмка GPU/нагрева на телефоне ещё нужна; эмуляторные результаты перечислены в отчёте.
