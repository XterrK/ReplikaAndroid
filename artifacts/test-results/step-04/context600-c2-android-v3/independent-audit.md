C2 actual Android native10: independent audit PASS, 564 проверок. Все10 sidecars и реальные512-мерныеvectors прошли C2replay; actualtokens→words→JuryJSON реконструированы, все основные метрики пересчитаны. Аудитор не запускалNN/ADB/build и не менял raw/source.

Historicalfixed5 rawWER: native43/442 противhost44/442, Δ=-0.226244п.п.; corpusgate absΔ<=0.5п.п. PASS. Perfileoutliers сохранены, остальныеdevфайлы не расширяютпулWER.

Отдельныйdev8: точноеK7/8, nativeDER0=18.298481%, rawWER70/533, normalizedWER16/532. Count>=7 иDER<=fixedV1.6+2п.п. PASS.

Проверены actualinstalledAPKhashes, all7remote/localmodelpins, build/source/config/catalog/input/reference/sidecarSHA, UUID/lifecyclecounts/releases и отсутствиеfallback/truncation. Всего344 реальныхwindows, 56 ASRchunks, 2169 tokens и767 wordproxies. Screenstay-on restored1.

| Файл | Rawerrors native/host | Rawturns equal | Exact common windows | Timestamp chunks differing |
| --- | --- | --- | --- | --- |
| dev-01-two-clean | 10/11 | True | 0/61 | 5 |
| dev-02-three-clean | 14/14 | True | 0/55 | 5 |
| dev-03-short | 6/6 | True | 0/16 | 1 |
| dev-04-expressive | 14/14 | True | 0/26 | 1 |
| dev-05-whisper | 5/5 | True | 0/14 | 2 |
| dev-06-overlap | 17/17 | True | 0/38 | 3 |
| dev-mono-m | 3/3 | True | 0/14 | 0 |
| dev-mono-s | 1/1 | True | 0/4 | 1 |
| holdout-02-three-clean | 16/16 | True | 0/69 | 6 |
| holdout-04-overlap-expressive | 10/10 | True | 0/47 | 7 |

Полные vector/text/token/timestamp/word различия пофайлам, доказательства иSHA — independent-audit.json. Не утверждается точное численное совпадениеNNмеждуhost/native; одинаковыйaggregateDER не доказывает его. x86timing uncontrolled, неcausal/ARM/телефонная/thermalприёмка. DER — montageproxy; AMInegative diagnostic остаётсяотдельным, безpooling/tuning/generalizationclaim. Это не полнаяприёмкапроекта.
