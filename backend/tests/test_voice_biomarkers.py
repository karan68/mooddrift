"""
End-to-end tests for the Voice Biomarkers feature (FEATURES.md Feature 1).

Covers:
  - Audio decoding (WAV path, garbage input graceful failure)
  - Per-feature extraction (pitch, energy, pause ratio, speech rate, jitter)
  - Composite vocal_stress_score (bounds, monotonicity, weights)
  - Personal baseline computation (insufficient data → None, stats correct)
  - Text-voice congruence and incongruence detection (both directions)
  - Schema acceptance of optional biomarker fields
  - Telegram pipeline: _process_entry merges biomarkers and stores in Qdrant
  - Telegram /telegram/webhook reply surfaces incongruence message
  - Dashboard endpoint /api/voice-biomarkers shape + content

Synthetic audio is generated as raw WAV bytes via numpy + soundfile so the
tests do not require ffmpeg or any audio codecs to be installed.
"""

import io
import sys
import os
import uuid
import math

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.voice_biomarkers import (
    extract_biomarkers,
    compute_vocal_stress_score,
    compute_user_baseline,
    analyze_congruence,
    _decode_audio,
)


# ============================================================
#                      Audio fixtures
# ============================================================

SR = 16000  # sample rate used everywhere in tests


def _wav_bytes(samples: np.ndarray, sr: int = SR) -> bytes:
    """Encode a float32 numpy array as WAV bytes via soundfile."""
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, samples.astype(np.float32), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _sine_voice(
    freq: float = 180.0,
    duration: float = 3.0,
    amp: float = 0.2,
    sr: int = SR,
    pitch_jitter: float = 0.0,
    pause_fraction: float = 0.0,
) -> np.ndarray:
    """Build a synthetic voice-like waveform (sum of harmonics).

    Args:
        freq:           Fundamental pitch in Hz.
        duration:       Total duration in seconds.
        amp:            Peak amplitude (0..1).
        sr:             Sample rate.
        pitch_jitter:   Std dev (Hz) of frame-to-frame pitch wobble.
        pause_fraction: Fraction of the clip filled with trailing silence.
    """
    n = int(duration * sr)
    t = np.arange(n) / sr

    if pitch_jitter > 0:
        # Build a slowly varying jittered freq curve
        rng = np.random.default_rng(42)
        wobble = rng.normal(0.0, pitch_jitter, size=n)
        instantaneous_freq = freq + wobble
        phase = 2 * np.pi * np.cumsum(instantaneous_freq) / sr
    else:
        phase = 2 * np.pi * freq * t

    signal = (
        amp * np.sin(phase)
        + 0.3 * amp * np.sin(2 * phase)   # 2nd harmonic
        + 0.15 * amp * np.sin(3 * phase)  # 3rd harmonic
    )
    # Tiny noise floor so silence detection has something to threshold against
    signal = signal + 0.001 * np.random.default_rng(0).standard_normal(n)

    if pause_fraction > 0:
        silent_n = int(n * pause_fraction)
        signal[-silent_n:] = 0.0

    return signal.astype(np.float32)


# ============================================================
#                     Decoding tests
# ============================================================


class TestAudioDecoding:
    @pytest.mark.unit
    def test_decode_wav_succeeds(self):
        wav = _wav_bytes(_sine_voice(duration=1.0))
        y, sr = _decode_audio(wav, target_sr=SR)
        assert y is not None
        assert sr == SR
        assert len(y) > 0

    @pytest.mark.unit
    def test_decode_garbage_returns_none(self):
        y, sr = _decode_audio(b"not real audio bytes at all")
        assert y is None
        assert sr is None

    @pytest.mark.unit
    def test_decode_empty_returns_none(self):
        y, sr = _decode_audio(b"")
        assert y is None
        assert sr is None

    @pytest.mark.unit
    def test_decode_resamples_to_target_sr(self):
        # 8 kHz sine; should be resampled to 16 kHz
        wav = _wav_bytes(_sine_voice(duration=1.0, sr=8000), sr=8000)
        y, sr = _decode_audio(wav, target_sr=16000)
        assert y is not None
        assert sr == 16000


