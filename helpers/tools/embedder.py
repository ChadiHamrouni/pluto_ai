"""
Multimodal embedder backed by nomic-embed-multimodal-3b via HuggingFace.

Handles text, images (PIL or path), and PDF pages uniformly — all inputs
are embedded into the same vector space.

Dependencies: colpali-engine, torch, Pillow
    pip install colpali-engine torch Pillow
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Union

import numpy as np
import torch
from PIL import Image
from colpali_engine.models import ColQwen2_5, ColQwen2_5_Processor

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

_model: ColQwen2_5 | None = None
_processor: ColQwen2_5_Processor | None = None
_ready: bool = False


def is_ready() -> bool:
    """Return True once the model has been loaded into memory."""
    return _ready


def load_model() -> None:
    """
    Eagerly load the embedding model into memory.

    Call this once at application startup so the model is warm before
    any requests arrive. Safe to call multiple times — subsequent calls
    are no-ops.
    """
    _load_model()


def _load_model() -> tuple[ColQwen2_5, ColQwen2_5_Processor]:
    global _model, _processor, _ready
    if _model is not None:
        return _model, _processor  # type: ignore[return-value]

    config = load_config()
    model_name = config["knowledge_base"]["embedding_model"]
    device = "cuda" if torch.cuda.is_available() else "cpu"

    logger.info("Loading multimodal embedding model '%s' on %s ...", model_name, device)

    _processor = ColQwen2_5_Processor.from_pretrained(model_name)
    _model = ColQwen2_5.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    ).eval()

    _ready = True
    logger.info("Multimodal embedding model loaded.")
    return _model, _processor


def _normalise(vec: np.ndarray) -> List[float]:
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


def embed_text(text: str) -> List[float]:
    """Embed a text string into a dense vector."""
    model, processor = _load_model()
    inputs = processor.process_queries([text]).to(model.device)
    with torch.no_grad():
        output = model(**inputs)
    # ColQwen2.5 returns per-token embeddings — mean pool to a single vector
    vec = output.last_hidden_state.mean(dim=1).squeeze().cpu().float().numpy()
    return _normalise(vec)


def embed_image(image: Union[str, Path, "Image.Image"]) -> List[float]:
    """
    Embed an image into the same vector space as text.

    *image* can be a file path (str or Path) or a PIL Image object.
    """
    model, processor = _load_model()

    if not isinstance(image, Image.Image):
        image = Image.open(image).convert("RGB")

    inputs = processor.process_images([image]).to(model.device)
    with torch.no_grad():
        output = model(**inputs)
    vec = output.last_hidden_state.mean(dim=1).squeeze().cpu().float().numpy()
    return _normalise(vec)


def embed(content: Union[str, Path, "Image.Image"]) -> List[float]:
    """
    Unified entry point — routes to embed_text or embed_image based on input type.

    - str/Path pointing to an image file (.jpg, .jpeg, .png, .webp) → embed_image
    - PIL Image → embed_image
    - anything else (str text, etc.) → embed_text
    """
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

    if isinstance(content, Image.Image):
        return embed_image(content)

    if isinstance(content, (str, Path)):
        path = Path(content)
        if path.suffix.lower() in IMAGE_EXTS and path.exists():
            return embed_image(path)

    return embed_text(str(content))
