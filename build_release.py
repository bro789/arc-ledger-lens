"""Create curated static deployment and source-review ZIPs; does not publish anything."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent
release = root / "release"
release.mkdir(exist_ok=True)
static_files = [root / "web" / x for x in ("index.html", "style.css", "app.js", "rpc.js", "LICENSE", "logo.svg", "logo.png", "evidence/demo-bundle.json")]
source_names = ["README.md", "LICENSE", ".gitignore", "arc_lens.py", "server.py", "capture_demo.py", "build_release.py", "build_logo.py", "assets/logo.svg", "assets/logo.png", "test_arc_lens.py", "test_browser_core.js", "submission/draft.md", "submission/demo-script.md", "evidence/account-mainnet.json", "evidence/transaction-mainnet.json", "evidence/demo-bundle.json"]
results = []
for name, files, base in (("arc-ledger-lens-static.zip", static_files, root / "web"),
                          ("arc-ledger-lens-source.zip", [root / x for x in source_names] + static_files, root)):
    path = release / name
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.relative_to(base).as_posix())
    results.append({"file": str(path), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "entries": len(files)})
(release / "manifest.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, indent=2))