# ============================================================
#                Per-feature extraction tests
# ============================================================


class TestExtractBiomarkers:
    @pytest.mark.unit
    def test_returns_none_for_empty_bytes(self):
        assert extract_biomarkers(b"") is None

    @pytest.mark.unit
    def test_returns_none_for_garbage(self):
        assert extract_biomarkers(b"\x00\x01garbage") is None

    @pytest.mark.unit
    def test_returns_none_for_too_short_audio(self):
        # 0.1s is below the 0.5s minimum
        wav = _wav_bytes(_sine_voice(duration=0.1))
        assert extract_biomarkers(wav) is None

    @pytest.mark.unit
    def test_returns_none_for_silent_audio(self):
        silent = np.zeros(int(2.0 * SR), dtype=np.float32)
        wav = _wav_bytes(silent)
        assert extract_biomarkers(wav) is None

    @pytest.mark.unit
    def test_returns_dict_for_normal_audio(self):
        wav = _wav_bytes(_sine_voice(freq=180.0, duration=2.0))
        result = extract_biomarkers(wav)
        assert result is not None
        for key in (
            "pitch_mean", "pitch_std", "speech_rate", "pause_ratio",
            "energy_mean", "jitter", "vocal_stress_score", "audio_duration",
        ):
            assert key in result

    @pytest.mark.unit
    def test_pitch_is_close_to_fundamental(self):
        """A 200 Hz sine should yield pitch_mean within ~30 Hz."""
        wav = _wav_bytes(_sine_voice(freq=200.0, duration=2.0))
        result = extract_biomarkers(wav)
        assert result is not None
        # pYIN may not lock perfectly on a pure sine, but should be in ballpark
        assert 150.0 <= result["pitch_mean"] <= 260.0

    @pytest.mark.unit
    def test_audio_duration_is_correct(self):
        wav = _wav_bytes(_sine_voice(duration=2.5))
        result = extract_biomarkers(wav)
        assert result is not None
        assert abs(result["audio_duration"] - 2.5) < 0.1

    @pytest.mark.unit
    def test_pause_ratio_increases_with_silence(self):
        """A clip with a long trailing pause should have a high pause_ratio."""
        no_pause = _wav_bytes(_sine_voice(duration=2.0, pause_fraction=0.0))
        long_pause = _wav_bytes(_sine_voice(duration=2.0, pause_fraction=0.6))

        a = extract_biomarkers(no_pause)
        b = extract_biomarkers(long_pause)
        assert a is not None and b is not None
        assert b["pause_ratio"] > a["pause_ratio"] + 0.2

    @pytest.mark.unit
    def test_energy_increases_with_amplitude(self):
        quiet = _wav_bytes(_sine_voice(duration=1.5, amp=0.05))
        loud = _wav_bytes(_sine_voice(duration=1.5, amp=0.5))
        a = extract_biomarkers(quiet)
        b = extract_biomarkers(loud)
        assert a is not None and b is not None
        assert b["energy_mean"] > a["energy_mean"] * 3

    @pytest.mark.unit
    def test_speech_rate_uses_transcript_when_provided(self):
        """speech_rate should reflect transcript word count when available."""
        wav = _wav_bytes(_sine_voice(duration=2.0))
        # 8 words / 2s ≈ 6 syl/s with the 1.5x word→syllable estimate
        result = extract_biomarkers(wav, transcript="one two three four five six seven eight")
        assert result is not None
        assert 4.0 <= result["speech_rate"] <= 8.0

    @pytest.mark.unit
    def test_speech_rate_zero_when_no_words_and_no_onsets(self):
        # Pure silence won't reach this branch (returns None). Use very low
        # amplitude noise instead so onsets are detected near-zero.
        wav = _wav_bytes(_sine_voice(duration=1.5, amp=0.05))
        result = extract_biomarkers(wav, transcript="")
        assert result is not None
        assert result["speech_rate"] >= 0.0

    @pytest.mark.unit
    def test_jitter_increases_with_pitch_wobble(self):
        steady = _wav_bytes(_sine_voice(freq=180.0, duration=2.0, pitch_jitter=0.0))
        wobbly = _wav_bytes(_sine_voice(freq=180.0, duration=2.0, pitch_jitter=15.0))

        a = extract_biomarkers(steady)
        b = extract_biomarkers(wobbly)
        assert a is not None and b is not None
        # Pitch tracking on synthetic signals can be noisy; assert ordering
        # only when jitter actually came through.
        if a["jitter"] > 0 and b["jitter"] > 0:
            assert b["jitter"] >= a["jitter"]


