"""PS3.15 Annex E basic-profile subset used by MIAP.

The lists are explicit so the receipt can name exactly what was changed.
"""

REPLACE: dict[str, str] = {
    "PatientName": "ANON^MIAP",
    "PatientID": "MIAP-ANON",
    "IssuerOfPatientID": "",
    "OtherPatientIDs": "",
    "OtherPatientNames": "",
    "PatientAddress": "",
    "PatientTelephoneNumbers": "",
    "PatientMotherBirthName": "",
    "AccessionNumber": "",
    "StudyID": "",
    "InstitutionName": "",
    "InstitutionAddress": "",
    "InstitutionalDepartmentName": "",
    "ReferringPhysicianName": "",
    "ReferringPhysicianAddress": "",
    "ReferringPhysicianTelephoneNumbers": "",
    "PerformingPhysicianName": "",
    "OperatorsName": "",
    "PhysiciansOfRecord": "",
    "RequestingPhysician": "",
    "StationName": "",
    "DeviceSerialNumber": "",
    "ManufacturerModelName": "MIAP",
    "SoftwareVersions": "MIAP",
    "ImageComments": "",
    "PatientComments": "",
    "StudyDescription": "",
    "SeriesDescription": "",
    "ProtocolName": "",
    "RequestedProcedureDescription": "",
    "PerformedProcedureStepDescription": "",
    "AdmissionID": "",
    "VisitComments": "",
    "PatientInsurancePlanCodeSequence": "",
}

REMOVE: tuple[str, ...] = (
    "PatientBirthDate",
    "PatientSex",
    "PatientAge",
    "PatientSize",
    "PatientWeight",
    "PatientState",
    "PatientReligiousPreference",
    "EthnicGroup",
    "StudyDate",
    "SeriesDate",
    "AcquisitionDate",
    "ContentDate",
    "InstanceCreationDate",
    "StudyTime",
    "SeriesTime",
    "AcquisitionTime",
    "ContentTime",
    "InstanceCreationTime",
    "AcquisitionDateTime",
    "DateOfLastCalibration",
    "TimeOfLastCalibration",
    "DigitalSignatureUID",
    "EncryptedAttributesSequence",
    "OriginalAttributesSequence",
)

# Retained because they are needed to run and interpret the image, and are not
# direct identifiers. The receipt records that they were kept.
RETAIN: tuple[str, ...] = (
    "Modality",
    "BodyPartExamined",
    "Laterality",
    "ViewPosition",
    "PatientOrientation",
    "ImageLaterality",
    "PixelSpacing",
    "ImagerPixelSpacing",
    "Rows",
    "Columns",
    "PhotometricInterpretation",
    "BitsAllocated",
    "BitsStored",
    "HighBit",
    "PixelRepresentation",
    "SamplesPerPixel",
    "RescaleIntercept",
    "RescaleSlope",
    "WindowCenter",
    "WindowWidth",
    "VOILUTFunction",
    "PresentationIntentType",
    "Manufacturer",
    "KVP",
    "Exposure",
    "ExposureTime",
    "XRayTubeCurrent",
    "DistanceSourceToDetector",
    "DistanceSourceToPatient",
)

SAFE_UID_KEYWORDS = {"TransferSyntaxUID"}


def is_remappable_uid(keyword: str) -> bool:
    if keyword in SAFE_UID_KEYWORDS:
        return False
    return not keyword.endswith("ClassUID")
