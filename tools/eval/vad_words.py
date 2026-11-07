"""Pure, experimental VAD-chunk and token-emission word planning.

Token emission frames are timing proxies, not forced-aligned acoustic word bounds.
No reference text or expected speaker count is accepted by these helpers.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import os
import re

if __package__:
    from .pipeline import Span, Turn, _f32, _kotlin_round_ms, merge_spans
else:
    from pipeline import Span, Turn, _f32, _kotlin_round_ms, merge_spans

SAME_FRAME = "Слова в одном кадре модели: проверьте границу"
NO_SPEAKER = "Не найден говорящий слова"
TIED_SPEAKER = "Неоднозначный говорящий слова"
OVERLAPPING_SPEAKERS = "Пересечение голосов в слове"
BOUNDARY_SPEAKERS = "Смена говорящего на границе слова"
SEAM_EDIT = "Пунктуация на границе реплики: проверьте текст"


@dataclass(frozen=True)
class Word:
    start_ms: int
    end_ms: int
    text: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class WordResult:
    supported: bool
    reason: str
    words: list[Word]


@dataclass(frozen=True)
class AssignedWord:
    start_ms: int
    end_ms: int
    text: str
    speaker: int
    reasons: tuple[str, ...] = ()


def normal_whitespace(text: str) -> str:
    return " ".join(text.split())


def plan_chunks(speech: list[Span], energy, max_ms: int = 20000, energy_split: bool = True,
                search_ms: int = 4000, window_ms: int = 40) -> list[Span]:
    """Choose a lowest-energy 40ms window, earliest tie, and cut at its center."""
    if min(max_ms, search_ms, window_ms) <= 0:
        raise ValueError("Chunk, search and window durations must be positive")
    result = []
    for span in merge_spans(speech):
        if span.start_ms < 0:
            raise ValueError("Speech must be bounded to the original clock")
        start = span.start_ms
        while start < span.end_ms:
            target = start + min(max_ms, span.end_ms - start)
            cut = target
            if energy_split and target < span.end_ms:
                first = max(start, target - search_ms)
                last = target - window_ms
                best_energy = math.inf
                for window_start in range(first, last + 1, window_ms):
                    value = float(energy(window_start, window_start + window_ms))
                    if not math.isfinite(value) or value < 0:
                        raise ValueError("Energy must be finite and nonnegative")
                    if value < best_energy:
                        best_energy = value
                        cut = window_start + window_ms // 2
            if not start < cut <= target:
                raise ValueError("Energy split must advance without exceeding maximum length")
            result.append(Span(start, cut))
            start = cut
    return result


def plan_vad_chunks(speech: list[Span], samples, max_ms: int = 20000,
                    energy_split: bool = True) -> list[Span]:
    def energy(start_ms, end_ms):
        start, end = start_ms * 16, end_ms * 16
        if start < 0 or end > len(samples) or end <= start:
            raise ValueError("Energy window exceeds canonical PCM")
        total = 0.0
        for raw in samples[start:end]:
            value = float(raw)
            total += value * value
        return total / (end - start)
    return plan_chunks(speech, energy, max_ms, energy_split)


def words_from_tokens(text: str, tokens: list[str], timestamps_seconds,
                       chunk_start_ms: int, chunk_end_ms: int,
                       frame_stride_ms: int | None) -> WordResult:
    def unsupported(reason):
        return WordResult(False, reason, [])
    if chunk_start_ms < 0 or chunk_end_ms <= chunk_start_ms:
        return unsupported("invalid_chunk")
    if not normal_whitespace(text):
        return WordResult(True, "empty_result", [])
    if type(frame_stride_ms) is not int or frame_stride_ms <= 0:
        return unsupported("unverified_frame_stride")
    if len(tokens) != len(timestamps_seconds) or not tokens:
        return unsupported("token_count_mismatch")
    if any(not isinstance(token, str) for token in tokens):
        return unsupported("invalid_token")
    converted = []
    previous = -math.inf
    duration = chunk_end_ms - chunk_start_ms
    for raw in timestamps_seconds:
        try:
            seconds = _f32(float(raw))
        except (ValueError, TypeError, OverflowError):
            return unsupported("nonfinite_timestamp")
        if not math.isfinite(seconds):
            return unsupported("nonfinite_timestamp")
        if seconds < previous:
            return unsupported("nonmonotonic_timestamps")
        previous = seconds
        try:
            local = _kotlin_round_ms(seconds)
        except (ValueError, OverflowError):
            return unsupported("nonfinite_timestamp")
        if seconds < 0 or local < 0 or local > duration:
            return unsupported("timestamp_out_of_range")
        if local % frame_stride_ms:
            return unsupported("timestamp_off_grid")
        converted.append(local)
    mapped = [token.replace("▁", " ") for token in tokens]
    for token in mapped:
        if sum(any(c.isalnum() for c in run) for run in re.findall(r"\S+", token)) > 1:
            return unsupported("multiword_token")
    reconstructed = "".join(mapped)
    if normal_whitespace(reconstructed) != normal_whitespace(text):
        return unsupported("text_roundtrip_mismatch")
    token_ranges = []
    offset = 0
    for index, token in enumerate(mapped):
        token_ranges.append((offset, offset + len(token), index))
        offset += len(token)
    words = []
    prefix = []
    for match in re.finditer(r"\S+", reconstructed):
        run = match.group()
        if not any(c.isalnum() for c in run):
            if words:
                words[-1] = replace(words[-1], text=words[-1].text + " " + run)
            else:
                prefix.append(run)
            continue
        participating = [index for a, b, index in token_ranges
                         if a < match.end() and b > match.start()
                         and any(c.isalnum() for c in reconstructed[max(a, match.start()):min(b, match.end())])]
        if not participating:
            return unsupported("no_lexical_words")
        start = chunk_start_ms + converted[participating[0]]
        end = min(chunk_end_ms, chunk_start_ms + converted[participating[-1]] + frame_stride_ms)
        if not chunk_start_ms <= start < end <= chunk_end_ms:
            return unsupported("word_outside_chunk")
        word_text = " ".join(prefix + [run])
        prefix = []
        words.append(Word(start, end, word_text))
    if not words:
        return unsupported("no_lexical_words")
    for index in range(len(words) - 1):
        current, following = words[index], words[index + 1]
        if following.start_ms > current.start_ms:
            words[index] = replace(current, end_ms=min(current.end_ms, following.start_ms))
        else:
            words[index] = replace(current, reasons=tuple(dict.fromkeys(current.reasons + (SAME_FRAME,))))
            words[index + 1] = replace(following, reasons=tuple(dict.fromkeys(following.reasons + (SAME_FRAME,))))
    if normal_whitespace(" ".join(w.text for w in words)) != normal_whitespace(text):
        return unsupported("text_roundtrip_mismatch")
    return WordResult(True, "supported", words)


def nearest_speaker(word: Word, turns: list[Turn], limit_ms: int, among=None) -> int:
    """Speaker of the closest known turn within limit_ms (0 = disabled); a tie keeps -1.

    Word times are token-emission estimates, so a word often lands a few hundred ms
    outside every diarization turn. Without this fallback it becomes its own
    unknown-speaker row with a tiny interval.
    """
    if limit_ms <= 0:
        return -1
    middle = (word.start_ms + word.end_ms) / 2
    best, best_distance = -1, None
    for turn in turns:
        if turn.speaker < 0 or (among is not None and turn.speaker not in among):
            continue
        if turn.start_ms <= middle < turn.end_ms:
            distance = -1  # the word centre lies inside this turn
        else:
            distance = max(0, turn.start_ms - word.end_ms, word.start_ms - turn.end_ms)
        if distance > limit_ms:
            continue
        if best_distance is None or distance < best_distance:
            best, best_distance = turn.speaker, distance
        elif distance == best_distance and turn.speaker != best:
            best = -2  # equally close different speakers: stay unknown
    return best if best >= 0 else -1


NEAREST_SPEAKER_MS = int(os.environ.get("REPLIKA_NEAREST_SPEAKER_MS", "1500"))  # app default; 0 = old behaviour


def assign_words(words: list[Word], turns: list[Turn]) -> list[AssignedWord]:
    result = []
    for word in words:
        active = [t for t in turns if t.speaker >= 0 and t.start_ms < word.end_ms and t.end_ms > word.start_ms]
        covered = {}
        for speaker in {t.speaker for t in active}:
            intervals = merge_spans([Span(max(word.start_ms, t.start_ms), min(word.end_ms, t.end_ms))
                                    for t in active if t.speaker == speaker])
            covered[speaker] = sum(t.end_ms - t.start_ms for t in intervals)
        reasons = list(word.reasons)
        if not covered:
            speaker = -1
            reasons.append(NO_SPEAKER)
        else:
            best = max(covered.values())
            candidates = [speaker for speaker, duration in covered.items() if duration == best]
            speaker = candidates[0] if len(candidates) == 1 else -1
            if speaker < 0:
                reasons.append(TIED_SPEAKER)
            if len(covered) > 1:
                simultaneous = any(a.speaker != b.speaker and
                    max(a.start_ms, b.start_ms, word.start_ms) < min(a.end_ms, b.end_ms, word.end_ms)
                    for i, a in enumerate(active) for b in active[i + 1:])
                reasons.append(OVERLAPPING_SPEAKERS if simultaneous else BOUNDARY_SPEAKERS)
        # Only a word outside every turn is rescued: ties and explicitly unknown native turns stay unknown.
        explicit_unknown = any(t.speaker < 0 and t.start_ms < word.end_ms and t.end_ms > word.start_ms for t in turns)
        if speaker < 0 and not covered and not explicit_unknown:
            speaker = nearest_speaker(word, turns, NEAREST_SPEAKER_MS)
        result.append(AssignedWord(word.start_ms, word.end_ms, word.text, speaker, tuple(dict.fromkeys(reasons))))
    return result


def seam_punctuation(text: str) -> str:
    value = text
    for index, char in enumerate(value):
        if char.isalpha():
            upper = char.upper()
            if len(upper) == 1:
                value = value[:index] + upper + value[index + 1:]
            break
    closing = "\"'»”’)]}"
    effective = len(value) - 1
    while effective >= 0 and (value[effective] in closing or value[effective].isspace()):
        effective -= 1
    if effective < 0 or value[effective] in ".!?…:;":
        return value
    if value[effective] in ",-—–":
        return value[:effective] + "." + value[effective + 1:]
    return value + "."


def group_words(words: list[AssignedWord], source: str,
                 punctuation_mode: str = "none") -> list[dict]:
    if punctuation_mode not in ("none", "seam"):
        raise ValueError("punctuation_mode must be none or seam")
    result = []
    for word in words:
        if result and result[-1]["speakerId"] == word.speaker:
            result[-1]["endMs"] = max(result[-1]["endMs"], word.end_ms)
            result[-1]["text"] += " " + word.text
            result[-1]["warnings"] = list(dict.fromkeys(result[-1]["warnings"] + list(word.reasons)))
        else:
            result.append({"startMs": word.start_ms, "endMs": word.end_ms,
                           "speakerId": word.speaker, "text": word.text,
                           "source": source, "warnings": list(word.reasons)})
    # Only a speaker split creates a seam. An unsplit ASR chunk keeps the model's
    # exact punctuation and case, including when the optional rule is selected.
    if punctuation_mode == "seam" and len(result) > 1:
        for segment in result:
            changed = seam_punctuation(segment["text"])
            if changed != segment["text"]:
                segment["warnings"] = list(dict.fromkeys(segment["warnings"] + [SEAM_EDIT]))
            segment["text"] = changed
    return result
