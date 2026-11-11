"""Generate synthetic DICOM and raster fixtures. No patient data is used."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "backend" / "tests" / "fixtures" / "generated"


def _pixels(rows: int = 512, cols: int = 512, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:rows, 0:cols]
    gradient = (xx / cols) * 1800 + (yy / rows) * 900
    noise = rng.normal(0, 40, size=(rows, cols))
    return np.clip(gradient + noise, 0, 4095).astype(np.uint16)


def make_dicom(
    path: Path,
    *,
    modality: str = "DX",
    body_part: str | None = "CHEST",
    laterality: str | None = None,
    view: str | None = None,
    photometric: str = "MONOCHROME2",
    patient_name: str = "TEST^PATIENT",
    patient_id: str = "MRN-987654",
    seed: int = 0,
    rows: int = 512,
    cols: int = 512,
) -> Path:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    dataset = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID = generate_uid()
    dataset.SeriesInstanceUID = generate_uid()
    dataset.FrameOfReferenceUID = generate_uid()
    dataset.Modality = modality
    if body_part:
        dataset.BodyPartExamined = body_part
    if laterality:
        dataset.Laterality = laterality
        dataset.ImageLaterality = laterality
    if view:
        dataset.ViewPosition = view

    dataset.PatientName = patient_name
    dataset.PatientID = patient_id
    dataset.PatientBirthDate = "19700101"
    dataset.PatientSex = "F"
    dataset.AccessionNumber = "ACC-2026-0001"
    dataset.StudyDate = "20260101"
    dataset.StudyTime = "101500"
    dataset.StudyDescription = "SYNTHETIC TEST STUDY"
    dataset.InstitutionName = "TEST HOSPITAL"
    dataset.ReferringPhysicianName = "DOCTOR^TEST"
    dataset.StationName = "TEST-STATION"
    dataset.DeviceSerialNumber = "SN-123456"
    dataset.ImageComments = "synthetic fixture"

    dataset.Rows = rows
    dataset.Columns = cols
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = photometric
    dataset.BitsAllocated = 16
    dataset.BitsStored = 12
    dataset.HighBit = 11
    dataset.PixelRepresentation = 0
    dataset.RescaleSlope = 1
    dataset.RescaleIntercept = 0
    dataset.PixelData = _pixels(rows, cols, seed).tobytes()

    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.save_as(path, enforce_file_format=True)
    return path


def make_raster(out: Path) -> None:
    from PIL import Image

    array = (_pixels(512, 512, 3) / 4095 * 255).astype(np.uint8)
    image = Image.fromarray(array, mode="L")
    exif = Image.Exif()
    exif[0x010F] = "TestCamera"
    exif[0x0110] = "TestModel"
    exif[0x0132] = "2026:01:01 10:15:00"
    image.save(out / "chest.png", exif=exif)
    image.convert("RGB").save(out / "chest.jpg", quality=92)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    make_dicom(out / "chest_pa.dcm", seed=1)
    make_dicom(out / "chest_mono1.dcm", seed=2, photometric="MONOCHROME1")
    make_dicom(out / "skull_ap.dcm", seed=3, body_part="SKULL")
    make_dicom(out / "chest_small.dcm", seed=4, rows=96, cols=96)
    make_dicom(out / "hand_pa.dcm", seed=5, body_part="HAND", laterality="L", view="PA")
    make_dicom(out / "hip_ap.dcm", seed=6, body_part="HIP", laterality="R", view="AP")

    mammo = out / "mammo_four_view"
    for index, (laterality, view) in enumerate(
        [("L", "CC"), ("R", "CC"), ("L", "MLO"), ("R", "MLO")]
    ):
        make_dicom(
            mammo / f"{laterality}{view}.dcm",
            modality="MG",
            body_part=None,
            laterality=laterality,
            view=view,
            seed=10 + index,
            rows=640,
            cols=480,
        )

    three = out / "mammo_three_view"
    for index, (laterality, view) in enumerate([("L", "CC"), ("R", "CC"), ("L", "MLO")]):
        make_dicom(
            three / f"{laterality}{view}.dcm",
            modality="MG",
            body_part=None,
            laterality=laterality,
            view=view,
            seed=20 + index,
            rows=640,
            cols=480,
        )

    duplicate = out / "mammo_duplicate"
    for name, laterality, view, seed in [
        ("LCC_a", "L", "CC", 30),
        ("LCC_b", "L", "CC", 31),
        ("RCC", "R", "CC", 32),
        ("LMLO", "L", "MLO", 33),
        ("RMLO", "R", "MLO", 34),
    ]:
        make_dicom(
            duplicate / f"{name}.dcm",
            modality="MG",
            body_part=None,
            laterality=laterality,
            view=view,
            seed=seed,
            rows=640,
            cols=480,
        )

    make_raster(out)
    (out / "corrupt.dcm").write_bytes(b"this is not a dicom file")
    print(f"Fixtures written to {out}")


if __name__ == "__main__":
    main()
