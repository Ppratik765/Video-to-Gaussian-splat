"""
Responsibility: semantic.py
Milestone: M2
"""

from abc import ABC, abstractmethod

import numpy as np


class Segmenter(ABC):
    @abstractmethod
    def predict_dynamic_mask(self, image_bgr: np.ndarray) -> np.ndarray:
        """
        Predict dynamic objects (people, cars, etc.) in the image.
        Returns a binary mask where 255 = dynamic (exclude), 0 = static.
        """
        pass

class NullSegmenter(Segmenter):
    def predict_dynamic_mask(self, image_bgr: np.ndarray) -> np.ndarray:
        h, w = image_bgr.shape[:2]
        return np.zeros((h, w), dtype=np.uint8)


class HFSegmenter(Segmenter):
    def __init__(self, model_type: str = "segformer"):
        try:
            import torch
            from transformers import (
                AutoImageProcessor,
                AutoModelForSemanticSegmentation,
                Mask2FormerForUniversalSegmentation,
                Mask2FormerImageProcessor,
            )
        except ImportError as e:
            raise RuntimeError("Hugging Face transformers and torch are required for HFSegmenter. Install with `pip install transformers torch`.") from e

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_type = model_type

        if model_type == "segformer":
            # MIT license for code, weights often NC but commonly used.
            # Using b0 for speed.
            model_id = "nvidia/segformer-b0-finetuned-ade-512-512"
            self.processor = AutoImageProcessor.from_pretrained(model_id)
            self.model = AutoModelForSemanticSegmentation.from_pretrained(model_id).to(self.device)
            # ADE20K dynamic classes (person, car, truck, bus, animal, bicycle, motorcycle)
            # IDs in ADE20K 150 (0-indexed): 12 (person), 20 (car), 83 (truck), 80 (bus), 126 (animal), 116 (bicycle)
            self.dynamic_classes = {12, 20, 80, 83, 116, 126}
        elif model_type == "mask2former":
            model_id = "facebook/mask2former-swin-tiny-ade-semantic"
            self.processor = Mask2FormerImageProcessor.from_pretrained(model_id)
            self.model = Mask2FormerForUniversalSegmentation.from_pretrained(model_id).to(self.device)
            self.dynamic_classes = {12, 20, 80, 83, 116, 126}
        else:
            raise ValueError(f"Unknown HF segmenter type: {model_type}")

        self.model.eval()

    def predict_dynamic_mask(self, image_bgr: np.ndarray) -> np.ndarray:
        import cv2
        import torch

        # Convert BGR to RGB
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

        with torch.no_grad():
            inputs = self.processor(images=image_rgb, return_tensors="pt").to(self.device)
            outputs = self.model(**inputs)

            if self.model_type == "segformer":
                logits = outputs.logits  # shape (batch_size, num_labels, height, width)
                # Resize logits to original image size
                upsampled_logits = torch.nn.functional.interpolate(
                    logits,
                    size=image_bgr.shape[:2],
                    mode="bilinear",
                    align_corners=False,
                )
                pred_map = upsampled_logits.argmax(dim=1)[0].cpu().numpy()
            else:
                # Mask2Former
                predicted_map = self.processor.post_process_semantic_segmentation(
                    outputs, target_sizes=[image_bgr.shape[:2]]
                )[0]
                pred_map = predicted_map.cpu().numpy()

        # Create binary mask for dynamic classes
        mask = np.zeros_like(pred_map, dtype=np.uint8)
        for c in self.dynamic_classes:
            mask[pred_map == c] = 255

        return mask
