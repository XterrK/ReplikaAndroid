Final C2 native-parameter probes: independent audit PASS, 3648 проверок, все32actualSD+windowNNdevcases. Все4альтернативы отвергнуты по заранее зафиксированному выбору; baselineC2неизменён.

| Профиль | Shift | MinOff | Kexact | NativeDER0 | Selection |
| --- | --- | --- | --- | --- | --- |
| baseline-existing | .1 | .5 | 7/8 | 18.298481% | retain |
| off-0p25 | 0.1 | 0.25 | 6/8 | 21.613409% | reject |
| off-1p0 | 0.1 | 1.0 | 4/8 | 19.799890% | reject |
| shift-0p25 | 0.25 | 0.5 | 5/8 | 18.980655% | reject |
| shift-0p5 | 0.5 | 0.5 | 4/8 | 24.221100% | reject |

Проверены source/model/input/reference/runtimeSHA, SDKFloat32bits всехminOn/minOff/shift/threshold,32freshSDcalls и902реальных512-dimensionalembeddingcalls сbalancedrelease; exactpureC2replay, actualcachedDword→Juryreplay, literal/rawWER71/533 во всех4полныхdev8профилях и независимый пересчётметрик/summary.

ГраницаSDKmetadata new_neural_inference=false относится только к чтениюconfig; actualcaseSD/windows NNотмечены отдельноtrue. ASRнеповторялся. Holdout/reserve/AMI не использовались длявыбора. Это финальнаяпроверкарекомендации minOff иselectedC2shift, а не новыйCgate/CPUтюнинг. RejectedvariantsнепереносятсявAPK; прежниеbaselinevalidationsсохраняются. Concurrenttimings не означаютускорение/fullpipelineRTF/ARM/телефоннуюприёмку. Raw/code/models/mainнеизменялись.