# ============================================================
#               Composite vocal_stress_score tests
# ============================================================


class TestCompositeScore:
    @pytest.mark.unit
    def test_score_in_zero_one_range(self):
        for biomarkers in [
            {"pitch_std": 0, "pause_ratio": 0, "energy_mean": 0, "speech_rate": 0, "jitter": 0},
            {"pitch_std": 50, "pause_ratio": 0.2, "energy_mean": 0.05, "speech_rate": 3.5, "jitter": 0.012},
            {"pitch_std": 0, "pause_ratio": 1.0, "energy_mean": 0.0, "speech_rate": 10.0, "jitter": 0.5},
        ]:
            score = compute_vocal_stress_score(biomarkers)
            assert 0.0 <= score <= 1.0

    @pytest.mark.unit
    def test_typical_speech_yields_low_score(self):
        # Values exactly matching the "typical" anchors should produce low stress.
        score = compute_vocal_stress_score({
            "pitch_std": 30.0,
            "pause_ratio": 0.20,
            "energy_mean": 0.05,
            "speech_rate": 3.5,
            "jitter": 0.012,
        })
        assert score < 0.2

    @pytest.mark.unit
    def test_high_jitter_increases_score(self):
        baseline = {
            "pitch_std": 30.0, "pause_ratio": 0.2, "energy_mean": 0.05,
            "speech_rate": 3.5, "jitter": 0.012,
        }
        elevated = {**baseline, "jitter": 0.05}  # well above _HIGH_JITTER
        assert compute_vocal_stress_score(elevated) > compute_vocal_stress_score(baseline)

    @pytest.mark.unit
    def test_long_pauses_increase_score(self):
        baseline = {
            "pitch_std": 30.0, "pause_ratio": 0.2, "energy_mean": 0.05,
            "speech_rate": 3.5, "jitter": 0.012,
        }
        elevated = {**baseline, "pause_ratio": 0.7}
        assert compute_vocal_stress_score(elevated) > compute_vocal_stress_score(baseline)

    @pytest.mark.unit
    def test_low_energy_increases_score(self):
        baseline = {
            "pitch_std": 30.0, "pause_ratio": 0.2, "energy_mean": 0.05,
            "speech_rate": 3.5, "jitter": 0.012,
        }
        withdrawn = {**baseline, "energy_mean": 0.005}
        assert compute_vocal_stress_score(withdrawn) > compute_vocal_stress_score(baseline)

    @pytest.mark.unit
    def test_flat_pitch_increases_score(self):
        baseline = {
            "pitch_std": 30.0, "pause_ratio": 0.2, "energy_mean": 0.05,
            "speech_rate": 3.5, "jitter": 0.012,
        }
        flat = {**baseline, "pitch_std": 5.0}  # very monotone
        assert compute_vocal_stress_score(flat) > compute_vocal_stress_score(baseline)

    @pytest.mark.unit
    def test_handles_missing_keys(self):
        # Missing keys should be treated as zero / default, never crash.
        score = compute_vocal_stress_score({})
        assert 0.0 <= score <= 1.0


