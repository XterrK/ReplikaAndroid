# Пункт 3 — ASR по VAD и словное назначение спикеров

Состояние на 2026-11-07T02:11:11+03:00. **Host quality gate PASS; Android quality/port gate PASS. Полная приёмка конвейера не установлена (`full_pipeline_acceptance=false`), цель времени слов <200 мс не проверена (`word_timing_acceptance=null`).** Обычная сборка сохраняет `v16`; кандидат включается явно через `-PreplikaAsrPlan=vad_words_context600`. Первый выбранный профиль отклонён и сохранён вместе с его результатами.

Веса GigaAM v3 E2E RNNT INT8, Silero, segmentation и embedding не заменялись. Основная метрика по §0.4 — raw WER с пунктуацией, регистром, ё и цифрами. WER и число ошибок должны уменьшаться; доля точного числа спикеров — увеличиваться. Разница host/Android является отдельной проверкой порта.

Host и Android распознают VAD chunks длиной до 20 с; длинный chunk режется по минимуму 40-мс mean-square энергии внутри последних 4 с исходного PCM. Реальные sherpa tokens склеиваются с учётом ASCII-пробелов, отдельных пробелов и `▁`. Проверяется Float32 clock со stride 40 мс. Слова назначаются по максимальному union-overlap с native turns; равенство/отсутствие остаётся unknown. Группировка выполняется отдельно внутри каждого ASR chunk. Выбранный context600 сохраняет VAD .5/.25/.25, добавляет 600 мс реального аудио перед речью, использует energy split и не включает seam-пунктуацию.

Token emission frames — оценки времени выхода токенов, без независимой калибровки или forced alignment. При неподдержанной разметке сохраняется настоящий ASR-текст всего chunk с unknown speaker и предупреждением; повторного ASR или выдуманных словных времён нет. Координаты первого/последнего слова сохраняются. Реализации: [Kotlin planner](../app/src/main/java/ru/replika/domain/VadWordPlanner.kt), [Python planner](../tools/eval/vad_words.py), [Worker](../app/src/main/java/ru/replika/ml/ProcessingWorker.kt), [AsrPlan](../app/src/main/java/ru/replika/domain/AsrPlan.kt).

Новый Worker содержит отдельный word-путь; прежний recognition loop сохранён. План передаётся явно в WorkManager; задания без сохранённого `asrPlan` выполняются через legacy. QA сохраняет реальные tokens/timestamps/words только при `collectWordEvidence=true`; в обычной обработке остаются сводки. Дополнительный payload ограничен 256 KiB, а native collector отклоняет неполные/усечённые доказательства. Семь полей policy, включая `pre_roll_ms`, проверяются [строго](../tools/eval/native_policy.py).

Все 11 dev-прогонов сохранены с reference/hypothesis/diagnostics/metrics/case JSON и config/code/input/model fingerprints. [Индекс](../artifacts/test-results/step-03/results.csv) и [source snapshots](../artifacts/test-results/step-03/source-snapshots) сохраняют также промежуточные версии. Baseline dev: 124/533 raw, 39/532 normalized, 2 удаления в short-кейсе.

| Dev run | Raw errors / WER ↓ | Normalized errors ↓ | Short deletions ↓ |
| --- | ---: | ---: | ---: |
| vad-words-none-dev | 93/533 (17.448%) | 26/532 | 2 |
| none-v2-dev | 93/533 (17.448%) | 26/532 | 2 |
| seam-dev | 116/533 (21.764%) | 26/532 | 2 |
| short15-dev | 92/533 (17.261%) | 22/532 | 2 |
| short10-dev | 99/533 (18.574%) | 20/532 | 0 |
| sensitive-dev | 89/533 (16.698%) | 22/532 | 2 |
| seam-v3-dev | 110/533 (20.638%) | 26/532 | 2 |
| short10-seam-dev | 119/533 (22.326%) | 20/532 | 0 |
| sensitive-short10-dev | 96/533 (18.011%) | 18/532 | 0 |
| context300-dev | 84/533 (15.760%) | 21/532 | 0 |
| context600-dev | 71/533 (13.321%) | 16/532 | 0 |

