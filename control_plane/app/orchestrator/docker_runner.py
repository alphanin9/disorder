from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import docker
import httpx
from docker.errors import DockerException, ImageNotFound, NotFound
from sqlalchemy.orm import Session

from control_plane.app.adapters.ctfd import CTFdClient
from control_plane.app.core.config import get_settings
from control_plane.app.db.models import ChallengeManifest, Run, RunResult
from control_plane.app.db.session import SessionLocal
from control_plane.app.schemas.result_contract import SandboxResult
from control_plane.app.services.auth_service import CodexAuthMaterial, get_codex_auth_material_for_tag
from control_plane.app.services.sync_service import get_ctfd_config
from control_plane.app.stop_criteria.engine import evaluate_stop_criteria
from control_plane.app.store import get_blob_store
from control_plane.app.store.minio import run_result_object_keys


@dataclass(slots=True)
class LocalDeployContext:
    network_name: str
    compose_project: str
    service_endpoints: list[dict]
    container_names: list[str]


class DockerRunner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.blob_store = get_blob_store()
        self.client = docker.DockerClient(base_url=self.settings.docker_socket)
        self.docker_bind_runs_dir = self._resolve_host_mount_path(self.settings.docker_bind_runs_dir)

    def launch_async(self, run_id: str) -> None:
        thread = threading.Thread(target=self.execute_run, args=(run_id,), daemon=True)
        thread.start()

    def execute_run(self, run_id: str) -> None:
        db = SessionLocal()
        run: Run | None = None
        container = None
        local_ctx: LocalDeployContext | None = None
        run_dir: Path | None = None

        try:
            run_uuid = UUID(run_id)
            run = db.get(Run, run_uuid)
            if run is None:
                return
            if run.status not in {"queued", "running"}:
                return

            challenge = db.get(ChallengeManifest, run.challenge_id)
            if challenge is None:
                run.status = "blocked"
                run.error_message = "Challenge not found"
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
                return

            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            run.error_message = None
            db.commit()

            run_dir = self.settings.runs_dir / str(run.id)
            chal_dir = run_dir / "chal"
            run_mount_dir = run_dir / "run"
            log_dir = run_dir / "logs"
            service_log_dir = log_dir / "services"
            log_path = log_dir / "sandbox.log"

            chal_dir.mkdir(parents=True, exist_ok=True)
            run_mount_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)
            service_log_dir.mkdir(parents=True, exist_ok=True)
            try:
                run_mount_dir.chmod(0o777)
            except OSError:
                pass

            self._hydrate_challenge_artifacts(challenge=challenge, target_dir=chal_dir)

            if run.local_deploy.get("enabled") and any(
                artifact.get("name") in {"docker-compose.yml", "compose.yml"} for artifact in challenge.artifacts
            ):
                local_ctx = self._start_local_deploy(run_id=str(run.id), challenge_dir=chal_dir)
                run.local_deploy = {
                    "enabled": True,
                    "network": local_ctx.network_name,
                    "endpoints": local_ctx.service_endpoints,
                    "service_logs": [f"logs/services/{name}.log" for name in local_ctx.container_names],
                }
                run.allowed_endpoints = [*run.allowed_endpoints, *local_ctx.service_endpoints]
                db.commit()

            spec = self._build_spec_payload(run=run, challenge=challenge)
            spec_path = run_mount_dir / "spec.json"
            spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

            self._ensure_sandbox_image()

            host_run_dir = self.docker_bind_runs_dir / str(run.id)
            host_chal_dir = host_run_dir / "chal"
            host_run_mount = host_run_dir / "run"
            auth_mount_volume = self._sandbox_auth_volumes(db=db, run_dir=run_dir, host_run_dir=host_run_dir)

            volumes = {
                str(host_chal_dir): {"bind": "/workspace/chal", "mode": "ro"},
                str(host_run_mount): {"bind": "/workspace/run", "mode": "rw"},
            }
            volumes.update(auth_mount_volume)

            cap_add: list[str] | None = None
            if self.settings.sandbox_ptrace_enabled:
                cap_add = ["SYS_PTRACE"]

            security_opt: list[str] | None = None
            if self.settings.sandbox_seccomp_unconfined:
                security_opt = ["seccomp=unconfined"]

            ida_mount = self._sandbox_ida_volumes()
            volumes.update(ida_mount)

            container = self.client.containers.run(
                self.settings.sandbox_image,
                detach=True,
                name=f"ctf-sandbox-{str(run.id)[:8]}",
                labels={"ctf_harness.run_id": str(run.id)},
                user="1000:1000",
                mem_limit=self.settings.default_mem_limit,
                nano_cpus=int(self.settings.default_cpu_limit * 1_000_000_000),
                pids_limit=self.settings.default_pids_limit,
                volumes=volumes,
                network=local_ctx.network_name if local_ctx else None,
                environment=self._sandbox_environment(),
                cap_add=cap_add,
                security_opt=security_opt,
            )

            log_thread = threading.Thread(target=self._stream_logs, args=(container, log_path), daemon=True)
            log_thread.start()

            max_minutes = int(run.budgets.get("max_minutes", 30))
            timed_out = False
            try:
                wait_result = container.wait(timeout=max_minutes * 60)
                status_code = int(wait_result.get("StatusCode", 1))
            except Exception:
                timed_out = True
                status_code = 124
                try:
                    container.kill()
                except DockerException:
                    pass

            log_thread.join(timeout=10)

            if timed_out:
                self._write_blocked_result(
                    run_mount_dir=run_mount_dir,
                    challenge=challenge,
                    reason="Run timed out before completion",
                    status="blocked",
                )
                final_status = "timeout"
                run.error_message = "Run timed out"
            else:
                final_status = "blocked" if status_code != 0 else "blocked"
                if status_code != 0:
                    run.error_message = f"Sandbox exited with status code {status_code}"

            result_path = run_mount_dir / "result.json"
            readme_path = run_mount_dir / "README.md"

            if not result_path.exists() or not readme_path.exists():
                self._write_blocked_result(
                    run_mount_dir=run_mount_dir,
                    challenge=challenge,
                    reason="Sandbox output contract missing result.json or README.md",
                    status="blocked",
                )

            result_data, validated = self._load_validated_result(
                run_mount_dir=run_mount_dir,
                challenge=challenge,
            )

            if final_status != "timeout":
                stop_eval = evaluate_stop_criteria(run.stop_criteria, result_data, run_mount_dir)
                result_data["stop_criterion_met"] = stop_eval.stop_criterion_met
                result_data["status"] = stop_eval.final_status
                if stop_eval.final_status == "flag_found":
                    result_data = self._verify_flag_result(db=db, challenge=challenge, result_data=result_data)
                result_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
                validated = SandboxResult.model_validate(result_data)
                final_status = stop_eval.final_status

            result_key, logs_key = run_result_object_keys(str(run.id))
            self.blob_store.put_file(result_key, result_path)
            self.blob_store.put_file(logs_key, log_path)

            for deliverable in validated.deliverables:
                deliverable_src = run_mount_dir / deliverable.path
                if not deliverable_src.exists() or not deliverable_src.is_file():
                    continue
                deliverable_key = f"runs/{run.id}/deliverables/{deliverable.path}"
                self.blob_store.put_file(deliverable_key, deliverable_src)

            if local_ctx is not None:
                self._capture_service_logs(local_ctx=local_ctx, run_id=str(run.id), service_log_dir=service_log_dir)

            if final_status == "flag_found":
                self._notify_discord_flag(run=run, challenge=challenge, result_data=result_data)

            result_row = db.get(RunResult, run.id)
            now = datetime.now(timezone.utc)
            if result_row is None:
                result_row = RunResult(
                    run_id=run.id,
                    status=final_status,
                    result_json_object_key=result_key,
                    logs_object_key=logs_key,
                    started_at=run.started_at,
                    finished_at=now,
                )
                db.add(result_row)
            else:
                result_row.status = final_status
                result_row.result_json_object_key = result_key
                result_row.logs_object_key = logs_key
                result_row.finished_at = now

            run.status = final_status
            run.finished_at = now
            if final_status in {"flag_found", "deliverable_produced"}:
                run.error_message = None
            db.commit()

        except Exception as exc:
            if run is not None:
                run.status = "blocked"
                run.error_message = str(exc)
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except (DockerException, NotFound):
                    pass
            if local_ctx is not None:
                self._stop_local_deploy(local_ctx=local_ctx, run_id=run_id)
            if run_dir is not None:
                self._cleanup_staged_auth(run_dir=run_dir)
            db.close()

    def terminate_run(self, run_id: str) -> dict[str, int]:
        killed = 0
        removed = 0

        target_label = f"ctf_harness.run_id={run_id}"
        containers = self.client.containers.list(all=True, filters={"label": target_label})
        if not containers:
            fallback_name = f"ctf-sandbox-{run_id[:8]}"
            containers = self.client.containers.list(all=True, filters={"name": fallback_name})

        for container in containers:
            try:
                container.kill()
                killed += 1
            except DockerException:
                pass
            try:
                container.remove(force=True)
                removed += 1
            except DockerException:
                pass

        compose_project = f"ctfrun{run_id.replace('-', '')[:10]}"
        chal_dir = self.settings.runs_dir / run_id / "chal"
        if chal_dir.exists():
            try:
                subprocess.run(
                    ["docker", "compose", "-p", compose_project, "down", "-v"],
                    cwd=chal_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except Exception:
                pass

        network_name = f"ctf_run_{run_id.replace('-', '')[:12]}"
        try:
            self.client.networks.get(network_name).remove()
        except DockerException:
            pass

        return {"killed": killed, "removed": removed}

    def _ensure_sandbox_image(self) -> None:
        try:
            self.client.images.get(self.settings.sandbox_image)
            return
        except ImageNotFound:
            pass

        build_context_candidates = [
            Path("/app/images/ctf-agent-sandbox"),
            Path("images/ctf-agent-sandbox"),
        ]
        for candidate in build_context_candidates:
            if candidate.exists():
                buildargs = {
                    "INSTALL_GHIDRA": "1" if self.settings.sandbox_build_install_ghidra else "0",
                    "GHIDRA_VERSION": str(self.settings.sandbox_build_ghidra_version),
                }
                self.client.images.build(path=str(candidate), tag=self.settings.sandbox_image, rm=True, buildargs=buildargs)
                return

        raise FileNotFoundError("Sandbox image not found and build context is unavailable")

    def _resolve_host_mount_path(self, configured_path: Path) -> Path:
        configured = configured_path.resolve()
        target = str(configured_path)
        if os.name == "nt":
            target = target.replace("\\", "/")

        try:
            container_id = socket.gethostname()
            me = self.client.containers.get(container_id)
            for mount in me.attrs.get("Mounts", []):
                destination = str(mount.get("Destination", ""))
                destination_normalized = destination.rstrip("/")
                target_normalized = target.rstrip("/")
                if target_normalized == destination_normalized or target_normalized.startswith(f"{destination_normalized}/"):
                    source = str(mount.get("Source", ""))
                    if not source:
                        continue
                    suffix = target_normalized[len(destination_normalized) :].lstrip("/")
                    return Path(source) / suffix if suffix else Path(source)
        except Exception:
            pass

        return configured

    def _sandbox_environment(self) -> dict[str, str]:
        env = {"PYTHONUNBUFFERED": "1", "HOME": "/home/ctf"}
        passthrough = [item.strip() for item in self.settings.sandbox_env_passthrough.split(",") if item.strip()]
        for name in passthrough:
            value = os.getenv(name)
            if value:
                env[name] = value

        env.setdefault("CODEX_HOME", "/home/ctf/.codex")
        env.setdefault("CODEX_AUTH_SEED_DIR", "/workspace/run/.auth_seed/codex")
        env.setdefault("SANDBOX_IDA_MCP_ENABLED", "true" if self.settings.sandbox_ida_mcp_enabled else "false")
        return env

    def _sandbox_auth_volumes(self, db: Session, run_dir: Path, host_run_dir: Path) -> dict[str, dict[str, str]]:
        staged_dir = run_dir / ".auth" / "codex"
        staged_dir.mkdir(parents=True, exist_ok=True)

        requested_tag = self.settings.sandbox_codex_auth_tag
        _, auth_material = get_codex_auth_material_for_tag(db, requested_tag=requested_tag)
        staged_from_store_count = self._stage_codex_auth_material(staged_dir=staged_dir, files=auth_material)
        if staged_from_store_count > 0:
            return {str(host_run_dir / ".auth" / "codex"): {"bind": "/workspace/run/.auth_seed/codex", "mode": "ro"}}
        return {}

    def _sandbox_ida_volumes(self) -> dict[str, dict[str, str]]:
        if not self.settings.sandbox_ida_mcp_enabled:
            return {}
        ida_path = self.settings.sandbox_ida_path
        if ida_path is None:
            return {}
        ida_path = ida_path.expanduser().resolve()
        if not ida_path.exists():
            return {}
        return {str(ida_path): {"bind": "/opt/ida", "mode": "ro"}}

    def _stage_codex_auth_material(self, staged_dir: Path, files: list[CodexAuthMaterial]) -> int:
        copied = 0
        for file_entry in files:
            safe_name = Path(file_entry.file_name.replace("\\", "/")).name
            if not safe_name:
                continue
            target = staged_dir / safe_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file_entry.content)
            copied += 1
        return copied

    def _cleanup_staged_auth(self, run_dir: Path) -> None:
        staged_root = run_dir / ".auth"
        if not staged_root.exists():
            return
        shutil.rmtree(staged_root, ignore_errors=True)

    def _resolve_flag_regex(self, challenge: ChallengeManifest) -> str | None:
        if challenge.flag_regex:
            return challenge.flag_regex
        if challenge.ctf and challenge.ctf.default_flag_regex:
            return challenge.ctf.default_flag_regex
        return None

    def _verify_flag_result(self, db: Session, challenge: ChallengeManifest, result_data: dict[str, Any]) -> dict[str, Any]:
        flag = result_data.get("flag")
        if not isinstance(flag, str) or not flag.strip():
            result_data["flag_verification"] = {
                "method": "none",
                "verified": False,
                "details": "Run reached flag_found without a concrete flag value.",
            }
            return result_data

        platform_error: str | None = None
        if challenge.platform == "ctfd":
            config = get_ctfd_config(db) or {}
            base_url = config.get("base_url")
            api_token = config.get("api_token")
            if base_url and api_token:
                client = CTFdClient(base_url=str(base_url), api_token=str(api_token))
                try:
                    attempt = client.submit_flag(challenge.platform_challenge_id, flag)
                    verdict = str(attempt.get("status") or attempt.get("message") or attempt.get("result") or "unknown")
                    verdict_lower = verdict.lower()
                    verified = any(token in verdict_lower for token in ("correct", "already", "solved"))
                    result_data["flag_verification"] = {
                        "method": "platform_submit",
                        "verified": verified,
                        "details": f"CTFd submission verdict: {verdict}",
                    }
                    return result_data
                except Exception as exc:
                    platform_error = str(exc)
                finally:
                    client.close()

        regex = self._resolve_flag_regex(challenge)
        if regex:
            try:
                matched = bool(re.search(regex, flag))
                details = f"Regex verification {'matched' if matched else 'did not match'} pattern: {regex}"
                if platform_error:
                    details += f"; platform submit unavailable: {platform_error}"
                result_data["flag_verification"] = {
                    "method": "regex_only",
                    "verified": matched,
                    "details": details,
                }
                return result_data
            except re.error as exc:
                platform_error = f"Invalid regex pattern: {exc}"

        result_data["flag_verification"] = {
            "method": "none",
            "verified": False,
            "details": platform_error or "No verification method configured.",
        }
        return result_data

    def _notify_discord_flag(self, run: Run, challenge: ChallengeManifest, result_data: dict[str, Any]) -> None:
        webhook_url = self.settings.discord_webhook_url
        if not self.settings.discord_notify_on_flag or not webhook_url:
            return

        verification = result_data.get("flag_verification") if isinstance(result_data.get("flag_verification"), dict) else {}
        flag_value = str(result_data.get("flag") or "")
        verified = bool(verification.get("verified", False))
        method = str(verification.get("method", "none"))
        details = str(verification.get("details", ""))

        color = 0x22C55E if verified else 0xF59E0B
        embed_fields = [
            {"name": "Challenge", "value": challenge.name[:1024] or "-", "inline": True},
            {"name": "Run ID", "value": str(run.id), "inline": True},
            {"name": "Backend", "value": run.backend[:1024] or "-", "inline": True},
            {"name": "Verification Method", "value": method[:1024] or "none", "inline": True},
            {"name": "Verified", "value": "true" if verified else "false", "inline": True},
            {"name": "Details", "value": (details or "No details provided.")[:1024], "inline": False},
        ]

        if self.settings.discord_notify_include_flag and flag_value:
            embed_fields.append({"name": "Flag Candidate", "value": f"`{flag_value[:1000]}`", "inline": False})

        payload = {
            "embeds": [
                {
                    "title": "Flag Candidate Ready for Submission",
                    "description": "A run finished with `flag_found` and produced a candidate flag.",
                    "color": color,
                    "fields": embed_fields,
                }
            ]
        }
        try:
            response = httpx.post(webhook_url, json=payload, timeout=10.0)
            response.raise_for_status()
        except Exception as exc:
            print(f"[orchestrator] discord webhook notification failed: {exc}", flush=True)

    def _hydrate_challenge_artifacts(self, challenge: ChallengeManifest, target_dir: Path) -> None:
        for artifact in challenge.artifacts:
            destination = target_dir / artifact["name"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.blob_store.download_file(artifact["object_key"], destination)

    def _build_spec_payload(self, run: Run, challenge: ChallengeManifest) -> dict[str, Any]:
        reasoning_effort = str(run.budgets.get("reasoning_effort") or "medium").lower()
        if reasoning_effort not in {"low", "medium", "high", "xhigh"}:
            reasoning_effort = "medium"

        mcp_servers: list[str] = []
        if os.getenv("CODEX_FLAG_VERIFY_MCP_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off", ""}:
            mcp_servers.append("flag_verify")
        if os.getenv("CODEX_CRYPTO_MCP_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off", ""}:
            mcp_servers.append("crypto_math")
        if os.getenv("CODEX_GHIDRA_MCP_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off", ""}:
            mcp_servers.append("ghidra")
        if self.settings.sandbox_ida_mcp_enabled:
            mcp_servers.append("ida")

        return {
            "run_id": str(run.id),
            "challenge_id": str(run.challenge_id),
            "challenge_name": challenge.name,
            "category": challenge.category,
            "points": challenge.points,
            "description_md": challenge.description_md,
            "backend": run.backend,
            "reasoning_effort": reasoning_effort,
            "budgets": run.budgets,
            "stop_criteria": run.stop_criteria,
            "allowed_endpoints": run.allowed_endpoints,
            "paths": run.paths,
            "local_deploy": run.local_deploy,
            "mcp": {"enabled": True, "servers": mcp_servers},
        }

    def _stream_logs(self, container, log_path: Path) -> None:
        with log_path.open("ab") as handle:
            for chunk in container.logs(stream=True, follow=True):
                handle.write(chunk)
                handle.flush()

    def _write_blocked_result(self, run_mount_dir: Path, challenge: ChallengeManifest, reason: str, status: str) -> None:
        fallback = {
            "challenge_id": str(challenge.id),
            "challenge_name": challenge.name,
            "status": status,
            "stop_criterion_met": "none",
            "flag_verification": {"method": "none", "verified": False, "details": reason},
            "deliverables": [],
            "repro_steps": [],
            "key_findings": [],
            "evidence": [],
            "notes": reason,
        }
        (run_mount_dir / "README.md").write_text("# Run Output\n\nNo successful output produced.\n", encoding="utf-8")
        (run_mount_dir / "result.json").write_text(json.dumps(fallback, indent=2), encoding="utf-8")

    def _load_validated_result(self, run_mount_dir: Path, challenge: ChallengeManifest) -> tuple[dict[str, Any], SandboxResult]:
        result_path = run_mount_dir / "result.json"

        try:
            result_data = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._write_blocked_result(
                run_mount_dir=run_mount_dir,
                challenge=challenge,
                reason=f"Invalid result.json content: {exc}",
                status="blocked",
            )
            result_data = json.loads(result_path.read_text(encoding="utf-8"))

        try:
            validated = SandboxResult.model_validate(result_data)
            return result_data, validated
        except Exception as exc:
            self._write_blocked_result(
                run_mount_dir=run_mount_dir,
                challenge=challenge,
                reason=f"Invalid result.json schema: {exc}",
                status="blocked",
            )
            result_data = json.loads(result_path.read_text(encoding="utf-8"))
            validated = SandboxResult.model_validate(result_data)
            return result_data, validated

    def _start_local_deploy(self, run_id: str, challenge_dir: Path) -> LocalDeployContext:
        compose_file = challenge_dir / "docker-compose.yml"
        if not compose_file.exists():
            compose_file = challenge_dir / "compose.yml"
        if not compose_file.exists():
            raise FileNotFoundError("Local deploy enabled but docker-compose.yml/compose.yml not found")

        network_name = f"ctf_run_{run_id.replace('-', '')[:12]}"
        compose_project = f"ctfrun{run_id.replace('-', '')[:10]}"

        self.client.networks.create(network_name, check_duplicate=True)

        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "-p", compose_project, "up", "-d"],
            cwd=challenge_dir,
            check=True,
            capture_output=True,
            text=True,
        )

        service_endpoints: list[dict] = []
        containers = self.client.containers.list(filters={"label": f"com.docker.compose.project={compose_project}"})
        network = self.client.networks.get(network_name)
        container_names: list[str] = []
        for service_container in containers:
            container_names.append(service_container.name)
            try:
                network.connect(service_container.id)
            except DockerException:
                pass
            ports = service_container.attrs.get("NetworkSettings", {}).get("Ports", {})
            for container_port in ports.keys():
                raw_port = int(str(container_port).split("/")[0])
                service_endpoints.append(
                    {
                        "type": "http",
                        "host": service_container.name,
                        "port": raw_port,
                        "url": f"http://{service_container.name}:{raw_port}",
                    }
                )

        return LocalDeployContext(
            network_name=network_name,
            compose_project=compose_project,
            service_endpoints=service_endpoints,
            container_names=container_names,
        )

    def _capture_service_logs(self, local_ctx: LocalDeployContext, run_id: str, service_log_dir: Path) -> None:
        for container_name in local_ctx.container_names:
            try:
                service_container = self.client.containers.get(container_name)
                log_blob = service_container.logs(stdout=True, stderr=True)
                log_path = service_log_dir / f"{container_name}.log"
                log_path.write_bytes(log_blob)
                self.blob_store.put_file(f"runs/{run_id}/service-logs/{container_name}.log", log_path)
            except DockerException:
                continue

    def _stop_local_deploy(self, local_ctx: LocalDeployContext, run_id: str) -> None:
        run_dir = self.settings.runs_dir / str(run_id)
        chal_dir = run_dir / "chal"

        try:
            subprocess.run(
                ["docker", "compose", "-p", local_ctx.compose_project, "down", "-v"],
                cwd=chal_dir,
                check=False,
                capture_output=True,
                text=True,
            )
        finally:
            try:
                self.client.networks.get(local_ctx.network_name).remove()
            except DockerException:
                pass
