---
pretty_name: Second Life Demo Data
task_categories:
- tabular-classification
- text-retrieval
tags:
- clinical-trials
- synthetic-data
- synthea
- clinicaltrials-gov
---

# Second Life Demo Data

This dataset repository stores the large files used by the Second Life class
project Space.

## Files

- `Final Clinical Trails Data.zip`: processed ClinicalTrials.gov trial tables.
- `Final Patients Synthea Data.zip`: generated Synthea patient tables.
- `Second_Life_Project_Documentation.docx`: project documentation.
- `Architecture Diagrams/`: editable and presentable architecture artifacts.

## Use In The Space

The app Space downloads the two zip files at startup and extracts them into the
folder names expected by `pipeline.py`:

- `Final Clinical Trails Data`
- `Final Patients Synthea Data`

## Data Notice

The patient records are synthetic/generated data for a class project demo. The
trial records are processed from public clinical-trial metadata. MIMIC-IV data is
not uploaded here because it has separate access and licensing requirements.