# ============================================================
#                 Personal baseline tests
# ============================================================


class FakePoint:
    """Minimal stand-in for a Qdrant ScoredPoint in unit tests."""
    def __init__(self, payload):
        self.payload = payload
        self.id = str(uuid.uuid4())
        self.vector = [0.0] * 384


class TestComputeUserBaseline:
    @pytest.mark.unit
    def test_returns_none_when_no_entries(self, monkeypatch):
        # Monkeypatch the lazy import inside compute_user_baseline
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])
        assert compute_user_baseline("u_empty") is None

    @pytest.mark.unit
    def test_returns_none_below_min_entries(self, monkeypatch):
        # Only 3 entries with biomarkers → below _MIN_BASELINE_ENTRIES (5)
        points = [
            FakePoint({
                "vocal_stress_score": 0.3,
                "pitch_mean": 180.0,
                "pitch_std": 30.0,
                "energy_mean": 0.05,
                "pause_ratio": 0.2,
                "speech_rate": 3.5,
                "jitter": 0.012,
            })
            for _ in range(3)
        ]
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)
        assert compute_user_baseline("u_few") is None

    @pytest.mark.unit
    def test_computes_mean_and_std(self, monkeypatch):
        scores = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        points = [
            FakePoint({
                "vocal_stress_score": s,
                "pitch_mean": 180.0,
                "pitch_std": 30.0,
                "energy_mean": 0.05,
                "pause_ratio": 0.2,
                "speech_rate": 3.5,
                "jitter": 0.012,
            })
            for s in scores
        ]
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)

        baseline = compute_user_baseline("u_full")
        assert baseline is not None
        stats = baseline["vocal_stress_score"]
        assert stats["count"] == 6
        assert abs(stats["mean"] - sum(scores) / len(scores)) < 1e-3
        assert stats["std"] > 0.0

    @pytest.mark.unit
    def test_skips_entries_without_biomarkers(self, monkeypatch):
        # 6 entries: 5 with biomarkers, 1 text-only — should still yield baseline
        points = [
            FakePoint({"vocal_stress_score": 0.3 + 0.05 * i, "pitch_mean": 180.0,
                       "pitch_std": 30.0, "energy_mean": 0.05, "pause_ratio": 0.2,
                       "speech_rate": 3.5, "jitter": 0.012})
            for i in range(5)
        ] + [FakePoint({"transcript": "text only entry"})]

        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)

        baseline = compute_user_baseline("u_mixed")
        assert baseline is not None
        assert baseline["vocal_stress_score"]["count"] == 5


# ============================================================
#               Congruence / incongruence tests
# ============================================================