Первый отбор sensitive-short10 был [заморожен до holdout](../artifacts/test-results/step-03/candidate-selection.json). Свежий all13 повторил dev 96/533 raw и 18/532 normalized, но holdout дал **78/444 против baseline 73/444**, поэтому профиль **отклонён**. Улучшение normalized 16/442 против 24/442 не отменяет raw gate. [Отчёт отклонённого профиля](../artifacts/test-results/step-03/comparison-selected-host/report.md) и исходные результаты остаются неизменными.

Во второй итерации context600 [выбран по dev](../artifacts/test-results/step-03/candidate-selection-iteration2.json) до проверки нового reserve. Старый holdout уже использован после первой итерации и служит отдельной regression validation. [Reserve](../benchmark/eval-reserve/manifest.json) содержит 10 файлов, 60 новых исходников, 367.423 с; metadata-only отбор заморожен до выбора кандидата, selection SHA256 `015045aa2b98a70cb6f8c3c82ebb2dee783023faa72740b3b1ec249d17b67656`. [Validation](../benchmark/eval-reserve/validation.json) и [disjointness](../benchmark/eval-reserve/disjointness.json) фиксируют исходники и воспроизводимость. Первый FAIL не заменяется и не усредняется с reserve.

| Host набор | Baseline raw ↓ | Context600 raw ↓ | Baseline normalized ↓ | Context600 normalized ↓ |
| --- | ---: | ---: | ---: | ---: |
| Прежний dev, 8 файлов | 124/533 (23.265%) | 71/533 (13.321%) | 39/532 | 16/532 |
| Прежний holdout, 5 файлов | 73/444 (16.441%) | 49/444 (11.036%) | 24/442 | 13/442 |
| Новый reserve, 10 файлов | 135/743 (18.170%) | 83/743 (11.171%) | 42/744 | 24/744 |

[Host gate](../artifacts/test-results/step-03/host-quality-gate.json) проверяет исходные dev/holdout, short D=0 на dev и отсутствие raw/normalized регрессии на reserve отдельно. Все 23 candidate cases поддержали word projection без fallback. [Host audit: 2131/2131 PASS](../artifacts/test-results/step-03/host-audit.json) пересчитал метрики из сохранённых reference/hypothesis и проверил hashes. Generic combined gate [reserve-отчёта](../artifacts/test-results/step-03/comparison-reserve-context600-host/report.md) остаётся `PENDING_UNEVALUATED_SPLIT`, поскольку в нём только holdout; это отражено в отдельном host gate. [Полное сравнение прежних 13 файлов](../artifacts/test-results/step-03/comparison-context600-selected-host/report.md).

**Android: пять фактических Worker cases на x86_64 API35 AVD.** [Quality/port gate PASS](../artifacts/test-results/step-03/android-quality-gate.json): raw **43/442 (9.729%)** против фактической V1.6 baseline **75/442 (16.968%)**. Парный host context600 дал 44/442; native-minus-host delta **−0.226 п.п.**, в пределах согласованного weighted corpus gate 0.5 п.п. по фиксированной пятёрке. Это отдельное сравнение от baseline/candidate WER. У `dev-01-two-clean` сохранён per-file outlier **−0.714 п.п.**, per-file PASS ему не присваивается.

[Native audit: 463/463 PASS](../artifacts/test-results/step-03/native-audit.json) восстановил интервалы слов, спикеров, причины warnings и Jury JSON из фактических native tokens/timestamps/turns: 32 chunks, 1224 токена/timestamp, 434 слова; evidence полный, fallback/truncation отсутствуют. Сохранены два буквальных расхождения host/native: `идеально!` / `идеально.` и `кунсткамеру` / `консткамеру`, а также сдвиг одной Jury-границы на 40 мс и различия emission frames. Установленная причина этих межплатформенных различий отсутствует. [Исходный native run](../artifacts/test-results/step-03/context600-android/run.json), [различия](../artifacts/test-results/step-03/native-port-differences.json), [policy negative proof](../artifacts/test-results/step-03/native-negative-policy-proof.json).

