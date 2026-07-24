"""Copy the validated single-file game into the Sites public asset directory."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent.parent
source = ROOT / "trade-risk-sim.html"
target = ROOT / "site-host" / "public" / "trade-risk-sim.html"

if not source.exists():
    raise FileNotFoundError(source)

target.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(source, target)

if source.read_bytes() != target.read_bytes():
    raise RuntimeError("Synced game differs from validated source")

print(f"synced {target.stat().st_size} bytes")
