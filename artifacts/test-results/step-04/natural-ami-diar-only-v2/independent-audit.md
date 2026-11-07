AMI natural diagnostic: audit integrity/recalculation PASS, 6288 проверок, все9 свежих SD case-profile outputs. Рецензент не запускалNN/ASR/VAD/LID/build/ADB и не менял raw/source.

| Профиль | Crop | K ref→final | DER0 | DER250 |
| --- | --- | --- | --- | --- |
| legacy-v16 | ami-natural-en2002a-headset-first60 | 4→10 | 67.6455% | 63.8147% |
| c1-centroid | ami-natural-en2002a-headset-first60 | 4→5 | 43.6296% | 39.1744% |
| c2-window | ami-natural-en2002a-headset-first60 | 4→6 | 42.9352% | 37.7715% |
| legacy-v16 | ami-natural-en2002a-array-first60 | 4→13 | 60.6465% | 55.1936% |
| c1-centroid | ami-natural-en2002a-array-first60 | 4→1 | 66.6114% | 63.2545% |
| c2-window | ami-natural-en2002a-array-first60 | 4→8 | 49.8849% | 45.6543% |
| legacy-v16 | ami-natural-en2002c-headset-first60 | 3→6 | 57.9461% | 56.2620% |
| c1-centroid | ami-natural-en2002c-headset-first60 | 3→3 | 54.8480% | 54.4856% |
| c2-window | ami-natural-en2002c-headset-first60 | 3→5 | 60.2255% | 58.3014% |

C2: точное K0/3, предсказано6/8/5 приэталоне4/4/3. НаEN2002c-headset DER0 ухудшился с57.946078% до60.225490%, +2.279412п.п. Это отрицательный диагностический результат, а не PASS качества.

Проверены source/model/catalog/lock/audio/RTTM/reference/runtime SHA, независимое Decimalвосстановлениеgold, Float32rawclock/stablelabels, DER0/250/K всехraw/stable/finalturns, реальныеvectors и exactpureC1/C2replay, lifecyclecounts/resources иNNmarkers. Всего9SDcalls; ASR/VAD/LID не запускались.

EN2002a headset/array — таже беседа и gold; a/c имеют общих участников.180s channel-time соответствуют120s уникальных meetingcrops. Trainingoverlap неизвестен. Агрегаты только описательные, это не независимые splits. Не объединятьK сdev, не использоватьдляподбора/новогоgate, не заявлять generalization/Android/phone/speedacceptance. Все исходные артефакты сохранены.
