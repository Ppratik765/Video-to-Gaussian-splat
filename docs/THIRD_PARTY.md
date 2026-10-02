# Third Party

| Component | Use | License | Status |
|---|---|---|---|
| OpenCV (opencv-python-headless) | flow, remap, morphology | Apache-2.0 | OK |
| PySceneDetect 0.6.4 | scene cuts | BSD-3-Clause | OK |
| yt-dlp | download (user-supplied URLs, permission note required) | Unlicense | OK |
| NumPy | math | BSD-3-Clause | OK |
| SegFormer b0 ADE20K weights (`nvidia/segformer-b0-finetuned-ade-512-512`) | optional dynamic-object masks | Hugging Face tag "other" (NVIDIA terms) | **License unconfirmed, likely non-commercial. Optional, off by default.** |
| Mask2Former tiny ADE20K weights (`facebook/mask2former-swin-tiny-ade-semantic`) | optional dynamic-object masks | Hugging Face tag "other" | **License terms unconfirmed. Optional, off by default.** |

The segmenter extras are never imported unless `masks.segmenter` is set. Do not redistribute
outputs or weights commercially until the terms are confirmed from the model repositories.