Ограничения остаются существенными. Native DER и автоматическое число спикеров не изменились; точное число кластеров — 2/8 dev, 2/5 прежнего holdout, 1/10 reserve (выше лучше). Candidate cpWER raw: 77.861% / 97.973% / 74.159%. Покрытие эталонных интервалов: 88.889% / 93.750% / 86.667%; медианная ошибка конца: 500 / 462.5 / 513 мс. Корпуса — монтажи независимых author clips с coarse utterance intervals, без независимой словной разметки: DER/timing являются proxy. Эти числа не подтверждают цель <200 мс, живой диалог или физический микрофон.

[Контроль времени](../artifacts/test-results/step-03/performance-control.md) на одном файле в текущем APK дал legacy RTF **4.739**, word RTF **4.605**, исторический legacy **1.185**. Диаризация заняла соответственно **219381 / 217471 / 50710 мс**. Высокое время воспроизводится и legacy-путём текущего APK; причина отличия от исторического замера не установлена. Один контрольный файл не доказывает ускорение алгоритма. Общая performance acceptance, ARM/телефон, peak RAM, thermal и battery ещё не подтверждены; неконтролируемый host RTF не заменяет эти проверки.

Проверки: [125 Python PASS](../artifacts/test-results/step-03/python-checks/summary.json), [111 JVM PASS](../artifacts/test-results/step-03/jvm/summary.json); [All-in-One/debug/test APK build PASS](../artifacts/test-results/step-03/build.log), [ARM64 static verification PASS](../artifacts/test-results/step-03/apk-verification.json). [Pure Kotlin/Python parity](../artifacts/test-results/step-03/word-planner-parity-v3/report.json): 282 cases без различий (278 реальных сохранённых token slices + 4 controlled); это проверка чистых функций, не 282 модельных прогона.

UI-регрессия [PASS: 2/2 за 18.633 с](../artifacts/test-results/step-03/ui/summary.json), [повторный лог](../artifacts/test-results/step-03/ui/attempt2.log). В [attempt1 — 1/2 PASS](../artifacts/test-results/step-03/ui/attempt1.log) assertions JSON и запись proof завершились, затем ожидание фокуса после Back из второго chooser достигло timeout. Исправлено только ожидание готовности chooser в тесте. [Jury JSON](../artifacts/test-results/step-03/ui/jury.json), [diagnostic JSON](../artifacts/test-results/step-03/ui/diagnostic.json) и [scope](../artifacts/test-results/step-03/ui/scope.json) фиксируют экспорт обоих форматов через UI без перезаписи Jury-файла на controlled fixture, без нового inference. [Main APK native5/control сохранён](../artifacts/test-results/step-03/installed-artifacts.json) и побайтово не изменился после замены test APK.

[APK preservation PASS](../artifacts/test-results/step-03/apk-preservation.json): прежние V1.6 и пункт 1 побайтово сохранены; все три APK имеют один signer certificate SHA256 `f40399356577bcd0a5c220818ba13e9686768a02830a7f6e3af81d5a487947ab`.

| APK | SHA256 |
| --- | --- |
| `release/fallback/REPLIKA-V1.6-AllInOne-arm64.apk` | `dec7523de9403248358a5b590f12069be47e821460cb6095af4c1424edb7febd` |
| `release/REPLIKA-Hack-Step01-AllInOne-arm64.apk` | `cc71c0a811d1d35efdc4186638898234a21171e21bebb1d8df75e67a454c53e5` |
| `release/REPLIKA-Hack-Step03-Context600-AllInOne-arm64.apk` | `048c42fd1ad6f48db10c90583baae3a94ad389ef4e6a9dbb50535879b442ae9d` |

[FP32 feasibility](../artifacts/test-results/step-03/fp32-feasibility.json): готовый FP32 encoder той же pinned ONNX-поставки не найден. PyTorch checkpoint требует отдельного контролируемого экспорта; такого A/B не выполняли. Production default остаётся legacy из-за открытых diarization, word-timing и performance осей. Следующий пункт C не начат; LLM, Lite-APK и лендинг также не начаты.