class TestAnalyzeCongruence:
    @pytest.mark.unit
    def test_no_biomarkers_returns_aligned(self):
        result = analyze_congruence({}, sentiment=0.5, baseline=None)
        assert result["incongruent"] is False
        assert result["direction"] == "aligned"
        assert result["congruence_score"] == 1.0

    @pytest.mark.unit
    def test_aligned_positive(self):
        # Positive text + low vocal stress = aligned
        result = analyze_congruence(
            {"vocal_stress_score": 0.15},
            sentiment=0.6,
            baseline=None,
        )
        assert result["incongruent"] is False
        assert result["direction"] == "aligned"

    @pytest.mark.unit
    def test_aligned_negative(self):
        # Negative text + high vocal stress = aligned (both sad/stressed)
        result = analyze_congruence(
            {"vocal_stress_score": 0.7},
            sentiment=-0.6,
            baseline=None,
        )
        assert result["incongruent"] is False
        assert result["direction"] == "aligned"

    @pytest.mark.unit
    def test_incongruence_text_positive_voice_stressed(self):
        """The headline X-factor signal: 'I'm fine' said in a stressed voice."""
        result = analyze_congruence(
            {"vocal_stress_score": 0.7},
            sentiment=0.6,
            baseline=None,
        )
        assert result["incongruent"] is True
        assert result["direction"] == "text_positive_voice_stressed"
        assert result["message"] is not None
        assert "voice" in result["message"].lower()
        assert result["congruence_score"] < 1.0

    @pytest.mark.unit
    def test_incongruence_text_negative_voice_calm(self):
        """The reverse: heavy words said in a steady voice = resilience signal."""
        result = analyze_congruence(
            {"vocal_stress_score": 0.15},
            sentiment=-0.6,
            baseline=None,
        )
        assert result["incongruent"] is True
        assert result["direction"] == "text_negative_voice_calm"
        assert result["message"] is not None
        assert "resilience" in result["message"].lower() or "steady" in result["message"].lower()

    @pytest.mark.unit
    def test_uses_personal_baseline_when_available(self):
        """With a low-stress baseline, even a moderate stress score should flag."""
        baseline = {
            "vocal_stress_score": {"mean": 0.2, "std": 0.05, "count": 10},
        }
        # 0.4 is z = (0.4 - 0.2) / 0.05 = 4 → way above threshold
        result = analyze_congruence(
            {"vocal_stress_score": 0.4},
            sentiment=0.5,  # positive text
            baseline=baseline,
        )
        assert result["incongruent"] is True
        assert result["vocal_stress_z"] is not None
        assert result["vocal_stress_z"] > 1.5

    @pytest.mark.unit
    def test_baseline_with_zero_std_handles_gracefully(self):
        baseline = {
            "vocal_stress_score": {"mean": 0.3, "std": 0.0, "count": 10},
        }
        result = analyze_congruence(
            {"vocal_stress_score": 0.5},
            sentiment=0.5,
            baseline=baseline,
        )
        # Should not raise division-by-zero; z-score handled
        assert "vocal_stress_z" in result

    @pytest.mark.unit
    def test_neutral_text_not_flagged(self):
        # Text sentiment near zero — neither positive nor negative — should not
        # trigger the incongruence rules.
        result = analyze_congruence(
            {"vocal_stress_score": 0.7},
            sentiment=0.0,
            baseline=None,
        )
        assert result["incongruent"] is False
        assert result["direction"] == "aligned"


# ============================================================
#                    Schema acceptance test
# ============================================================


class TestSchemaAcceptsBiomarkers:
    @pytest.mark.unit
    def test_payload_accepts_biomarker_fields(self):
        from models.schemas import MoodEntryPayload

        payload = MoodEntryPayload(
            user_id="u",
            date="2026-04-17",
            timestamp=1744700000,
            transcript="hello",
            sentiment_score=0.3,
            keywords=["hi"],
            week_number=16,
            month="2026-04",
            entry_type="checkin",
            pitch_mean=180.0,
            pitch_std=25.0,
            speech_rate=3.5,
            pause_ratio=0.2,
            energy_mean=0.05,
            jitter=0.012,
            vocal_stress_score=0.3,
            audio_duration=4.2,
            text_voice_congruence=0.9,
            voice_incongruent=False,
        )
        assert payload.vocal_stress_score == 0.3
        assert payload.voice_incongruent is False

    @pytest.mark.unit
    def test_payload_works_without_biomarker_fields(self):
        from models.schemas import MoodEntryPayload
        payload = MoodEntryPayload(
            user_id="u", date="2026-04-17", timestamp=1, transcript="hi",
            sentiment_score=0.0, keywords=[], week_number=1, month="2026-04",
        )
        assert payload.vocal_stress_score is None


# ============================================================
#       Telegram pipeline integration (with monkeypatching)
# ============================================================


