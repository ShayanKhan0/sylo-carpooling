# Machine Learning Verification Notebooks

This folder contains real, standalone notebook workflows for verification using pretrained models.

## Notebooks

- 01_FaceNet_Verification_Pipeline.ipynb
- 02_Tesseract_Identity_Verification_Pipeline.ipynb

## Principles

- No backend integration
- No frontend integration
- Reproducible evaluation with dataset CSVs
- JSON report output for evidence in academic review

## Setup

1. Create and activate Python environment.
2. Install dependencies:

   pip install -r requirements.txt

3. Install system Tesseract engine.

## Input CSV files

- data/facenet_pairs.csv
- data/ocr_identity_examples.csv

## Output

The notebooks write reports into:

- reports/facenet_report.json
- reports/tesseract_report.json

## Academic presentation guidance

Use these points honestly:

- We use pretrained FaceNet and pretrained Tesseract.
- We did not train deep models from scratch.
- We calibrated and evaluated performance on labeled test pairs/examples.
