# Пункт C: данные, модели и проверки

Основной читаемый отчёт: [STEP_04_DIARIZATION.md](../../../docs/STEP_04_DIARIZATION.md).
Текущий статус работы: [STATUS.md](../../../docs/history/root/STATUS.md). WER/DER/cpWER — ошибки,
меньше лучше; точное число говорящих — доля успешных файлов, больше лучше.

## Проверенный контрольный профиль C2

Исходный ERes2Net, native threshold0,30/shift0,1/minOff0,5,
измеренные чистые окна1,5с/шаг0,75с, averageHCτ0,36, малые кластеры2с/3%,
сглаживание500мс. Те же семь весов, без новых моделей в APK.

| Проверка | Доказательства |
| --- | --- |
| Выбор и dev-протокол до validation | [freeze](candidate-c2-validation-freeze.json), [fine-протокол](../../../configs/eval/diar-protocol-window-fine-v1.json) |
| Host: dev7/8, holdout4/5, reserve5/10 | [отдельные gates](candidate-c2-validation-gates/summary.json) |
| Полный новый NN на13+10 записях | [original](candidate-c2-full-original/summary.json), [reserve](candidate-c2-full-reserve/summary.json), [3164-check audit](full-c2-equivalence-audit.json) |
| Настоящий Android10/10 | [run](context600-c2-android-v3/run.json), [CSV](context600-c2-android-v3/results.csv), [независимый аудит](context600-c2-android-v3/independent-audit.json) |
| Честные межплатформенные различия | [native audit](context600-c2-android-v3/independent-audit.md): вектора не побайтно равны, текстовые/временные различия сохранены |
| APKv2:173JVM/static/signature | [сборка](build-c2-v2/summary.json), [static](apk-static-v2.json) |
| Python337/код неизменён во время тестов | [summary](python-integrated-v5/summary.json) |
| Два UI-теста текущего APK | [результат](ui-v3/summary.json) |
| Реальный smoke + Python replay | [smoke](native-c2-smoke-v2/run.json), [проверка](native-c2-smoke-v2/pure-validation.json) |

Фиксированная Android-пятёрка: raw43/442=9,7285%, host44/442=9,9548%,
Δ−0,226244п.п. Порог0,5п.п. относится только к этой пятёрке; per-file выброс сохранён.
Androiddev8: raw70/533, normalized16/532, K7/8, nativeDER0=18,2984805764%.
344реальных512dimвектора и56ASRчанков сохранены в10полныхQAфайлах.
Это AOSP API35/x86_64, не ARM/телефонная скорость и не общая точность диалогов.

## Исследование и неудачные варианты

- [Каталог/происхождение/лицензии](model-provenance.md): шесть моделей,
  48fixed-K и672automatic SD-вызова. FixedK — исследовательский oracle.
- [Независимый аудит84nativeпрофилей](acceptance-native-overview-v2.json):
  все профили без дополнительной постобработки не прошли совместные count/DER критерии.
- C1 centroid/eigengap реализован наPython/Kotlin; [274parity](kotlin-refiner/differential-report.json).
  [Абляция](refiner-ablation-baseline-v1/results.csv) сохраняет варианты без eigengap и другие стадии.
- C2 — отдельная измеренная window-HC альтернатива. Его выбранное разбиение не управляется
  eigengap; [157parity](kotlin-window-refiner/differential-report.json) этого алгоритма сохранены.
- [Проверка named требований](c-requirements-audit-pending.md) отделяет подтверждённые C-gates
  от оставшихся общих задач ARM/скорости/word-time/финальной сдачи.
- [Финальный dev-only minOff/shift протокол](../../../configs/eval/c2-final-native-parameters-v1.json)
  закрывает дополнительную рекомендацию подбора параметров. Контрольный APK сохраняется;
  32 новых SD-вызова завершены; все четыре варианта отвергнуты.
  [Итог выбора](final-native-parameter-selection.json).

Ранние проекции использовали реальные сохранённые D-ASR токены и явно помечены как replay.
Поздние полные C1/C2 host и Android-прогоны повторили NN. Файлы reference/hypothesis/metrics,
исходные turns, реальные эмбеддинги, CSV, code/config/model/runtime fingerprints сохранены.
Аудиторы и исторические версии runner находятся в [runner-snapshots](runner-snapshots/README.md).

## Естественная встреча и границы

[AMI:9SD-прогонов](natural-ami-diar-only-v2/summary.json),
[6288-check независимый аудит](natural-ami-diar-only-v2/independent-audit.json).
C2K6/8/5 при gold4/4/3:0/3; на третьем фрагменте DER хужеlegacy на2,2794п.п.
Два микрофона одной беседы и общие участники не являются независимыми split.
По этому диагностическому набору параметры не подбираются.

В full-project acceptance остаются открыты независимые границы слов, ARM/телефонная
скорость, CPU/thermal/import, английский/стерео и финальная сдача. Обычный source-default
и исторические WorkData/manualK сохраняютv16; старые APK не заменяются.

Неудачные попытки остаются данными: [SELinux hardlink](diarization-evidence-link-failure-v1/failure.json),
[до-NN SciPy import](natural-diar-runtime-import-failure-v1/failure.json), [спящий UI](ui-v1/summary.json),
[full-launch1](context600-c2-android-v1/run.json), [full-launch2](context600-c2-android-v2/run.json).
Они не являются успешными модельными прогонами и не получают выдуманные метрики.