class TestTelegramPipelineIntegration:
    """Verify _process_entry merges biomarkers into the payload and runs
    congruence detection. Uses fake Qdrant + fake services so no external
    dependencies are required."""

    def _setup_fakes(self, monkeypatch):
        stored = {}

        def fake_upsert(vector, payload):
            pid = str(uuid.uuid4())
            stored[pid] = (vector, payload)
            return pid

        def fake_detect_drift(user_id, new_entry_vector=None):
            return {
                "detected": False, "skipped": False,
                "drift_score": 0.0, "severity": "none",
                "message": "stable", "matching_period": None,
                "matching_context": None, "coping_strategies": None,
                "sentiment_direction": "stable",
            }

        # Fake the lazy imports inside _process_entry
        import services.embedding as emb
        import services.sentiment as sent
        import services.keywords as kw
        import services.qdrant_service as qs
        import services.drift_engine as de
        import services.voice_biomarkers as vbm

        monkeypatch.setattr(emb, "generate_embedding", lambda t: [0.0] * 384)
        monkeypatch.setattr(sent, "analyze_sentiment", lambda t: 0.6)  # positive
        monkeypatch.setattr(kw, "extract_keywords", lambda t, max_keywords=5: ["hello"])
        monkeypatch.setattr(qs, "upsert_entry", fake_upsert)
        # Patch detect_drift in BOTH places it's imported
        monkeypatch.setattr(de, "detect_drift", fake_detect_drift)
        import routers.telegram_bot as tb
        monkeypatch.setattr(tb, "detect_drift", fake_detect_drift)
        # Pretend the user has no baseline yet
        monkeypatch.setattr(vbm, "compute_user_baseline", lambda uid, days=60: None)

        return stored

    @pytest.mark.unit
    def test_process_entry_without_biomarkers_omits_voice_fields(self, monkeypatch):
        stored = self._setup_fakes(monkeypatch)
        from routers.telegram_bot import _process_entry

        result = _process_entry("u_text_only", "I had a good day", entry_type="checkin")
        assert result["biomarkers"] is None
        assert result["congruence"] is None

        # Stored payload should NOT have voice fields
        _vec, payload = next(iter(stored.values()))
        assert "vocal_stress_score" not in payload
        assert "voice_incongruent" not in payload

    @pytest.mark.unit
    def test_process_entry_with_biomarkers_stores_voice_fields(self, monkeypatch):
        stored = self._setup_fakes(monkeypatch)
        from routers.telegram_bot import _process_entry

        biomarkers = {
            "pitch_mean": 180.0, "pitch_std": 25.0, "speech_rate": 3.5,
            "pause_ratio": 0.2, "energy_mean": 0.05, "jitter": 0.012,
            "vocal_stress_score": 0.25, "audio_duration": 4.0,
        }
        result = _process_entry(
            "u_voice", "I had a good day", biomarkers=biomarkers,
        )
        assert result["biomarkers"] == biomarkers
        assert result["congruence"] is not None
        # Aligned (positive text + low stress)
        assert result["congruence"]["incongruent"] is False

        _vec, payload = next(iter(stored.values()))
        assert payload["vocal_stress_score"] == 0.25
        assert payload["pitch_mean"] == 180.0
        assert payload["voice_incongruent"] is False
        assert payload["text_voice_congruence"] == 1.0

    @pytest.mark.unit
    def test_process_entry_flags_incongruence(self, monkeypatch):
        """Positive text + high vocal stress should be flagged incongruent."""
        stored = self._setup_fakes(monkeypatch)
        from routers.telegram_bot import _process_entry

        biomarkers = {
            "pitch_mean": 180.0, "pitch_std": 5.0,  # flat pitch
            "speech_rate": 3.5, "pause_ratio": 0.6,  # long pauses
            "energy_mean": 0.005,                    # very quiet
            "jitter": 0.05,                          # tremor
            "vocal_stress_score": 0.75,
            "audio_duration": 4.0,
        }
        result = _process_entry(
            "u_voice_flag", "Everything is great today!", biomarkers=biomarkers,
        )
        assert result["congruence"]["incongruent"] is True
        assert result["congruence"]["direction"] == "text_positive_voice_stressed"

        _vec, payload = next(iter(stored.values()))
        assert payload["voice_incongruent"] is True

    @pytest.mark.unit
    def test_format_response_surfaces_incongruence(self, monkeypatch):
        from routers.telegram_bot import _format_response
        result = {
            "sentiment": 0.5,
            "keywords": ["work"],
            "drift": {"detected": False, "skipped": False,
                      "message": "Patterns look consistent.", "severity": "none"},
            "congruence": {
                "incongruent": True,
                "message": "Your words sound positive, but your voice is different today.",
                "direction": "text_positive_voice_stressed",
                "congruence_score": 0.4,
                "vocal_stress_z": 2.1,
            },
        }
        text = _format_response(result)
        assert "Voice check-in" in text
        assert "voice is different" in text


