"""LivenessResult value object — FAS model prediction output."""

from __future__ import annotations

from dataclasses import dataclass


# Class labels matching the model's 6-class output order
FAS_CLASSES: tuple[str, ...] = (
    "fake_mannequin",
    "fake_mask",
    "fake_papercut",
    "fake_printed",
    "fake_screen",
    "realperson",
)
REAL_CLASS_IDX: int = 5


@dataclass(frozen=True)
class LivenessResult:
    """Immutable result of a Face Anti-Spoofing (FAS) model prediction.

    Contains the full 6-class probability distribution and derived
    boolean is_live flag based on a configurable threshold.
    """

    predicted_class: str
    predicted_index: int
    confidence: float  # Probability of the predicted class
    probabilities: tuple[float, ...]  # Full 6-class distribution
    is_live: bool
    inference_time_ms: int

    @classmethod
    def from_probabilities(
        cls,
        probabilities: list[float],
        threshold: float = 0.5,
        inference_time_ms: int = 0,
    ) -> LivenessResult:
        """Create from a softmax probability distribution.

        Args:
            probabilities: 6-class softmax output from FAS model.
            threshold: Minimum probability for 'realperson' to be considered live.
            inference_time_ms: Time taken for inference in milliseconds.
        """
        pred_idx = max(range(len(probabilities)), key=lambda i: probabilities[i])
        pred_class = FAS_CLASSES[pred_idx]
        confidence = probabilities[pred_idx]
        live_prob = probabilities[REAL_CLASS_IDX]

        return cls(
            predicted_class=pred_class,
            predicted_index=pred_idx,
            confidence=confidence,
            probabilities=tuple(probabilities),
            is_live=pred_idx == REAL_CLASS_IDX and live_prob >= threshold,
            inference_time_ms=inference_time_ms,
        )

    @property
    def live_probability(self) -> float:
        """Probability of the 'realperson' class."""
        return self.probabilities[REAL_CLASS_IDX]

    @property
    def spoof_probability(self) -> float:
        """Combined probability of all spoof classes."""
        return 1.0 - self.live_probability

    @property
    def top_spoof_class(self) -> str:
        """The spoof class with the highest probability (excludes realperson)."""
        spoof_probs = list(self.probabilities[:REAL_CLASS_IDX])
        idx = max(range(len(spoof_probs)), key=lambda i: spoof_probs[i])
        return FAS_CLASSES[idx]
