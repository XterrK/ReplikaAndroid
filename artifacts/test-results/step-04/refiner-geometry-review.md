# Saved refiner geometry review

The current centroid merger has two separate limitations: it can combine
predicted labels, but it cannot split different acoustic patterns already inside
one label; its small-cluster stage can also remove a measured short label without
strong identity evidence. These are hypotheses to test on full dev, not reasons
to relax the count or DER gates.

The accompanying `refiner-geometry-review.json` records 31 verified saved source
cases: all eight baseline clean-window cases and partial `.30`/`.50` snapshots
from the two running automatic grids. It also records 112 complete baseline
temporal-refiner case/threshold traces. Every completed case passed its stored
evidence hashes; failures are empty. Source grids were still RUNNING at capture,
so these snapshots do not establish a full model comparison.

Geometry uses only predicted turns and their actual measured windows. It uses
the existing normalization and duration-weighted centroid helpers. No reference
text was parsed, no gold count entered geometry, no outputs or settings were
adjusted, and no audio or neural inference was performed. Reference counts and
DER were read from existing scorer records solely to explain saved failures.

## Short file: a heterogeneous label plus a duration-only collapse

For `dev-03-short`, baseline ERes2Net and both `.30`/`.50` ERes2Net/ResNet runs
have identical native intervals:

| Predicted label | Union activity | Real clean windows | Observation |
| --- | ---: | ---: | --- |
| 0 | 14,411 ms | 15 | Four long native islands contain broad acoustic variation |
| 1 | 1,890 ms | 1 | Measured centroid exists, but activity is below the 2,000 ms small cutoff |

Within label 0, ERes2Net window-pair cosine has median **0.384760**, minimum
**0.089326**, and maximum **0.822564**. The corresponding mono controls have
medians **0.628472** and **0.682945**. ResNet's same-label short-file median is
**0.460555**, with minimum **0.266386**. The JSON also excludes overlapping
window pairs in a separate summary, because shared samples can inflate cohesion.

Recurring patterns are present across distant times: ERes2Net windows
`352–1852 ms` and `6232–7732 ms` have cosine **0.736266** despite sharing no
samples. Other pairs inside that same native label are much less similar.
Chronological cosine matrices, spectra and graph components across the global
threshold range are retained in JSON. They support heterogeneous or potentially
mixed native activity. They do **not** prove exactly two acoustic modes or human
identities; short duration, emotion, phonetic content and noise remain confounds.

The two native-label centroids have cosine **0.499778** for ERes2Net and
**0.579930** for ResNet. At the saved baseline temporal threshold 0.60, the
refiner performs no cosine or eigengap merge; eigengap estimates K=2. The
small-cluster rule alone assigns label 1 to label 0, reducing K=2 to K=1.
Thus this loss is neither a missing-embedding fallback nor an eigengap failure.
Keeping K=2 would still not establish correct diarization: the saved native
partition already has poor DER. A window-level split can test information lost
by one-centroid-per-native-label aggregation, without claiming acceptance first.

## Three-speaker count failures arise at different stages

At the illustrative saved threshold 0.60:

- `dev-02-three-clean` starts with six measured centroids and no missing labels.
  Four cosine merges produce two groups. Their successive similarities are
  0.719093, 0.725, 0.696026 and 0.670 (full precision and memberships in JSON).
  No eigengap reduction or small assignment occurs. Within-label window medians
  span roughly 0.446–0.627, so high centroid similarity does not establish clean
  speaker identity inside each native label.
- `dev-04-expressive` has five native labels, but label 4 contains only 304 ms
  and has no feasible 1,000 ms clean island. Two cosine merges leave three groups;
  temporal fallback then absorbs this unmeasured label, leaving two. That
  fallback collapses 287 ms of simultaneous speaker activity. It provides no
  acoustic identity evidence for the absorbed fragment.
- `dev-05-whisper` retains a correct count of three at this threshold while its
  saved native DER remains 62.62%. Correct K alone does not establish the correct
  partition or justify promotion.

All 112 saved baseline-temporal traces preserve the original speech-activity
**union** exactly. This does not preserve overlapping speaker-time when labels
are merged, and does not imply correct identities. JSON separately records
overlap-collapse durations and every actual merge, small assignment and smoothing
decision. An eigengap estimate is counted as a reduction only when a saved merge
is explicitly marked `stage=eigengap`.

## Gate remains unmet

The fixed-production comparison has native DER0 **26.885182%**, so the existing
limit is **28.885182%**, with at least **7/8** exact native counts required.
Baseline temporal tau 0.35 has DER0 **27.212563%** but only **3/8** correct counts.
Tau 0.60 reaches **5/8** counts but DER0 **31.626723%**. No global tau in this
saved baseline grid meets both criteria. The distinction between these failures
must remain visible; count-only selection would hide poor partitions.

No profile, model or Android policy was promoted by this review. The next
window-level overclustering experiment remains a host-only hypothesis and must
pass the unchanged full dev and separate regression checks.
