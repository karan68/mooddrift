"""
Voice biomarker extraction and incongruence detection.

Per FEATURES.md "Feature 1: Emotional Voice Biomarkers":

Analyzes the *acoustic properties* of every voice note — not just the transcript.

Features extracted (per voice note):
  - pitch_mean (Hz)        — average fundamental frequency on voiced frames
  - pitch_std (Hz)         — pitch variability (low std = flat affect signal)
  - speech_rate (syl/sec)  — syllables per second (estimated from transcript)
  - pause_ratio (0..1)     — fraction of audio that is silence
  - energy_mean (RMS)      — average loudness/energy
  - jitter (relative)      — micro pitch variation (vocal tremor proxy)

Composite:
  - vocal_stress_score (0..1) — weighted blend of the above, anchored against
    typical English speech ranges. Higher = more vocal indicators of distress.

Personal baseline:
  - compute_user_baseline(user_id) returns the user's own typical biomarker
    averages from past entries, used for personalised z-scoring.

Incongruence detection:
  - analyze_congruence(biomarkers, sentiment, baseline) flags entries where
    the *text* sentiment is positive but the *voice* indicates distress
    (or vice versa) — the headline X-factor signal of this feature.

Graceful degradation:
  - All public functions return None on any decoding/extraction failure.
  - The journaling pipeline must continue working when biomarkers are
    unavailable (e.g. ffmpeg missing on a hosting tier, codec not supported,
    audio too short, librosa not installed).
"""

from __future__ import annotations

import io
import math
from typing import Optional

# === Anchored "typical" values for normalising features without a baseline ===
# These are conservative anchors based on adult English conversational speech.
# Used so that vocal_stress_score is meaningful even on the very first entry,
# before a personal baseline exists.
_TYPICAL_PAUSE_RATIO = 0.20      # ~20% silence is normal in casual speech
_HIGH_PAUSE_RATIO = 0.50         # >50% silence is unusual (long hesitations)
_TYPICAL_ENERGY = 0.05           # typical RMS for a clear voice note
_LOW_ENERGY = 0.01               # very quiet / withdrawn
_TYPICAL_SPEECH_RATE = 3.5       # syllables per second (English avg ~3-4)
_TYPICAL_JITTER = 0.012          # relative jitter ~1.2% is normal
_HIGH_JITTER = 0.04              # >4% suggests vocal instability
_TYPICAL_PITCH_STD = 30.0        # Hz — flat speech has low variance

# Minimum number of past voiced entries needed before a personal baseline
# is considered statistically meaningful.
_MIN_BASELINE_ENTRIES = 5

# Z-score threshold above which a single feature is considered "elevated"
# relative to the user's personal baseline.
_BASELINE_Z_THRESHOLD = 1.5

