C2 native collector v3: READY после независимого read-only review. Исходники/NN/build/ADB не изменялись и не запускались рецензентом. Владелец сообщил36focusedtestsPASS и actual --checkPASS; повторного запуска рецензентом не было.

ДоNN найдены и исправлены: (1) fullQA против compactRoom, (2) только математическое поле refiner.small_cluster_cutoff_ms:2000.0/2000, (3) missingsemanticSHA для native_policy/port_comparison, (4) localrawcapture при ненулевом instrumentationexit. В v3 допустимо только точное finite integral int↔Double равенство для указанного поля <=2^53; политика/clock/counters/BigInteger остаются строгими. Полная QA-диагностика и реальные vectors/tree продолжают независимый replay.

Проверены actualWorker/Evalbridge/sidecar, Float32параметры и nullableconfig, APK/model hashes, UUID/recordingID/clock, actualwindowcounts, word/timestamp→Juryreplay. Historicalfixed5 weightedrawWERgate(absΔ<=0.5п.п.) отделён от dev8count>=7/nativeDER<=fixed+0.02; union10 не расширяетWERgate. Остаточных блокирующих замечаний не найдено.

Полные SHA и история замечаний — native-c2-collector-review.json. Это готовность collection/reproducer, не результатAndroidquality/ARM/телефонной приёмки.
