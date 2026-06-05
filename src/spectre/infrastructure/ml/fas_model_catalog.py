from __future__ import annotations

from dataclasses import dataclass

from spectre.infrastructure.ml.handlers.antispoofnet_v4 import AntiSpoofNetV4Handler
from spectre.infrastructure.ml.handlers.base import BaseFASHandler
from spectre.infrastructure.ml.handlers.ilhamcaesar_resnet50 import IlhamCaesarResNet50Handler


@dataclass(frozen=True)
class FASModelSpec:
    model_id: str
    handler_cls: type[BaseFASHandler]
    artifact_path_attr: str
    version: str
    description: str
    supports_tta: bool


FAS_MODEL_CATALOG: dict[str, FASModelSpec] = {
    "antispoofnet_v4": FASModelSpec(
        model_id="antispoofnet_v4",
        handler_cls=AntiSpoofNetV4Handler,
        artifact_path_attr="model_path_resolved",
        version="1.0",
        description="AntiSpoofNetV4 — ConvNeXtSmall + CDC + FFT branches (256x256, 6-class)",
        supports_tta=True,
    ),
    "ilhamcaesar_resnet50": FASModelSpec(
        model_id="ilhamcaesar_resnet50",
        handler_cls=IlhamCaesarResNet50Handler,
        artifact_path_attr="ilhamcaesar_model_path_resolved",
        version="1.2",
        description="IlhamCaesar ResNet50 transfer-learning classifier (224x224, 6-class)",
        supports_tta=False,
    ),
}
