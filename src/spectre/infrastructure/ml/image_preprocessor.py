"""Image preprocessor — normalize and prepare images for model inference.

Preprocessing pipeline matching the training configuration:
1. Resize to 256×256 (BICUBIC)
2. Convert to float32 [0, 1]
3. Normalize with ImageNet mean/std
4. Clip to ±2.5
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from spectre.config import Settings

if TYPE_CHECKING:
    pass

# ImageNet normalization constants (matching training)
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
CLIP_VAL = 2.5


class ImagePreprocessor:
    """Preprocesses images for FAS model inference.

    Matches the exact preprocessing pipeline used during training
    to ensure consistent model behavior.
    """

    def __init__(self, settings: Settings) -> None:
        self._img_size = settings.model_img_size
        self._use_tta = settings.model_use_tta

    def preprocess(self, image_bytes: bytes) -> np.ndarray:
        """Preprocess raw image bytes into a model-ready float32 array.

        Args:
            image_bytes: Raw JPEG/PNG image bytes.

        Returns:
            Float32 array of shape (256, 256, 3), normalized.
        """
        img = Image.open(
            __import__("io").BytesIO(image_bytes)
        ).convert("RGB")
        return self._normalize(img)

    def preprocess_pil(self, img: Image.Image) -> np.ndarray:
        """Preprocess a PIL Image into a model-ready array."""
        img = img.convert("RGB")
        return self._normalize(img)

    def _normalize(self, img: Image.Image) -> np.ndarray:
        """Resize, normalize, and clip."""
        img = img.resize((self._img_size, self._img_size), Image.Resampling.BICUBIC)
        arr = np.array(img).astype(np.float32) / 255.0
        arr = (arr - MEAN) / STD
        return np.clip(arr, -CLIP_VAL, CLIP_VAL)

    def build_tta_batch(self, image_bytes: bytes) -> tuple[np.ndarray, list[float]]:
        """Build a 12-crop Test-Time Augmentation (TTA) batch.
        
        Args:
            image_bytes: Raw JPEG/PNG image bytes.
            
        Returns:
            Tuple of (batch_array of shape (12, 256, 256, 3), weights_list).
        """
        img = Image.open(
            __import__("io").BytesIO(image_bytes)
        ).convert("RGB")
        
        scale   = 1.15
        new_sz  = int(self._img_size * scale)
        resized = img.resize((new_sz, new_sz), Image.Resampling.BICUBIC)
        left    = (new_sz - self._img_size) // 2
        top     = (new_sz - self._img_size) // 2
        center  = resized.crop((left, top, left + self._img_size, top + self._img_size))

        crops: list[np.ndarray] = []
        crops.append(self.preprocess_pil(img))
        crops.append(self.preprocess_pil(img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)))
        crops.append(self.preprocess_pil(center))
        crops.append(self.preprocess_pil(center.transpose(Image.Transpose.FLIP_LEFT_RIGHT)))

        corners = [
            (0,              0,              self._img_size,  self._img_size),
            (new_sz - self._img_size, 0,         new_sz,      self._img_size),
            (0,              new_sz - self._img_size, self._img_size, new_sz),
            (new_sz - self._img_size, new_sz - self._img_size, new_sz, new_sz),
        ]
        for box in corners:
            c = resized.crop(box)
            crops.append(self.preprocess_pil(c))
            crops.append(self.preprocess_pil(c.transpose(Image.Transpose.FLIP_LEFT_RIGHT)))

        weights = [
            0.35, 0.35, 0.075, 0.075,
            0.01875, 0.01875, 0.01875, 0.01875,
            0.01875, 0.01875, 0.01875, 0.01875
        ]
        return np.array(crops, dtype=np.float32), weights

    def preprocess_batch(self, images: list[bytes]) -> np.ndarray:
        """Preprocess multiple images into a batch array.

        Returns:
            Float32 array of shape (N, 256, 256, 3).
        """
        return np.array([self.preprocess(img) for img in images], dtype=np.float32)

    def validate_image(self, image_bytes: bytes) -> tuple[bool, str]:
        """Validate image quality and dimensions.

        Returns:
            Tuple of (is_valid, error_message).
        """
        try:
            img = Image.open(__import__("io").BytesIO(image_bytes))
            img.verify()
        except Exception:
            return False, "Invalid or corrupt image file."

        # Re-open after verify (verify closes the file)
        img = Image.open(__import__("io").BytesIO(image_bytes))

        if img.mode not in ("RGB", "RGBA", "L"):
            return False, f"Unsupported image mode: {img.mode}"

        w, h = img.size
        if w < 64 or h < 64:
            return False, f"Image too small: {w}×{h} (minimum 64×64)."

        if len(image_bytes) > 5 * 1024 * 1024:
            return False, "Image exceeds 5MB size limit."

        return True, ""
