---
title: Second Life Clinical Trial Matching
sdk: docker
app_port: 7860
pinned: false
---

# Second Life Clinical Trial Matching

Second Life is a two-portal Flask application for matching synthetic patient
profiles to clinical trials and helping hospitals identify patients who are open
to trial participation.

## Space Startup

This Hugging Face Space uses Docker. On startup, `hf_space_bootstrap.py`
downloads the required dataset zip files from the companion Dataset repository:

`MrNoOne07/second-life-data`

The app then starts `app.py` on port `7860`.

## Demo Logins

Demo credentials are documented in `login.md`.

## Data Notice

The uploaded demo data includes generated Synthea patient data and processed
ClinicalTrials.gov data for class demonstration. MIMIC-IV validation data is not
bundled in this Space by default because it has separate access and licensing
requirements.
