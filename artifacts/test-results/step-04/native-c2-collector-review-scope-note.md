Уточнение scope review: формулировка «R1–R4 исправлены до NN» относится только к запуску полного collector10, а не к отсутствию всех прежних C2 neural smoke. Независимый single-case driver уже выполнил NN+ASR.

Smokev1 начался2026-11-07T02:07:39.297784Z (05:07:39+03): Worker обработал запись за10259ms, измерил4реальных512-мерныхвектора, streams/extractor освобождены, refinementaccepted=true. QAпубликация получилаAccessDeniedException, evidenceTruncated=true; instrumentation/report остаютсяFAILED. Это не успешнаяQAприёмка.

Smokev2 начался02:22:44.486967Z (05:22:44+03), завершился02:22:57.485117Z: SMOKE_PASS, Worker8331ms, теже4реальныхвектора, QAнеусечена. Это функциональныйsinglecase, неcorpus/core/ARM/телефоннаяприёмка. Терминальные попытки fullcollectorv1/v2 были отдельными pre-NNошибками запуска.

Первоначальныйreview и все rawNN/JSONсохранены безизменений. ПроверенныеSHA и точныеполя — в native-c2-collector-review-scope-note.json. РецензентNN/build/ADB не запускал.
