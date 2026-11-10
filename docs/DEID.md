# De-identification

MIAP removes direct identifiers from every uploaded file before it becomes a
case image. De-identification is mandatory and cannot be skipped: the upload
path never stores the original bytes. Each upload returns a receipt (stored in
the image record) naming exactly what was changed, and the receipt is included
in the case workspace so a reviewer can see what happened to the file.

Pipeline version: `ps3.15-basic-subset/1.0` for DICOM,
`exif-strip-raster/1.0` for PNG/JPEG.

## DICOM

The implementation follows the DICOM PS3.15 Annex E *Basic Application Level
Confidentiality Profile* as a fixed subset. The lists live in
`backend/app/modules/deid/tags.py` so the receipt can name every tag, rather
than hiding the decisions in code paths.

### Replaced (present but overwritten)

| Tag | Replacement |
| --- | --- |
| PatientName | `ANON^MIAP` |
| PatientID | `MIAP-ANON` |
| IssuerOfPatientID, OtherPatientIDs, OtherPatientNames | empty |
| AccessionNumber, StudyID | empty |
| InstitutionName, InstitutionAddress, InstitutionalDepartmentName | empty |
| Referring/Performing/Requesting Physician and related names | empty |
| OperatorsName, PhysiciansOfRecord | empty |
| StationName, DeviceSerialNumber | empty |
| ManufacturerModelName, SoftwareVersions | `MIAP` / `MIAP` |
| StudyDescription, SeriesDescription, ProtocolName | empty |
| Requested/PerformedProcedureStepDescription, VisitComments | empty |

Added on every file: `PatientIdentityRemoved = YES`,
`DeidentificationMethod = ps3.15-basic-subset/1.0`, `SeriesDescription =
MIAP de-identified`.

### Removed (deleted when present)

All dates and times of care (`StudyDate`, `SeriesDate`, `AcquisitionDate`,
`InstanceCreationDate`, and their times, plus `AcquisitionDateTime` and
calibration timestamps); demographics (`PatientBirthDate`, `PatientSex`,
`PatientAge`, `PatientSize`, `PatientWeight`, `PatientState`,
`PatientReligiousPreference`, `EthnicGroup`); signatures and history
(`DigitalSignatureUID`, `EncryptedAttributesSequence`,
`OriginalAttributesSequence`). All private tags are removed unconditionally.

### Retained (needed to display and interpret the image)

`Modality`, `BodyPartExamined`, `Laterality`, `ViewPosition`,
`PatientOrientation`, `ImageLaterality`, geometry and pixel description
(`Rows`, `Columns`, `PixelSpacing`, `ImagerPixelSpacing`, `PhotometricInterpretation`,
`BitsAllocated`, `BitsStored`, `HighBit`, `PixelRepresentation`,
`SamplesPerPixel`), display calibration (`RescaleIntercept`, `RescaleSlope`,
`WindowCenter`, `WindowWidth`, `VOILUTFunction`), and acquisition technique
(`Manufacturer`, `KVP`, `Exposure`, `ExposureTime`, `XRayTubeCurrent`,
source-to-detector and source-to-patient distances). The receipt lists the
retained tags so their presence is auditable.

### UID remapping

Every instance UID (and the file-meta `MediaStorageSOPInstanceUID`) is
replaced with a keyed, deterministic value of the form `2.25.<128-bit
integer>`, computed with HMAC-SHA-256 over the original UID using the
application secret. Properties:

- the same input UID always maps to the same output UID, so series that
  belong together stay together;
- without the secret the mapping cannot be reversed or reproduced;
- **the mapping key is not retained by MIAP** (`reidentification_key_retained:
  false` in the receipt). There is no re-identification path, by design.

Class UIDs and `TransferSyntaxUID` are not remapped: rewriting them would
break decoding.

## Raster images (PNG/JPEG)

There is no DICOM header to enumerate, so the raster path re-encodes the
image (PNG optimized, or JPEG quality 95) and drops EXIF, XMP and any embedded
ICC profile. The receipt records `exif-strip-raster/1.0`, the input/output
SHA-256 and a warning that modality and body region had to be chosen manually
or guessed, because a raster carries no acquisition metadata.

## Burned-in annotation

If the DICOM declares `BurnedInAnnotation = YES`, the receipt carries a
warning that pixel-embedded text cannot be removed and the image must be
reviewed before sharing. MIAP does not attempt OCR or inpainting of pixels:
altering pixels would change the diagnostic content.

## What a receipt contains

```
pipeline                       ps3.15-basic-subset/1.0
sha256_in / sha256_out         hash of input and output bytes
removed / replaced / retained  sorted tag keyword lists
uids_remapped                  count of remapped UIDs
reidentification_key_retained  always false
warnings                       human-readable caveats
```

The receipt is attached to the image (`Image.deid_json`), shown in the case
workspace and included in the audit trail for the upload event.

## Known limits

- This is a fixed subset, not a full PS3.15 profile implementation: no
  configurable profile, no date shifting, no `CleanPixelDataOption`.
- Burned-in annotation, photographic identifyers in the pixel data, and
  identifiers in free-text sequence content outside the named tags are not
  detected.
- The HMAC secret is the application secret key. Rotating it changes future
  remaps but does not affect images already stored.
- De-identification is prevention, not certification. The MVP intends
  research/teaching use with synthetic or consented data, and every result
  page repeats that the output is decision support, not a diagnosis.
