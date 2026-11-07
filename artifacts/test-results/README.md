# Сырые результаты тестов

Здесь лежат все исходные данные проверок: эталоны, ответы приложения, диагностика,
метрики, логи сборок и устройств. Человеческое описание и итоговые таблицы —
в [docs/TEST_RESULTS.md](../../docs/TEST_RESULTS.md).

Сохраняются и неудачные попытки: папки с `failed`, `attempt01` или пометкой FAIL
в отчёте не удалялись и не переписывались.

## Как устроен прогон

Каждый прогон стенда — отдельная папка. Внутри:

| Файл | Что это |
| --- | --- |
| `config.json` | Параметры конвейера |
| `manifest.json` | Список файлов и их SHA-256 |
| `summary.json` | Итоги по наборам dev / holdout / всем: ошибки, знаменатели, DER, число говорящих, RTF |
| `results.csv` | Одна строка на файл |
| `<id файла>/reference.json` | Эталон (авторский текст и интервалы) |
| `<id файла>/hypothesis.json` | Что выдало приложение |
| `<id файла>/diagnostics.json` | Токены, времена, стадии, ресурсы |
| `<id файла>/metrics.json` | Все метрики по файлу |
| `independent-audit.json` | Независимый пересчёт метрик из сохранённых файлов (где есть) |

## Индекс по этапам

### step-00 — сохранение исходного состояния

Снимок V1.6 до начала доработок и проверка публикации.
Главное: [preservation.json](step-00/preservation.json).

### step-01 — JSON в формате жюри

Экспорт строго по схеме `transcript / speaker_id / start_ms / end_ms / text`,
автоматический режим говорящих по умолчанию.
Главное: [acceptance.json](step-01/acceptance.json), JSON из интерфейса — в [android/](step-01/android).

### step-02 — стенд оценки и исходные цифры V1.6

| Что | Где |
| --- | --- |
| V1.6 на ПК, 13 файлов | [baseline-v16-host-android-decoder/summary.json](step-02/baseline-v16-host-android-decoder/summary.json) |
| V1.6 на эмуляторе, 5 файлов | [baseline-v16-android/](step-02/baseline-v16-android) |
| Сравнение ПК и эмулятора | [port-comparison-user-gate/comparison.json](step-02/port-comparison-user-gate/comparison.json) |
| Совпадение декодирования звука ПК и Android | [decoder-parity/](step-02/decoder-parity) |

### step-03 — распознавание по фрагментам речи

| Что | Где |
| --- | --- |
| Все варианты на dev одной таблицей | [results.csv](step-03/results.csv) |
| Выбранный вариант (600 мс контекста), ПК, 13 файлов | [context600-selected-host/summary.json](step-03/context600-selected-host/summary.json) |
| V1.6 и выбранный вариант на reserve | [reserve-v16-host/](step-03/reserve-v16-host), [reserve-context600-host/](step-03/reserve-context600-host) |
| Эмулятор, 5 файлов | [android-quality-gate.json](step-03/android-quality-gate.json), [context600-android/](step-03/context600-android) |
| Отклонённый первый кандидат | [comparison-selected-host/report.md](step-03/comparison-selected-host/report.md) |

### step-04 — диаризация

| Что | Где |
| --- | --- |
| Итог: текущий конвейер на ПК, 13 файлов | [candidate-c2-full-original/summary.json](step-04/candidate-c2-full-original/summary.json) |
| Итог: текущий конвейер на ПК, reserve | [candidate-c2-full-reserve/summary.json](step-04/candidate-c2-full-reserve/summary.json) |
| Эмулятор, 10 файлов | [context600-c2-android-v3/](step-04/context600-c2-android-v3) |
| Шесть моделей отпечатка голоса с известным K | папки `fixed-*` |
| 84 автоматических профиля | [acceptance-native-overview-v2.json](step-04/acceptance-native-overview-v2.json), [acceptance-native-results-v2.csv](step-04/acceptance-native-results-v2.csv) |
| Отклонённые параметры сегментации | [final-native-parameter-audit.json](step-04/final-native-parameter-audit.json) |
| Естественные совещания AMI | [natural-ami-diar-only-v2/results.csv](step-04/natural-ami-diar-only-v2/results.csv) |
| Происхождение и лицензии моделей | [model-provenance.md](step-04/model-provenance.md) |
| Описание папок этапа | [README.md](step-04/README.md) |

### step-05 — потоки CPU, термоконтроль, импорт, телефон

| Что | Где |
| --- | --- |
| Телефон vivo X300, 10 файлов: качество | [vivo-arm-full10-audited-v2/](step-05/vivo-arm-full10-audited-v2) |
| Телефон, файлы 1 / 3 / 10 мин: скорость | [vivo-perf-one-audited-v2/](step-05/vivo-perf-one-audited-v2) |
| ПК, 1 / 2 / 4 потока | [cpu-host-threads1/](step-05/cpu-host-threads1), [cpu-host-threads2/](step-05/cpu-host-threads2), [cpu-host-threads4/](step-05/cpu-host-threads4) |
| Эмулятор, 2 потока и автоподбор | [cpu-android-control2-v1/](step-05/cpu-android-control2-v1), [cpu-android-auto1-v1/](step-05/cpu-android-auto1-v1) |
| Импорт 13 форматов | [android-import-thermal-v1/summary.json](step-05/android-import-thermal-v1/summary.json) |
| Термоконтроль | [android-thermal-v2/summary.json](step-05/android-thermal-v2/summary.json) |
| Системный выбор файла | [android-picker-v1/](step-05/android-picker-v1) |
| Android-регрессия, 27 тестов | [android-regression-v1/summary.json](step-05/android-regression-v1/summary.json) |
| Сборка, JVM-тесты | [build-auto-v2/summary.json](step-05/build-auto-v2/summary.json) |
| Эмулятор с 16 КБ-страницами | [ps16k-android-one-v1/](step-05/ps16k-android-one-v1) |
| Сохранность данных при обновлении на телефоне | [vivo-prior-data-preservation-after-long3-v1.json](step-05/vivo-prior-data-preservation-after-long3-v1.json) |
| Незавершённая серия скорости на эмуляторе (FAILED) | [perf-2-4-4-2-v1/run.json](step-05/perf-2-4-4-2-v1/run.json) |

### Следующие этапы

| Что | Где |
| --- | --- |
| Английский язык и определение языка | [step-07](step-07/) |
| Длинные записи, диаризация окнами | [step-06](step-06/) |
| Импорт больших файлов, лимиты Android 15, прогресс | [step-08](step-08/) |
| Отклонённый эксперимент с пунктуацией на стыках | [docs/STEP_10_PUNCT_BRIDGE.md](../../docs/STEP_10_PUNCT_BRIDGE.md) |
| Сквозные прогоны интегрированной сборки на телефоне и эмуляторе, финальный RTF | [step-12-device](step-12-device/README.md) |

## Что не попадает в репозиторий

- Аудио тестового корпуса — скачивается скриптом из открытого набора
  (см. [benchmark/eval](../../benchmark/eval/README.md)).
- Личные данные с телефона: база данных, серийный номер, системные дампы.
  В репозитории только очищенные результаты.
- Веса моделей и APK — в GitHub Releases.
