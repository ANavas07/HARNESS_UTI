"""Ejecuta un eval definido en evals/: copia aislada, N corridas, grader y reporte JSON.

Requiere Python 3.10+ y PyYAML (requirements-evals.txt). El agente es un comando
externo; el runner no llama a ningun modelo por si mismo.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = PROJECT_ROOT / "evals"
SIGNALS = ("intentos_hasta_verde", "comandos_fallidos", "preguntas_humano",
           "tokens_entrada", "tokens_salida", "llamadas_modelo",
           "hasta_primer_test_valido_s")
STEP_KEYS = {"nombre", "run", "exit", "stderr_no_contiene", "archivo_existe",
             "sin_cambios", "solo_modifica"}
IGNORED_PARTS = {"__pycache__", ".pytest_cache"}
STEP_TIMEOUT_S = 300


def load_eval(path):
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("Falta PyYAML: pip install -r requirements-evals.txt") from exc
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    request = "entrada" if data.get("capa") == "runtime" else "tarea"
    for key in ("id", "estado", request, "grader", "umbral"):
        if key not in data:
            raise SystemExit(f"Eval invalido: falta '{key}'")
    return data


def git(*args):
    return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True,
                          check=True).stdout


def excluded(rel, prefixes):
    return any(rel == p.rstrip("/") or rel.startswith(p.rstrip("/") + "/") for p in prefixes)


def materialize(dest, origin, exclude):
    """Copia el repositorio sin los prefijos excluidos; devuelve (commit, sucio)."""
    commit = git("rev-parse", "HEAD").decode().strip()
    dirty = bool(git("status", "--porcelain").strip())
    dest.mkdir(parents=True)
    if origin == "head":
        with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", "HEAD"))) as tar:
            members = [m for m in tar.getmembers() if not excluded(m.name, exclude)]
            safe = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
            tar.extractall(dest, members=members, **safe)
        return commit, False
    for rel in git("ls-files", "-co", "--exclude-standard", "-z").decode().split("\0"):
        if rel and not excluded(rel, exclude) and (PROJECT_ROOT / rel).is_file():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT_ROOT / rel, target)
    return commit, dirty


def snapshot(root):
    hashes = {}
    for path in root.rglob("*"):
        if path.is_file() and not IGNORED_PARTS.intersection(path.parts) and path.suffix != ".pyc":
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def changed(before, after):
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


def expand(text, places):
    for key, value in places.items():
        text = text.replace("{" + key + "}", value)
    if text.startswith("python "):
        text = f'"{sys.executable}" ' + text[len("python "):]
    return text


def run_shell(command, cwd, timeout, env=None):
    """Ejecuta con limite de tiempo y termina el arbol de procesos al vencer."""
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" \
        else {"start_new_session": True}
    proc = subprocess.Popen(command, cwd=cwd, shell=True, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        return None, out, err, True


def grade(steps, repo, places, initial, agent_changes, env):
    results = []
    for number, step in enumerate(steps, 1):
        started = time.monotonic()
        result = {"paso": number, "nombre": step.get("nombre", ""), "ok": True, "detalle": []}
        unknown = set(step) - STEP_KEYS
        if unknown:
            result.update(ok=False, no_soportado=sorted(unknown))
        if "run" in step and not unknown:
            code, out, err, timed_out = run_shell(expand(step["run"], places), repo, STEP_TIMEOUT_S, env)
            result["exit"] = code
            if timed_out:
                result["ok"] = False
                result["detalle"].append(f"supero {STEP_TIMEOUT_S} s")
            elif "exit" in step and code != step["exit"]:
                result["ok"] = False
                result["detalle"].append(f"exit {code}, esperado {step['exit']}")
            if step.get("stderr_no_contiene") and step["stderr_no_contiene"] in (err or ""):
                result["ok"] = False
                result["detalle"].append(f"stderr contiene {step['stderr_no_contiene']!r}")
            if not result["ok"]:
                result["stderr_final"] = (err or "")[-800:]
        if "archivo_existe" in step and not unknown:
            if not Path(expand(step["archivo_existe"], places)).is_file():
                result["ok"] = False
                result["detalle"].append("archivo esperado no existe")
        if "sin_cambios" in step and not unknown:
            current = snapshot(repo)
            altered = [p for p in step["sin_cambios"] if current.get(p) != initial.get(p)]
            if altered:
                result["ok"] = False
                result["detalle"].append(f"modificados: {altered}")
        if "solo_modifica" in step and not unknown:
            outside = [p for p in agent_changes if not excluded(p, step["solo_modifica"])]
            if outside:
                result["ok"] = False
                result["detalle"].append(f"fuera del alcance: {outside}")
        result["duracion_s"] = round(time.monotonic() - started, 3)
        results.append(result)
    return results


def read_signals(path):
    values = dict.fromkeys(SIGNALS)
    if path.is_file():
        try:
            reported = json.loads(path.read_text(encoding="utf-8"))
            values.update({k: reported[k] for k in SIGNALS if k in reported})
        except (json.JSONDecodeError, OSError):
            values["error_lectura"] = True
    return values


def run_once(spec, mode, agent, origin, index, stamp):
    kind = "" if mode == "agente" else f"-{mode.replace('_', '-')}"
    run_id = f"{spec['id']}{kind}-{stamp}-{index:02d}"
    environment = spec.get("entorno", {})
    budget = spec.get("presupuesto", {})
    record = {"run_id": run_id, "eval_id": spec["id"], "capa": spec.get("capa"),
              "tipo": mode, "origen": origin,
              "red": "no_restringida_por_el_runner" if environment.get("red") else None,
              "iniciado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="eval-") as tmp:
        repo, scratch = Path(tmp) / "repo", Path(tmp) / "tmp"
        scratch.mkdir()
        try:
            record["commit_base"], record["arbol_sucio"] = materialize(
                repo, origin, environment.get("excluir", ["evals/"]))
        except (subprocess.CalledProcessError, OSError) as exc:
            record.update(resultado="environment_error", error=str(exc))
            return record
        places = {"evals": EVALS_DIR.as_posix(), "tmp": scratch.as_posix(), "repo": repo.as_posix()}
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        initial = snapshot(repo)
        agent_s = 0.0
        timed_out = False
        if mode == "control_positivo":
            solution = EVALS_DIR / spec.get("solucion", "")
            if not spec.get("solucion") or not solution.is_dir():
                record.update(resultado="environment_error", error="eval sin 'solucion' de referencia")
                return record
            shutil.copytree(solution, repo, dirs_exist_ok=True)
        elif mode == "agente":
            task_file, signals_file = Path(tmp) / "tarea.md", Path(tmp) / "senales.json"
            task_file.write_text(spec["tarea"], encoding="utf-8")
            agent_env = {**env, "EVAL_TAREA": str(task_file), "EVAL_SENALES": str(signals_file),
                         "EVAL_REPO": str(repo), "EVAL_ID": spec["id"], "EVAL_RUN_ID": run_id}
            agent_started = time.monotonic()
            code, out, err, timed_out = run_shell(
                agent, repo, budget.get("tiempo_max_s", 600), agent_env)
            agent_s = time.monotonic() - agent_started
            record["agente"] = {"exit": code, "supero_plazo": timed_out,
                                "stdout_final": (out or "")[-800:], "stderr_final": (err or "")[-800:]}
            record["senales"] = read_signals(signals_file)
        agent_changes = changed(initial, snapshot(repo))
        record["archivos_modificados"] = agent_changes
        grader_started = time.monotonic()
        steps = grade(spec["grader"], repo, places, initial, agent_changes, env)
        record["grader"] = steps
        if any(s.get("no_soportado") for s in steps):
            record["resultado"] = "environment_error"
        elif timed_out:
            record["resultado"] = "budget_exceeded"
        else:
            record["resultado"] = "accepted" if all(s["ok"] for s in steps) else "failed"
        record["tiempos_s"] = {"total": round(time.monotonic() - started, 3),
                               "agente": round(agent_s, 3),
                               "grader": round(time.monotonic() - grader_started, 3)}
    if mode.startswith("control"):
        expected = "accepted" if mode == "control_positivo" else "failed"
        record["control_correcto"] = record["resultado"] == expected
    return record


def summarize(spec, mode, records):
    counts = {}
    for r in records:
        counts[r["resultado"]] = counts.get(r["resultado"], 0) + 1
    accepted = counts.get("accepted", 0)
    rate = accepted / len(records)
    summary = {"eval_id": spec["id"], "tipo": mode, "corridas": len(records),
               "resultados": counts, "tasa_exito": round(rate, 3),
               "run_ids": [r["run_id"] for r in records]}
    totals = [r["tiempos_s"]["total"] for r in records if "tiempos_s" in r]
    if totals:
        summary["mediana_tiempo_s"] = round(statistics.median(totals), 3)
    if mode == "agente":
        threshold = 1.0 if spec.get("critico") else spec["umbral"]["tasa_minima"]
        summary.update(umbral=threshold, cumple=rate >= threshold)
        for key in SIGNALS:
            values = [r["senales"][key] for r in records if r.get("senales", {}).get(key) is not None]
            summary[f"mediana_{key}"] = statistics.median(values) if values else None
    else:
        summary["cumple"] = all(r.get("control_correcto") for r in records)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval", type=Path, help="Archivo YAML del eval")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--agente", help="Comando del agente; recibe EVAL_TAREA, EVAL_SENALES y EVAL_REPO")
    group.add_argument("--control", choices=["negativo", "positivo"])
    parser.add_argument("--corridas", type=int, help="N; por defecto el del eval (controles: 1)")
    parser.add_argument("--origen", choices=["head", "trabajo"], default="head",
                        help="head: commit actual; trabajo: archivos locales sin commit (se marca sucio)")
    parser.add_argument("--salida", type=Path, default=PROJECT_ROOT / "reports/evals")
    parser.add_argument("--forzar", action="store_true", help="Ejecutar aunque el estado no sea 'ejecutable'")
    args = parser.parse_args(argv)

    spec = load_eval(args.eval)
    if spec.get("capa") == "runtime":
        print(f"{spec['id']}: los evals de runtime requieren el ejecutor del agente de calendario",
              file=sys.stderr)
        return 2
    if spec["estado"] != "ejecutable" and not args.forzar:
        print(f"{spec['id']}: estado '{spec['estado']}', no ejecutable", file=sys.stderr)
        return 2
    mode = f"control_{args.control}" if args.control else "agente"
    runs = args.corridas or (1 if args.control else spec.get("corridas", 5))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.salida / f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for index in range(1, runs + 1):
        record = run_once(spec, mode, args.agente, args.origen, index, stamp)
        (out_dir / f"{record['run_id']}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        failed = [s["paso"] for s in record.get("grader", []) if not s["ok"]]
        print(f"[{index}/{runs}] {record['resultado']}"
              + (f" (pasos fallidos: {failed})" if failed else ""), flush=True)
        records.append(record)

    summary = summarize(spec, mode, records)
    kind = "" if mode == "agente" else f"-{mode.replace('_', '-')}"
    (out_dir / f"{spec['id']}{kind}-{stamp}-resumen.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["cumple"] else 1


if __name__ == "__main__":
    sys.exit(main())