# Weights for the composite vocal_stress_score (must sum to 1.0)
_STRESS_WEIGHTS = {
    "jitter": 0.25,
    "pause_ratio": 0.25,
    "low_energy": 0.20,
    "rate_deviation": 0.15,
    "flat_pitch": 0.15,
}


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clip a value into a closed range [lo, hi]."""
    if value != value:  # NaN check
        return lo
    return max(lo, min(hi, value))


def _decode_audio(audio_bytes: bytes, target_sr: int = 16000):
    """Decode arbitrary audio bytes into (mono float32 ndarray, sample_rate).

    Tries soundfile first (handles WAV, FLAC, OGG-Vorbis natively, fast path
    for tests). Falls back to librosa.load with audioread (handles OGG-Opus
    from Telegram, MP3, M4A — but requires ffmpeg installed).

    Returns (None, None) on any failure rather than raising.
    """
    try:
        import numpy as np
        import soundfile as sf

        data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)  # downmix to mono
        if sr != target_sr:
            try:
                import librosa
                data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
                sr = target_sr
            except Exception:
                pass  # keep original sr if resample fails
        return np.asarray(data, dtype=np.float32), sr
    except Exception:
        pass

    try:
        import numpy as np
        import librosa

        data, sr = librosa.load(io.BytesIO(audio_bytes), sr=target_sr, mono=True)
        return np.asarray(data, dtype=np.float32), sr
    except Exception:
        return None, None


def extract_biomarkers(
    audio_bytes: bytes,
    transcript: Optional[str] = None,
) -> Optional[dict]:
    """Extract voice biomarkers from raw audio bytes.

    Args:
        audio_bytes: Raw audio file bytes (WAV, OGG, MP3, etc.).
        transcript: Optional transcript text — used to estimate speech_rate
            (syllables / sec) more accurately than acoustic onset detection.

    Returns:
        Dict with biomarker fields (all floats), or None if extraction failed
        or the audio was too short / silent to be analysed meaningfully.

        Keys: pitch_mean, pitch_std, speech_rate, pause_ratio, energy_mean,
        jitter, vocal_stress_score, audio_duration.
    """
    if not audio_bytes:
        return None

    y, sr = _decode_audio(audio_bytes)
    if y is None or sr is None or len(y) == 0:
        return None

    duration = float(len(y)) / float(sr)
    # Need at least 0.5s of audio to extract anything meaningful
    if duration < 0.5:
        return None

    try:
        import numpy as np
        import librosa
    except Exception:
        return None

    # --- Energy (RMS) ---
    try:
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
        energy_mean = float(np.mean(rms))
    except Exception:
        rms = None
        energy_mean = 0.0

    # If the clip is essentially silent, biomarkers aren't meaningful.
    if energy_mean < 1e-4:
        return None

    # --- Pause ratio (silence detection via energy threshold) ---
    pause_ratio = 0.0
    if rms is not None and len(rms) > 0:
        # Frames quieter than 10% of mean energy are considered silence.
        silence_threshold = max(energy_mean * 0.10, 1e-3)
        silent_frames = int(np.sum(rms < silence_threshold))
        pause_ratio = float(silent_frames) / float(len(rms))

    # --- Pitch (F0) via pYIN — robust on noisy speech ---
    pitch_mean = 0.0
    pitch_std = 0.0
    jitter = 0.0
    try:
        f0, voiced_flag, _ = librosa.pyin(
            y,
            fmin=50.0,
            fmax=400.0,
            sr=sr,
            frame_length=2048,
        )
        if f0 is not None:
            voiced_f0 = f0[~np.isnan(f0)]
            if len(voiced_f0) >= 5:
                pitch_mean = float(np.mean(voiced_f0))
                pitch_std = float(np.std(voiced_f0))
                # Relative jitter = mean abs frame-to-frame change / mean pitch.
                if pitch_mean > 0:
                    deltas = np.abs(np.diff(voiced_f0))
                    jitter = float(np.mean(deltas) / pitch_mean)
    except Exception:
        # pYIN can fail on very short / pathological inputs; leave defaults.
        pass

    # --- Speech rate (syllables per second) ---
    # If we have a transcript, use word_count * ~1.5 syllables/word — fast and
    # robust. Otherwise fall back to onset-rate as a rough proxy.
    speech_rate = 0.0
    if transcript:
        words = [w for w in transcript.split() if w.strip()]
        if words:
            est_syllables = len(words) * 1.5
            speech_rate = est_syllables / max(duration, 0.5)
    if speech_rate == 0.0:
        try:
            onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time")
            if len(onsets) > 0:
                speech_rate = float(len(onsets)) / max(duration, 0.5)
        except Exception:
            speech_rate = 0.0

    biomarkers = {
        "pitch_mean": round(pitch_mean, 3),
        "pitch_std": round(pitch_std, 3),
        "speech_rate": round(speech_rate, 3),
        "pause_ratio": round(pause_ratio, 4),
        "energy_mean": round(energy_mean, 5),
        "jitter": round(jitter, 5),
        "audio_duration": round(duration, 2),
    }
    biomarkers["vocal_stress_score"] = round(
        compute_vocal_stress_score(biomarkers), 4
    )
    return biomarkers


def compute_vocal_stress_score(biomarkers: dict) -> float:
    """Compute a composite vocal stress score in [0, 1] from raw biomarkers.

    Uses anchored normalisation so the score is meaningful without a
    personal baseline. Higher values = more vocal indicators of distress.

    The composite blends five normalised sub-signals:
      - jitter        (vocal tremor / instability)
      - pause_ratio   (hesitation / cognitive load)
      - low_energy    (withdrawal / fatigue, inverted from energy_mean)
      - rate_deviation(speech rate too fast OR too slow)
      - flat_pitch    (low pitch_std = monotone affect)
    """
    jitter = float(biomarkers.get("jitter") or 0.0)
    pause_ratio = float(biomarkers.get("pause_ratio") or 0.0)
    energy_mean = float(biomarkers.get("energy_mean") or 0.0)
    speech_rate = float(biomarkers.get("speech_rate") or 0.0)
    pitch_std = float(biomarkers.get("pitch_std") or 0.0)

    # Each sub-signal -> [0, 1] where 1 = stronger stress indicator.
    jitter_n = _clip(
        (jitter - _TYPICAL_JITTER) / max(_HIGH_JITTER - _TYPICAL_JITTER, 1e-6)
    )
    pause_n = _clip(
        (pause_ratio - _TYPICAL_PAUSE_RATIO)
        / max(_HIGH_PAUSE_RATIO - _TYPICAL_PAUSE_RATIO, 1e-6)
    )
    # Energy: lower than typical -> higher stress contribution.
    if energy_mean >= _TYPICAL_ENERGY:
        low_energy_n = 0.0
    else:
        low_energy_n = _clip(
            (_TYPICAL_ENERGY - energy_mean)
            / max(_TYPICAL_ENERGY - _LOW_ENERGY, 1e-6)
        )
    # Rate deviation: distance from typical, both directions count.
    if speech_rate <= 0:
        rate_dev_n = 0.0
    else:
        rate_dev_n = _clip(abs(speech_rate - _TYPICAL_SPEECH_RATE) / 3.0)
    # Flat pitch: low pitch_std relative to typical -> stress indicator.
    if pitch_std <= 0:
        flat_pitch_n = 0.0
    else:
        flat_pitch_n = _clip(
            (_TYPICAL_PITCH_STD - pitch_std) / _TYPICAL_PITCH_STD
        )

    score = (
        _STRESS_WEIGHTS["jitter"] * jitter_n
        + _STRESS_WEIGHTS["pause_ratio"] * pause_n
        + _STRESS_WEIGHTS["low_energy"] * low_energy_n
        + _STRESS_WEIGHTS["rate_deviation"] * rate_dev_n
        + _STRESS_WEIGHTS["flat_pitch"] * flat_pitch_n
    )
    return _clip(score)


def compute_user_baseline(user_id: str, days: int = 60) -> Optional[dict]:
    """Compute the user's personal biomarker baseline from past Qdrant entries.

    Scrolls all entries with stored biomarker fields and returns mean + std
    for the key features. Returns None if there are not enough voiced entries
    (<_MIN_BASELINE_ENTRIES) to be statistically meaningful.

    Args:
        user_id: User identifier.
        days: Look-back window in days.
    """
    try:
        from datetime import datetime, timezone, timedelta
        from services.qdrant_service import scroll_entries
    except Exception:
        return None

    try:
        date_from = int(
            (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        )
        entries = scroll_entries(user_id=user_id, date_from=date_from, limit=200)
    except Exception:
        return None

    samples: dict[str, list[float]] = {
        "vocal_stress_score": [],
        "pitch_mean": [],
        "pitch_std": [],
        "energy_mean": [],
        "pause_ratio": [],
        "speech_rate": [],
        "jitter": [],
    }
    for e in entries:
        payload = e.payload or {}
        if payload.get("vocal_stress_score") is None:
            continue
        for key in samples:
            value = payload.get(key)
            if value is None:
                continue
            try:
                samples[key].append(float(value))
            except (TypeError, ValueError):
                continue

    if len(samples["vocal_stress_score"]) < _MIN_BASELINE_ENTRIES:
        return None

    def _stats(values: list[float]) -> dict:
        if not values:
            return {"mean": 0.0, "std": 0.0, "count": 0}
        n = len(values)
        mean = sum(values) / n
        if n < 2:
            std = 0.0
        else:
            std = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
        return {"mean": round(mean, 5), "std": round(std, 5), "count": n}

    return {key: _stats(values) for key, values in samples.items()}


def analyze_congruence(
    biomarkers: dict,
    sentiment: float,
    baseline: Optional[dict] = None,
) -> dict:
    """Detect text-voice incongruence — the headline signal of this feature.

    Returns a dict with:
      - congruence_score (0..1): 1 = text and voice agree, 0 = they disagree
      - incongruent (bool): True when the mismatch is large enough to flag
      - direction (str): "text_positive_voice_stressed" |
                         "text_negative_voice_calm" | "aligned"
      - message (str|None): Human-readable explanation when incongruent
      - vocal_stress_z (float|None): Z-score vs personal baseline if available

    Args:
        biomarkers: Output of extract_biomarkers().
        sentiment: Text sentiment score in [-1, 1].
        baseline: Output of compute_user_baseline() or None.
    """
    if not biomarkers or biomarkers.get("vocal_stress_score") is None:
        return {
            "congruence_score": 1.0,
            "incongruent": False,
            "direction": "aligned",
            "message": None,
            "vocal_stress_z": None,
        }

    stress = float(biomarkers["vocal_stress_score"])

    # Compute z-score against personal baseline if one exists.
    vocal_z: Optional[float] = None
    if baseline is not None:
        b = baseline.get("vocal_stress_score") or {}
        b_mean = float(b.get("mean", 0.0))
        b_std = float(b.get("std", 0.0))
        if b_std > 1e-4:
            vocal_z = (stress - b_mean) / b_std
        elif stress > b_mean:
            vocal_z = 2.0  # any deviation is large when std is ~0

    # The voice is considered "stressed" when:
    #   - z-score > threshold (if baseline available), OR
    #   - raw stress score > 0.55 (no-baseline fallback)
    if vocal_z is not None:
        voice_stressed = vocal_z >= _BASELINE_Z_THRESHOLD
    else:
        voice_stressed = stress >= 0.55

    # Text considered "positive" if sentiment > 0.2, "negative" if < -0.2.
    text_positive = sentiment > 0.2
    text_negative = sentiment < -0.2

    direction = "aligned"
    incongruent = False
    message: Optional[str] = None

    if text_positive and voice_stressed:
        direction = "text_positive_voice_stressed"
        incongruent = True
        message = (
            "Your words sound positive, but your voice has a different tone "
            "than usual today. Sometimes we say we're fine before we realise "
            "we're not — gentle check-in: how are you really feeling?"
        )
    elif text_negative and not voice_stressed and stress < 0.35:
        direction = "text_negative_voice_calm"
        incongruent = True
        message = (
            "Your words feel heavy, but your voice sounds steady. That can be "
            "a sign of resilience — you're processing something hard without "
            "being overwhelmed by it."
        )

    # Congruence score: 1.0 when aligned, scales down with mismatch magnitude.
    if not incongruent:
        congruence_score = 1.0
    else:
        # Magnitude of mismatch — how far apart text and voice are.
        text_norm = (sentiment + 1.0) / 2.0          # 0..1
        voice_calm = 1.0 - stress                     # 0..1 (calm = 1)
        # When aligned, text_norm and voice_calm should be similar.
        gap = abs(text_norm - voice_calm)
        congruence_score = round(_clip(1.0 - gap), 4)

    return {
        "congruence_score": congruence_score,
        "incongruent": incongruent,
        "direction": direction,
        "message": message,
        "vocal_stress_z": round(vocal_z, 3) if vocal_z is not None else None,
    }
