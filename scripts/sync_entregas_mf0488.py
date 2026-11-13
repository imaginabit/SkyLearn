"""Sincroniza entregas de mf0488 con las carpetas locales.

Lee scripts/manifest_entregas_mf0488.ndjson y, para cada Submission:
- resuelve la carpeta del alumno por username (`alumnos/*-ugr-2026-X/MF0488_3/actividades/`)
- si ya existe un fichero con el nombre destino, lo salta
- si no, hace `scp` desde el servidor

Genera scripts/.sync_entregas_resultado.json con el resultado por entrada.
"""
import json, os, re, subprocess, sys, hashlib
from pathlib import Path

BASE = Path("C:/Users/SeguridadInformatica/Documents/seguridad-informatica-2026")
ALUMNOS = BASE / "alumnos"
MANIFEST = Path("scripts/manifest_entregas_mf0488.ndjson")
OUT = Path("scripts/.sync_entregas_resultado.json")

# Índice por username -> carpeta
def build_alumno_index():
    idx = {}
    for d in sorted(ALUMNOS.iterdir()):
        if not d.is_dir():
            continue
        m = re.search(r"-ugr-2026-\d+$", d.name)
        if m:
            idx[m.group(0).lstrip("-")] = d
    return idx

def sha256(path, blocksize=65536):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(blocksize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def main():
    idx = build_alumno_index()
    entries = [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    results = []
    for e in entries:
        username = e["username"]
        folder = idx.get(username)
        if not folder:
            results.append({**e, "status": "NO_FOLDER", "target": None})
            continue
        target_dir = folder / "MF0488_3" / "actividades"
        if not target_dir.exists():
            results.append({**e, "status": "NO_TARGET_DIR", "target": str(target_dir)})
            continue
        target_name = f"{e['code']}_{username}_{e['original_filename']}"
        target = target_dir / target_name
        if target.exists():
            results.append({**e, "status": "EXISTS", "target": str(target)})
            continue
        # scp
        rel = e["remote_path"]
        # Usamos sudo cat + ssh para evitar problemas de permisos con www-data.
        # Lo más simple: probar scp directo; si falla, hacer fallback por sudo.
        cmd = ["scp", f"debian@imaginabit.com:{rel}", str(target)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
            if target.exists():
                results.append({**e, "status": "OK", "target": str(target)})
            else:
                results.append({**e, "status": "SCP_NO_FILE", "target": str(target), "stderr": r.stderr})
        except subprocess.CalledProcessError as ex:
            # Fallback: copiar con sudo a /tmp y luego bajarlo
            tmp_remote = f"/tmp/entrega_tmp_{e['pk']}_{target_name}"
            ssh_cp = subprocess.run(
                ["ssh", "debian@imaginabit.com", f"sudo cp '{rel}' '{tmp_remote}' && sudo chown debian:debian '{tmp_remote}'"],
                capture_output=True, text=True, timeout=60,
            )
            if ssh_cp.returncode != 0:
                results.append({**e, "status": "SCP_FAIL", "stderr": ex.stderr + " | " + ssh_cp.stderr, "target": str(target)})
                continue
            r2 = subprocess.run(["scp", f"debian@imaginabit.com:{tmp_remote}", str(target)],
                                capture_output=True, text=True, timeout=60)
            subprocess.run(["ssh", "debian@imaginabit.com", f"rm -f '{tmp_remote}'"],
                           capture_output=True, text=True)
            if target.exists():
                results.append({**e, "status": "OK_VIA_SUDO", "target": str(target)})
            else:
                results.append({**e, "status": "SCP_FAIL_2", "stderr": ex.stderr + " | " + r2.stderr, "target": str(target)})
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    # Resumen
    by_status = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r)
    print(f"Total: {len(results)}")
    for k, v in by_status.items():
        print(f"  {k}: {len(v)}")
    for r in results:
        print(f"  - pk={r['pk']:>3} {r['username']:>12} {r['code']:<14} -> {r['status']:<10} {r.get('target','')}")

if __name__ == "__main__":
    main()
