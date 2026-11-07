# Продолжение REPLIKA на ноутбуке

**Работа приостановлена по запросу пользователя на контрольном срезе пункта 5.**
Начинать с [HANDOFF_NEXT_AGENT.md](HANDOFF_NEXT_AGENT.md), [STATUS.md](STATUS.md)
и [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md). Реализация CPU, термоконтроля и импорта
проверена; результаты и оставшиеся ограничения — в
[отчёте пункта 5](docs/STEP_05_RUNTIME_IMPORT.md). Источник итогового commit — история
`hack/final` и тег `hack-step05-20261107`; ветка работы — `hack/task-05-runtime-import`.
Пункт 6 не начат. Возобновлять работу только по новому указанию пользователя.

Пункт C опубликован: commit `b619519`, объединённый
[PR #4](https://github.com/XterrK/ReplikaAndroid/pull/4) и
[выпуск C2](https://github.com/XterrK/ReplikaAndroid/releases/tag/hack-step04-20261107).
Проверенный ранее D описан в [отчёте D](docs/STEP_03_VAD_WORD_ASR.md), C — в
[отчёте C](docs/STEP_04_DIARIZATION.md); эти checkpoint не являются текущими задачами.

Стабильный fallback — **V1.6 / versionCode 8**, pack V1.5 с прежними семью моделями.
Обычные ML-defaults остаются `v16`; context600, C2 и CPU `auto_v1` включаются явно,
старые задания сохраняют legacy-путь. Следовать [PLAN_19H.md](PLAN_19H.md)
с приоритетом §0.4 > §0.3 > §0.2 > §0.1: GigaAM v3 E2E и основная метрика raw WER
с пунктуацией и регистром. Общая приёмка проекта и естественных диалогов не заявлена.

Инструкции переноса ниже описывают базовый срез V1.6. Его исторический UI-цикл и
[отчёт V1.6](TEST_REPORT_V1_6.md) не заменяют актуальные проверки конвейера.

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
