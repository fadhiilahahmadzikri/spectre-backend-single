"""Custom Keras layers required for loading the AntiSpoofNetV4 model.

Adapted from Kaggle/huggingface_app.py — the Windows-compatible float32 version.
These layers must be registered before loading best_model.keras.

Architecture:
    AntiSpoofNetV4
    ├── ConvNeXtSmall backbone (768-dim spatial features)
    ├── AttentionPooling (768-dim → 768-dim pooled)
    ├── FrequencyBranch (FFT magnitude → 256-dim)
    ├── CDCBranch (Central Difference Convolution → 256-dim)
    ├── Concatenate (768 + 256 + 256 = 1280-dim)
    ├── fsfm_embedder (Dense 1280 → 512-dim) ← EMBEDDING LAYER
    ├── LayerNorm + GELU + Dropout
    └── logits (Dense 512 → 6-class)
"""

from __future__ import annotations

import os
import warnings

# Suppress TensorFlow warnings for clean startup
os.environ.setdefault("KERAS_BACKEND", "tensorflow")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_XLA_FLAGS", "--tf_xla_auto_jit=0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # Force CPU

warnings.filterwarnings("ignore", category=DeprecationWarning)

import tensorflow as tf

tf.config.optimizer.set_jit(False)

import keras
from keras import layers


@keras.saving.register_keras_serializable()
class CDCConv(keras.Layer):
    """Central Difference Convolution — captures fine-grained texture patterns.

    Mixes standard convolution with a central difference term to detect
    micro-textures indicative of spoofing (print artifacts, screen pixels).
    """

    def __init__(
        self,
        filters: int,
        kernel_size: int = 3,
        strides: int = 1,
        theta: float = 0.7,
        **kw: object,
    ):
        kw["dtype"] = "float32"
        super().__init__(**kw)
        self.filters = filters
        self.kernel_size = kernel_size
        self.strides = strides
        self.theta = theta
        self._conv = layers.Conv2D(
            filters, kernel_size, strides=strides, padding="same", use_bias=False
        )

    def build(self, input_shape: tuple) -> None:
        safe_shape = [1 if d is None else d for d in input_shape]
        dummy = tf.zeros(safe_shape, dtype=tf.float32)
        self.call(dummy)
        super().build(input_shape)

    def call(self, x: tf.Tensor) -> tf.Tensor:
        x = tf.cast(x, tf.float32)
        normal = tf.cast(self._conv(x), tf.float32)
        ksum = tf.reduce_sum(self._conv.kernel, axis=[0, 1], keepdims=True)
        ksum = tf.cast(ksum, tf.float32)
        diff = tf.nn.conv2d(
            x, ksum, strides=[1, self.strides, self.strides, 1], padding="SAME"
        )
        diff = tf.cast(diff, tf.float32)
        theta = tf.cast(self.theta, tf.float32)
        return theta * normal + (1.0 - theta) * (normal - diff)

    def get_config(self) -> dict:
        return {
            **super().get_config(),
            "filters": self.filters,
            "kernel_size": self.kernel_size,
            "strides": self.strides,
            "theta": self.theta,
        }


