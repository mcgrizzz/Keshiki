import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Import the inner package as `keshiki` without the root __init__ (which needs a
# running Anki). Kiso's pytest plugin bundles keshiki/_kiso/ before tests import it.
sys.path.insert(0, str(ROOT))
