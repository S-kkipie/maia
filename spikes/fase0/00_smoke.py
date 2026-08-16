import importlib.metadata as md
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401  (el import dispara el guard de API key)

for pkg in ("claude-agent-sdk", "pipecat-ai", "python-dotenv"):
    try:
        print(f"{pkg}: {md.version(pkg)}")
    except md.PackageNotFoundError:
        sys.exit(f"Paquete no instalado: {pkg}")

cred = pathlib.Path.home() / ".claude" / ".credentials.json"
if not cred.exists():
    sys.exit(f"No hay credentials.json en {cred} — corre `claude /login`.")
print("credentials.json: OK")
print("Smoke OK")