@keras.saving.register_keras_serializable()
class FrequencyBranch(keras.Layer):
    """FFT-based frequency analysis branch.

    Converts input to grayscale, computes 2D FFT magnitude spectrum,
    then processes through a small ConvNet to detect frequency-domain
    spoofing artifacts (moiré patterns, print halftones).
    """

    def __init__(self, out_dim: int = 256, **kw: object):
        kw["dtype"] = "float32"
        super().__init__(**kw)
        self.out_dim = out_dim
        ch = [32, 64, 128, 256]
        self._convs = [
            layers.Conv2D(c, 3, strides=2, padding="same", name=f"fb_conv{i}")
            for i, c in enumerate(ch)
        ]
        self._lns = [
            layers.LayerNormalization(name=f"fb_ln{i}") for i in range(len(ch))
        ]
        self._pool = layers.GlobalAveragePooling2D(name="fb_gap")
        self._proj = layers.Dense(out_dim, name="fb_proj")
        self._norm = layers.LayerNormalization(name="fb_outnorm")

    def build(self, input_shape: tuple) -> None:
        safe_shape = [1 if d is None else d for d in input_shape]
        dummy = tf.zeros(safe_shape, dtype=tf.float32)
        self.call(dummy)
        super().build(input_shape)

    def call(self, x: tf.Tensor, training: bool = False) -> tf.Tensor:
        x = tf.cast(x, tf.float32)
        gray = tf.reduce_mean(x, axis=-1)
        fft = tf.signal.fft2d(
            tf.cast(tf.complex(gray, tf.zeros_like(gray)), tf.complex64)
        )
        fft = tf.roll(
            tf.roll(fft, tf.shape(fft)[-2] // 2, axis=-2),
            tf.shape(fft)[-1] // 2,
            axis=-1,
        )
        mag = tf.expand_dims(tf.math.log(tf.abs(fft) + 1e-8), -1)
        h = tf.cast(mag, tf.float32)
        for conv, ln in zip(self._convs, self._lns):
            h = tf.nn.swish(ln(conv(h), training=training))
            h = tf.cast(h, tf.float32)
        out = self._norm(self._proj(self._pool(h)))
        return tf.cast(out, tf.float32)

    def get_config(self) -> dict:
        return {**super().get_config(), "out_dim": self.out_dim}


@keras.saving.register_keras_serializable()
class CDCBranch(keras.Layer):
    """Central Difference Convolution branch for texture analysis.

    Processes the input through a stack of CDC layers to extract
    fine-grained texture features that distinguish real faces from
    various spoofing attack types.
    """

    def __init__(self, out_dim: int = 256, **kw: object):
        kw["dtype"] = "float32"
        super().__init__(**kw)
        self.out_dim = out_dim
        ch = [32, 64, 128, 256]
        self._cdcs = [
            CDCConv(c, strides=2, theta=0.7, name=f"cb_cdc{i}")
            for i, c in enumerate(ch)
        ]
        self._lns = [
            layers.LayerNormalization(name=f"cb_ln{i}") for i in range(len(ch))
        ]
        self._pool = layers.GlobalAveragePooling2D(name="cb_gap")
        self._proj = layers.Dense(out_dim, name="cb_proj")
        self._norm = layers.LayerNormalization(name="cb_outnorm")

    def build(self, input_shape: tuple) -> None:
        safe_shape = [1 if d is None else d for d in input_shape]
        dummy = tf.zeros(safe_shape, dtype=tf.float32)
        self.call(dummy)
        super().build(input_shape)

    def call(self, x: tf.Tensor, training: bool = False) -> tf.Tensor:
        h = tf.cast(x, tf.float32)
        for cdc, ln in zip(self._cdcs, self._lns):
            h = tf.nn.gelu(ln(cdc(h), training=training))
            h = tf.cast(h, tf.float32)
        out = self._norm(self._proj(self._pool(h)))
        return tf.cast(out, tf.float32)

    def get_config(self) -> dict:
        return {**super().get_config(), "out_dim": self.out_dim}


@keras.saving.register_keras_serializable()
class AttentionPooling(keras.Layer):
    """Attention-based global pooling.

    Replaces standard global average pooling with a learned attention
    mechanism that weights spatial positions by their relevance.
    """

    def __init__(self, dim: int = 512, **kw: object):
        kw["dtype"] = "float32"
        super().__init__(**kw)
        self.dim = dim
        self._fc1 = layers.Dense(dim // 4, activation="tanh")
        self._fc2 = layers.Dense(1)

    def build(self, input_shape: tuple) -> None:
        safe_shape = [1 if d is None else d for d in input_shape]
        dummy = tf.zeros(safe_shape, dtype=tf.float32)
        self.call(dummy)
        super().build(input_shape)

    def call(self, x: tf.Tensor) -> tf.Tensor:
        x = tf.cast(x, tf.float32)
        w = tf.cast(self._fc1(x), tf.float32)
        w = tf.nn.softmax(self._fc2(w), axis=1)
        return tf.reduce_sum(x * w, axis=1)

    def compute_output_shape(self, input_shape: tuple) -> tuple:
        return (input_shape[0], self.dim)

    def get_config(self) -> dict:
        return {**super().get_config(), "dim": self.dim}


# Custom objects dict for model loading
CUSTOM_OBJECTS: dict[str, type] = {
    "CDCConv": CDCConv,
    "FrequencyBranch": FrequencyBranch,
    "CDCBranch": CDCBranch,
    "AttentionPooling": AttentionPooling,
}
