"""Model registry — singleton that loads and serves the AntiSpoofNetV4 model.

Loads the model once at application startup. Provides two inference modes:
1. Full forward pass → 6-class logits (for FAS classification)
2. Intermediate extraction → 512-dim embedding from fsfm_embedder layer

CPU-only inference with float32 precision. No GPU, no XLA, no mixed precision.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import tensorflow as tf

import keras
from keras import mixed_precision

from spectre.config import Settings
from spectre.core.logger import get_logger
from spectre.infrastructure.ml.custom_layers import CUSTOM_OBJECTS

logger = get_logger(__name__)


class ModelRegistry:
    """Singleton model registry — loads AntiSpoofNetV4 and provides inference.

    The model architecture (from train.py):
        Input(256,256,3)
        → ConvNeXtSmall backbone → Reshape → AttentionPooling → 768-dim
        → FrequencyBranch → 256-dim
        → CDCBranch → 256-dim
        → Concatenate → 1280-dim
        → Dense(512, name='fsfm_embedder') → 512-dim  ← EMBEDDING
        → LayerNorm → GELU → Dropout
        → Dense(6, name='logits') → 6-dim  ← CLASSIFICATION
    """

    def __init__(self) -> None:
        self._model: keras.Model | None = None
        self._embedding_model: keras.Model | None = None
        self._classify_fn: object | None = None
        self._embed_fn: object | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self, settings: Settings) -> None:
        """Load the model from disk. Called once at application startup."""
        model_path = settings.model_path_resolved
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model file not found: {model_path}. "
                "Ensure 'artifact/best_model.keras' exists."
            )

        logger.info("model_loading", path=str(model_path))
        start = time.monotonic()

        # Force CPU + float32
        mixed_precision.set_global_policy("float32")

        self._model = keras.saving.load_model(
            str(model_path),
            custom_objects=CUSTOM_OBJECTS,
            compile=False,
        )

        # Build embedding extraction sub-model:
        # Output from the 'fsfm_embedder' layer (Dense(512)) BEFORE dropout/logits
        embedder_layer = self._model.get_layer("fsfm_embedder")
        self._embedding_model = keras.Model(
            inputs=self._model.input,
            outputs=embedder_layer.output,
            name="EmbeddingExtractor",
        )

        # Compile inference functions (traced for performance)
        self._classify_fn = self._compile_classify()
        self._embed_fn = self._compile_embed()

        elapsed = time.monotonic() - start
        logger.info(
            "model_loaded",
            elapsed_sec=round(elapsed, 2),
            params=self._model.count_params(),
        )

    def _compile_classify(self) -> object:
        """Compile a traced classification function."""
        model = self._model

        @tf.function(jit_compile=False, reduce_retracing=True)
        def classify(x: tf.Tensor) -> tf.Tensor:
            logits = model(x, training=False)
            return tf.nn.softmax(tf.cast(logits, tf.float32), axis=-1)

        return classify

    def _compile_embed(self) -> object:
        """Compile a traced embedding extraction function."""
        embed_model = self._embedding_model

        @tf.function(jit_compile=False, reduce_retracing=True)
        def embed(x: tf.Tensor) -> tf.Tensor:
            features = embed_model(x, training=False)
            # L2 normalize the embedding
            features = tf.cast(features, tf.float32)
            return tf.nn.l2_normalize(features, axis=-1)

        return embed

    def classify(self, image: np.ndarray) -> np.ndarray:
        """Run FAS classification on a preprocessed image.

        Args:
            image: Float32 array of shape (256, 256, 3) or (N, 256, 256, 3).

        Returns:
            Softmax probabilities of shape (6,) or (N, 6).
        """
        if self._classify_fn is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        if image.ndim == 3:
            image = image[np.newaxis, ...]

        tensor = tf.constant(image, dtype=tf.float32)
        probs = self._classify_fn(tensor)
        return probs.numpy()

    def extract_embedding(self, image: np.ndarray) -> np.ndarray:
        """Extract 512-dim face embedding from preprocessed image.

        Args:
            image: Float32 array of shape (256, 256, 3) or (N, 256, 256, 3).

        Returns:
            L2-normalized embedding of shape (512,) or (N, 512).
        """
        if self._embed_fn is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        if image.ndim == 3:
            image = image[np.newaxis, ...]

        tensor = tf.constant(image, dtype=tf.float32)
        embedding = self._embed_fn(tensor)
        result = embedding.numpy()

        # Squeeze batch dim if single image
        if result.shape[0] == 1:
            result = result[0]

        return result