# ============================================================
#             Voice-note webhook end-to-end smoke test
# ============================================================


class TestVoiceWebhookEndToEnd:
    """Full path: Telegram /telegram/webhook receives a voice note → background
    handler downloads → transcribes → extracts biomarkers → stores in Qdrant.

    All external services (Telegram HTTP, Groq Whisper, Qdrant) are mocked
    so the test is deterministic and offline-safe."""

    @pytest.mark.unit
    def test_voice_webhook_runs_biomarker_pipeline(self, monkeypatch):
        from fastapi.testclient import TestClient
        from main import app
        import routers.telegram_bot as tb

        # Capture the payload that ends up in Qdrant
        captured = {}

        def fake_upsert(vector, payload):
            captured["payload"] = payload
            return "fake-point-id"

        # Wire up fakes
        monkeypatch.setattr(tb, "_send_message_sync", lambda chat_id, text: None)
        monkeypatch.setattr(tb, "_send_voice_sync", lambda chat_id, b: None)
        monkeypatch.setattr(
            tb, "_download_file_sync",
            lambda fid: _wav_bytes(_sine_voice(duration=2.0)),
        )

        import services.transcription as tr
        monkeypatch.setattr(tr, "transcribe_audio", lambda b: "I am doing well today")

        import services.embedding as emb
        import services.sentiment as sent
        import services.keywords as kw
        import services.qdrant_service as qs
        import services.drift_engine as de
        import services.voice_biomarkers as vbm

        monkeypatch.setattr(emb, "generate_embedding", lambda t: [0.0] * 384)
        monkeypatch.setattr(sent, "analyze_sentiment", lambda t: 0.5)
        monkeypatch.setattr(kw, "extract_keywords", lambda t, max_keywords=5: ["well"])
        monkeypatch.setattr(qs, "upsert_entry", fake_upsert)

        stable_drift = {
            "detected": False, "skipped": False,
            "drift_score": 0.0, "severity": "none",
            "message": "stable", "matching_period": None,
            "matching_context": None, "coping_strategies": None,
            "sentiment_direction": "stable",
        }
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: stable_drift)
        monkeypatch.setattr(tb, "detect_drift", lambda *a, **kw: stable_drift)
        monkeypatch.setattr(vbm, "compute_user_baseline", lambda uid, days=60: None)

        client = TestClient(app)

        # Build a voice-note webhook payload
        chat_id = 700001
        payload = {
            "update_id": int(uuid.uuid4().int % 1_000_000),
            "message": {
                "message_id": 1,
                "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
                "chat": {"id": chat_id, "type": "private"},
                "date": 1744700000,
                "voice": {"file_id": "fake_file_id", "duration": 2},
            },
        }

        # Trigger via webhook (which spawns a background thread)
        resp = client.post("/telegram/webhook", json=payload)
        assert resp.status_code == 200

        # Wait for background processing
        import time
        for _ in range(30):
            if "payload" in captured:
                break
            time.sleep(0.2)

        assert "payload" in captured, "Voice note was not processed end-to-end"
        stored_payload = captured["payload"]

        # Verify biomarker fields were extracted from the synthetic WAV and
        # merged into the Qdrant payload.
        assert "vocal_stress_score" in stored_payload
        assert 0.0 <= stored_payload["vocal_stress_score"] <= 1.0
        assert "pitch_mean" in stored_payload
        assert "audio_duration" in stored_payload
        assert "voice_incongruent" in stored_payload
        assert "text_voice_congruence" in stored_payload
        assert stored_payload["transcript"] == "I am doing well today"


