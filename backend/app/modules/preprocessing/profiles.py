"""Per-model preprocessing profiles.

Each engine declares one profile in ``ml/registry.json``. The profile fixes the
input size, channel count, crop and intensity scaling so a stored result can be
reproduced from its provenance record alone.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    size: tuple[int, int]
    channels: int
    crop: str
    scale: str
    normalisation: str


PROFILES: dict[str, Profile] = {
    "xrv_chest_224": Profile(
        name="xrv_chest_224",
        size=(224, 224),
        channels=1,
        crop="centre",
        scale="xrv",
        normalisation="torchxrayvision.datasets.normalize(img, 255), centre crop, resize",
    ),
    "monai_density_299": Profile(
        name="monai_density_299",
        size=(299, 299),
        channels=3,
        crop="resize",
        scale="unit",
        normalisation="intensity [0,1], resize 299x299, grey copied to RGB",
    ),
    "siglip_bone_224": Profile(
        name="siglip_bone_224",
        size=(224, 224),
        channels=3,
        crop="resize",
        scale="half",
        normalisation="intensity [0,1], resize 224x224, grey copied to RGB, (x-0.5)/0.5",
    ),
}


def profile_for(name: str | None) -> Profile:
    if not name:
        return PROFILES["xrv_chest_224"]
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown preprocessing profile: {name}") from exc


def heatmap_mapping(profile: str | None) -> str:
    """Where the model input sits on the stored image.

    ``centre`` profiles crop a square from the middle of the radiograph;
    ``resize`` profiles resample the whole image, so the map covers all of it.
    """
    try:
        crop = profile_for(profile).crop
    except ValueError:
        return "centre"
    return "centre" if crop == "centre" else "full"
