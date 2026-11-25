// Replays the golden games inside Pyodide (the browser's Python) and checks the same state
// hashes CPython checks in engine/tests/test_golden.py. A mismatch means the two runtimes
// would disagree about a match, which breaks replays and browser practice.
import { loadPyodide } from "pyodide";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const engine = join(dirname(fileURLToPath(import.meta.url)), "..");
const pyodide = await loadPyodide();

function copyDir(from, to, suffix) {
	pyodide.FS.mkdirTree(to);
	for (const name of readdirSync(from).filter((n) => n.endsWith(suffix))) {
		pyodide.FS.writeFile(`${to}/${name}`, readFileSync(join(from, name)));
	}
}

copyDir(join(engine, "src", "arena_engine"), "/arena/arena_engine", ".py");
copyDir(join(engine, "tests", "golden"), "/arena/golden", ".json.gz");
pyodide.FS.writeFile("/arena/golden_check.py", readFileSync(join(engine, "tests", "golden_check.py")));

const report = pyodide.runPython(`
import sys
sys.path.insert(0, "/arena")
from pathlib import Path
import golden_check

count, problems = golden_check.check_all(Path("/arena/golden"))
header = f"Pyodide {sys.version.split()[0]} ({sys.platform}): {count} golden games"
"\\n".join([header, *problems, "ok" if count and not problems else "FAILED"])
`);
console.log(report);
process.exitCode = report.endsWith("ok") ? 0 : 1;
