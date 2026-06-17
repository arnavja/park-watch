"""Build a stratified sample for the public demo deployment.

The raw 105 MB BTP CSV cannot be committed (license + size).
This script extracts a small (~30K row) stratified sample that
preserves the hourly + police-station distribution, lets the
dashboard run on Streamlit Cloud without the raw file.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
SRC = ROOT / "data" / "violations.parquet"
OUT = ROOT / "data" / "sample_violations.parquet"
SAMPLE_SIZE = 30_000

df = pd.read_parquet(SRC)
print(f"Source: {len(df):,} rows")

# Stratify by (police_station, hour) so distribution is preserved
stratum = df["police_station"].fillna("unknown") + "|" + df["hour"].astype(str)
frac = SAMPLE_SIZE / len(df)
sample = df.groupby(stratum, group_keys=False).apply(
    lambda g: g.sample(max(1, int(len(g) * frac)), random_state=1)
).reset_index(drop=True)

print(f"Sample: {len(sample):,} rows  ({100*len(sample)/len(df):.1f}%)")
sample.to_parquet(OUT, index=False, compression="snappy")
size_mb = OUT.stat().st_size / 1024 / 1024
print(f"Wrote {OUT}  ({size_mb:.1f} MB)")
