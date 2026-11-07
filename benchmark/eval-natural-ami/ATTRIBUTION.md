# AMI natural-meeting diagnostic attribution

AMI Meeting Corpus signals and manual annotation release1.6.2: CC BY4.0,
according to https://groups.inf.ed.ac.uk/ami/download/ (2017 license update).
Attribute the AMI consortium and J. Carletta et al., The AMI Meeting Corpus: A
Pre-announcement (2006). The selected EN2002a/c meetings are naturally occurring
project discussions; speech references derive from manual word annotation.

RTTM benchmark setup: BUT Speech@FIT / F. Landini, J. Profant, M. Diez and
L. Burget, AMI-diarization-setup; pin/source URLs and SHA256 are in provenance.
Retain the accompanying Apache2.0 setup LICENSE and cite the benchmark setup.

Changes: first60-second PCM crop only; RTTM intervals clipped to that crop and
converted to integer milliseconds. No ASR, VAD, voice replacement or annotation
correction. Gold has blank text; this is speaker-diarization research only,
not English ASR task E. Audio stays outside Git/APK.

EN2002a headset/array are the same conversation/ground truth. EN2002a/c share
participants; this is not a speaker-disjoint sample. Candidate model training
overlap is unknown. This small diagnostic does not replace the original dev or
regression gates or establish general natural-dialogue performance.
