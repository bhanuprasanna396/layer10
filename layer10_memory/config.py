from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = ROOT / "outputs"

SCHEMA_VERSION = "1.0.0"
EXTRACTION_VERSION = "extractor=v1|schema=1.0.0"