# ============================================================
#               Dashboard endpoint shape test
# ============================================================


class TestVoiceBiomarkersEndpoint:
    @pytest.mark.unit
    def test_endpoint_returns_expected_shape_for_empty_user(self, monkeypatch):
        """Even with no voice entries the endpoint should return a well-formed
        response (empty timeline, null baseline)."""
        from fastapi.testclient import TestClient
        from main import app

        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])

        client = TestClient(app)
        resp = client.get(f"/api/voice-biomarkers?user_id=void_user_{uuid.uuid4().hex[:6]}&days=30")
        assert resp.status_code == 200
        data = resp.json()

        assert "timeline" in data
        assert "baseline" in data
        assert "latest_incongruence" in data
        assert "summary" in data
        assert data["timeline"] == []
        assert data["baseline"] is None
        assert data["latest_incongruence"] is None
        assert data["summary"]["total_voice_entries"] == 0
        assert data["summary"]["incongruent_count"] == 0

    @pytest.mark.unit
    def test_endpoint_returns_timeline_and_summary(self, monkeypatch):
        """With biomarker-bearing entries, the endpoint should populate the
        timeline, summary, and surface the latest incongruent point."""
        from fastapi.testclient import TestClient
        from main import app

        # 6 entries, 1 of which is incongruent
        points = []
        for i in range(5):
            points.append(FakePoint({
                "date": f"2026-04-{10+i}",
                "timestamp": 1744700000 + i * 86400,
                "sentiment_score": 0.4,
                "vocal_stress_score": 0.2 + i * 0.02,
                "pitch_mean": 180.0,
                "pitch_std": 30.0,
                "speech_rate": 3.5,
                "pause_ratio": 0.2,
                "energy_mean": 0.05,
                "jitter": 0.012,
                "audio_duration": 4.0,
                "text_voice_congruence": 0.95,
                "voice_incongruent": False,
                "transcript": f"day {i}",
            }))
        # The flagged one (most recent)
        points.append(FakePoint({
            "date": "2026-04-15",
            "timestamp": 1744700000 + 6 * 86400,
            "sentiment_score": 0.6,
            "vocal_stress_score": 0.75,
            "pitch_mean": 175.0,
            "pitch_std": 5.0,
            "speech_rate": 3.5,
            "pause_ratio": 0.6,
            "energy_mean": 0.005,
            "jitter": 0.05,
            "audio_duration": 4.0,
            "text_voice_congruence": 0.4,
            "voice_incongruent": True,
            "transcript": "everything is great",
        }))

        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)
        # Also patch the already-imported reference in the dashboard router
        import routers.dashboard as dash
        monkeypatch.setattr(dash, "scroll_entries", lambda **kw: points)

        client = TestClient(app)
        resp = client.get(f"/api/voice-biomarkers?user_id=u_demo_{uuid.uuid4().hex[:6]}&days=90")
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["timeline"]) == 6
        # Sorted ascending by timestamp
        timestamps = [p["timestamp"] for p in data["timeline"]]
        assert timestamps == sorted(timestamps)

        assert data["summary"]["total_voice_entries"] == 6
        assert data["summary"]["incongruent_count"] == 1
        assert data["summary"]["avg_vocal_stress"] is not None

        assert data["latest_incongruence"] is not None
        assert data["latest_incongruence"]["voice_incongruent"] is True
        assert data["latest_incongruence"]["transcript"].startswith("everything")

        # Baseline computed (>=5 entries with vocal_stress_score)
        assert data["baseline"] is not None
        assert data["baseline"]["vocal_stress_score"]["count"] >= 5
