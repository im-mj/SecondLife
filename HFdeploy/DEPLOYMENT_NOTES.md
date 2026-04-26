# Hugging Face Deployment Files

This folder keeps the Hugging Face deployment-specific files for organization
and handoff.

## App Space

- Space repo: `MrNoOne07/second-life`
- Live URL: `https://mrnoone07-second-life.hf.space`
- SDK: Docker
- App port: `7860`

Deployment files used by the Space:

- `Dockerfile`
- `README.md`
- `requirements.txt`
- `.hfignore`
- `hf_space_bootstrap.py`

The deployed app also needs the main project files from the repository root:

- `app.py`
- `pipeline.py`
- `database.py`
- `templates/`
- `static/`
- `secondlife.db`
- `model_cache.pkl`
- `login.md`

## Dataset Repo

- Dataset repo: `MrNoOne07/second-life-data`

Files uploaded to the Dataset repo:

- `Final Clinical Trails Data.zip`
- `Final Patients Synthea Data.zip`
- `Second_Life_Project_Documentation.docx`
- `Architecture Diagrams/`
- Dataset card copied from `hf_dataset_README.md`

## Important

When uploading to Hugging Face again, build a clean upload/staging folder that
contains these `HFdeploy` files at the upload root together with the main app
files listed above. Hugging Face expects the Space `Dockerfile` and `README.md`
at the upload root, not inside a nested folder.
