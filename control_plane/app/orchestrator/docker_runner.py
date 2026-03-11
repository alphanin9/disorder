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
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.app.core.config import get_settings
from control_plane.app.db.models import CTFIntegrationConfig, ChallengeManifest, Run, RunResult
from control_plane.app.db.session import SessionLocal
from control_plane.app.schemas.result_contract import SandboxResult
from control_plane.app.services.auth_service import CodexAuthMaterial, get_codex_auth_material_for_tag
from control_plane.app.services.auto_continuation_service import evaluate_and_queue_auto_continuation
from control_plane.app.services.flag_submission_service import build_flag_verification
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
            skills_mount_volume = self._sandbox_codex_skills_volumes()
            ida_mount_volume, ida_env = self._sandbox_ida_mount_and_env()
            continuation_mount_volume = self._sandbox_continuation_volume(run=run, host_run_dir=host_run_dir)

            volumes = {
                str(host_chal_dir): {"bind": "/workspace/chal", "mode": "ro"},
                str(host_run_mount): {"bind": "/workspace/run", "mode": "rw"},
            }
            volumes.update(auth_mount_volume)
            volumes.update(skills_mount_volume)
            volumes.update(ida_mount_volume)
            volumes.update(continuation_mount_volume)
            sandbox_env = self._sandbox_environment(db=db, challenge=challenge)
            sandbox_env.update(ida_env)

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
                environment=sandbox_env,
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
                    failure_reason_code="timeout",
                )
                final_status = "timeout"
                run.error_message = "Run timed out"
            else:
                final_status = "blocked" if status_code != 0 else "blocked"
                if status_code != 0:
                    run.error_message = f"Sandbox exited with status code {status_code}"

            result_path = run_mount_dir / "result.json"
            readme_path = run_mount_dir / "README.md"

            contract_missing_output = not result_path.exists() or not readme_path.exists()
            if contract_missing_output:
                self._write_blocked_result(
                    run_mount_dir=run_mount_dir,
                    challenge=challenge,
                    reason="Sandbox output contract missing result.json or README.md",
                    status="blocked",
                    failure_reason_code="sandbox_output_contract_missing",
                )

            result_data, validated, contract_valid, contract_failure_code, contract_failure_detail = self._load_validated_result(
                run_mount_dir=run_mount_dir,
                challenge=challenge,
            )
            if contract_missing_output:
                contract_valid = False
                contract_failure_code = "sandbox_output_contract_missing"
                contract_failure_detail = "Sandbox output contract missing result.json or README.md"
            result_status_before_stop_eval = str(result_data.get("status") or "blocked")

            if final_status != "timeout":
                stop_eval = evaluate_stop_criteria(run.stop_criteria, result_data, run_mount_dir)
                result_data["stop_criterion_met"] = stop_eval.stop_criterion_met
                result_data["status"] = stop_eval.final_status
                if stop_eval.final_status == "flag_found":
                    result_data = self._verify_flag_result(db=db, run=run, challenge=challenge, result_data=result_data)
                result_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
                validated = SandboxResult.model_validate(result_data)
                final_status = stop_eval.final_status
            finalization_metadata = self._build_finalization_metadata(
                result_data=result_data,
                status_code=status_code,
                timed_out=timed_out,
                contract_valid=contract_valid,
                contract_failure_code=contract_failure_code,
                contract_failure_detail=contract_failure_detail,
                result_status_before_stop_eval=result_status_before_stop_eval,
                result_status_after_stop_eval=final_status,
            )

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
                    finalization_metadata=finalization_metadata,
                    started_at=run.started_at,
                    finished_at=now,
                )
                db.add(result_row)
            else:
                result_row.status = final_status
                result_row.result_json_object_key = result_key
                result_row.logs_object_key = logs_key
                result_row.finalization_metadata = finalization_metadata
                result_row.finished_at = now

            run.status = final_status
            run.finished_at = now
            if final_status in {"flag_found", "deliverable_produced"}:
                run.error_message = None
            db.commit()
            db.refresh(run)
            db.refresh(result_row)

            auto_child = evaluate_and_queue_auto_continuation(
                db=db,
                run=run,
                result=result_row,
                settings=self.settings,
                blob_store=self.blob_store,
            )
            if auto_child is not None:
                self.launch_async(str(auto_child.id))

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

        target = (getattr(self.settings, "sandbox_build_target", None) or "").strip()
        build_kwargs: dict[str, Any] = {
            "tag": self.settings.sandbox_image,
            "rm": True,
        }
        if target:
            build_kwargs["target"] = target

        build_context_candidates = [
            Path("/app/images/ctf-agent-sandbox"),
            Path("images/ctf-agent-sandbox"),
        ]
        for candidate in build_context_candidates:
            if candidate.exists():
                self.client.images.build(path=str(candidate), **build_kwargs)
                return

        raise FileNotFoundError("Sandbox image not found and build context is unavailable")

    def _resolve_host_mount_path(self, configured_path: Path) -> Path:
        target_raw = str(configured_path)
        target = target_raw.replace("\\", "/") if os.name == "nt" else target_raw
        mounts: list[dict[str, Any]] = []

        try:
            container_id = socket.gethostname()
            me = self.client.containers.get(container_id)
            mounts = me.attrs.get("Mounts", [])
        except Exception:
            mounts = []

        # Docker Desktop on Windows + Linux control-plane container:
        # allow users to pass `G:\...` style host paths and translate them
        # into a Linux daemon-visible path (`/run/desktop/mnt/host/g/...`).
        if os.name != "nt":
            translated = self._translate_windows_host_path_for_daemon(target_raw=target_raw, mounts=mounts)
            if translated:
                target = translated
                print(
                    f"[orchestrator] translated Windows host path '{target_raw}' to '{target}' for Docker daemon",
                    flush=True,
                )

        configured = Path(target).resolve()

        try:
            for mount in mounts:
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

    def _translate_windows_host_path_for_daemon(self, target_raw: str, mounts: list[dict[str, Any]]) -> str | None:
        windows_path = re.match(r"^(?P<drive>[A-Za-z]):[\\/](?P<rest>.*)$", target_raw)
        if not windows_path:
            return None

        drive = windows_path.group("drive").lower()
        rest = windows_path.group("rest").replace("\\", "/").lstrip("/")

        prefix: str | None = None
        for mount in mounts:
            source = str(mount.get("Source", "")).replace("\\", "/")
            match = re.match(r"^(?P<prefix>/(?:run/desktop/mnt/host|host_mnt))/(?P<drive>[A-Za-z])(?:/|$)", source)
            if match and match.group("drive").lower() == drive:
                prefix = match.group("prefix")
                break

        if prefix is None:
            prefix = os.getenv("DOCKER_DESKTOP_HOST_MOUNT_PREFIX", "/run/desktop/mnt/host").strip()
            if not prefix:
                prefix = "/run/desktop/mnt/host"

        translated = f"{prefix}/{drive}"
        if rest:
            translated = f"{translated}/{rest}"
        return translated

    def _ctf_has_ctfd_integration(self, db: Session, ctf_id: UUID | None) -> bool:
        if ctf_id is None:
            return False
        stmt = (
            select(CTFIntegrationConfig.id)
            .where(
                CTFIntegrationConfig.ctf_id == ctf_id,
                CTFIntegrationConfig.provider == "ctfd",
            )
            .limit(1)
        )
        return db.execute(stmt).scalar_one_or_none() is not None

    def _sandbox_environment(
        self,
        *,
        db: Session | None = None,
        challenge: ChallengeManifest | None = None,
    ) -> dict[str, str]:
        env = {"PYTHONUNBUFFERED": "1", "HOME": "/home/ctf"}
        passthrough = [item.strip() for item in self.settings.sandbox_env_passthrough.split(",") if item.strip()]
        for name in passthrough:
            value = os.getenv(name)
            if value:
                env[name] = value

        env.setdefault("CODEX_HOME", "/home/ctf/.codex")
        env.setdefault("CODEX_AUTH_SEED_DIR", "/workspace/run/.auth_seed/codex")
        env.setdefault("CODEX_SKILLS_SEED_DIR", "/workspace/run/.skill_seed/codex/skills")
        control_plane_url = (self.settings.sandbox_control_plane_url or "").strip()
        if control_plane_url:
            env.setdefault("DISORDER_CONTROL_PLANE_URL", control_plane_url.rstrip("/"))
        else:
            env.setdefault("DISORDER_CONTROL_PLANE_URL", f"http://host.docker.internal:{self.settings.app_port}")
        flag_submit_mcp_enabled = bool(getattr(self.settings, "sandbox_flag_submit_mcp_enabled", False))
        if not flag_submit_mcp_enabled and db is not None and challenge is not None:
            try:
                flag_submit_mcp_enabled = self._ctf_has_ctfd_integration(db, challenge.ctf_id)
            except Exception as exc:
                print(
                    f"[orchestrator] unable to determine CTFd integration for challenge {challenge.id}; "
                    f"leaving flag submit MCP disabled: {exc}",
                    flush=True,
                )
        env.setdefault(
            "CODEX_FLAG_SUBMIT_MCP_ENABLED",
            "1" if flag_submit_mcp_enabled else "0",
        )
        return env

    def _sandbox_ida_mount_and_env(self) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
        host_path = (self.settings.sandbox_ida_host_path or "").strip()
        if not host_path:
            return {}, {"SANDBOX_IDA_ENABLED": "0"}

        mount_path = (self.settings.sandbox_ida_mount_path or "/opt/ida").strip() or "/opt/ida"
        port = self.settings.sandbox_idalib_mcp_port
        if port <= 0:
            port = 8745

        resolved = self._resolve_host_mount_path(Path(host_path))
        env = {
            "SANDBOX_IDA_ENABLED": "1",
            "SANDBOX_IDA_INSTALL_PATH": mount_path,
            "SANDBOX_IDALIB_MCP_PORT": str(port),
            "SANDBOX_IDA_ACCEPT_EULA": "1" if self.settings.sandbox_ida_accept_eula else "0",
            "SANDBOX_IDA_EULA_VERSIONS": self.settings.sandbox_ida_eula_versions,
            "IDADIR": mount_path,
            "IDA_PATH": mount_path,
            "IDA_DIR": mount_path,
        }
        volume: dict[str, dict[str, str]] = {str(resolved): {"bind": mount_path, "mode": "ro"}}

        registry_host_path = (self.settings.sandbox_ida_registry_host_path or "").strip()
        if registry_host_path:
            registry_resolved = self._resolve_host_mount_path(Path(registry_host_path))
            volume[str(registry_resolved)] = {"bind": "/home/ctf/.idapro", "mode": "rw"}

        return volume, env

    def _sandbox_auth_volumes(self, db: Session, run_dir: Path, host_run_dir: Path) -> dict[str, dict[str, str]]:
        staged_dir = run_dir / ".auth" / "codex"
        staged_dir.mkdir(parents=True, exist_ok=True)

        requested_tag = self.settings.sandbox_codex_auth_tag
        _, auth_material = get_codex_auth_material_for_tag(db, requested_tag=requested_tag)
        staged_from_store_count = self._stage_codex_auth_material(staged_dir=staged_dir, files=auth_material)
        if staged_from_store_count > 0:
            return {str(host_run_dir / ".auth" / "codex"): {"bind": "/workspace/run/.auth_seed/codex", "mode": "ro"}}
        return {}

    def _sandbox_codex_skills_volumes(self) -> dict[str, dict[str, str]]:
        host_path = (self.settings.sandbox_codex_skills_host_path or "").strip()
        if not host_path:
            return {}

        resolved = self._resolve_host_mount_path(Path(host_path))
        return {
            str(resolved): {
                "bind": "/workspace/run/.skill_seed/codex/skills",
                "mode": "ro",
            }
        }

    def _sandbox_continuation_volume(self, run: Run, host_run_dir: Path) -> dict[str, dict[str, str]]:
        mount_path = str((run.paths or {}).get("continuation_mount") or "").strip()
        if not mount_path:
            return {}

        local_path = self.settings.runs_dir / str(run.id) / "continuation"
        host_path = host_run_dir / "continuation"
        if not local_path.exists() or not local_path.is_dir():
            print(
                f"[orchestrator] continuation mount requested for run {run.id} but local context path is missing: {local_path}",
                flush=True,
            )
            return {}

        print(
            f"[orchestrator] mounting continuation context for run {run.id}: {host_path} -> {mount_path} (ro)",
            flush=True,
        )
        return {str(host_path): {"bind": mount_path, "mode": "ro"}}

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

    def _verify_flag_result(self, db: Session, run: Run, challenge: ChallengeManifest, result_data: dict[str, Any]) -> dict[str, Any]:
        flag = result_data.get("flag")
        if not isinstance(flag, str) or not flag.strip():
            result_data["flag_verification"] = {
                "method": "none",
                "verified": False,
                "details": "Run reached flag_found without a concrete flag value.",
            }
            return result_data

        regex = self._resolve_flag_regex(challenge)
        result_data["flag_verification"] = build_flag_verification(
            db,
            run_id=run.id,
            challenge=challenge,
            flag=flag,
            regex=regex,
        )
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
            "agent_invocation": run.agent_invocation or {},
            "allowed_endpoints": run.allowed_endpoints,
            "paths": run.paths,
            "local_deploy": run.local_deploy,
            "continuation": {
                "is_continuation": run.parent_run_id is not None,
                "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
                "depth": run.continuation_depth,
                "input": run.continuation_input,
                "type": run.continuation_type,
                "mount_path": (run.paths or {}).get("continuation_mount"),
                "parent_result_path": "/workspace/continuation/parent_result.json"
                if (run.paths or {}).get("continuation_mount")
                else None,
                "parent_readme_path": "/workspace/continuation/parent_readme.md"
                if (run.paths or {}).get("continuation_mount")
                else None,
                "request_path": "/workspace/continuation/continuation_request.json"
                if (run.paths or {}).get("continuation_mount")
                else None,
                "deliverables_mount_path": "/workspace/continuation/deliverables"
                if (run.paths or {}).get("continuation_mount")
                else None,
                "deliverables_manifest_path": "/workspace/continuation/deliverables_manifest.json"
                if (run.paths or {}).get("continuation_mount")
                else None,
            },
        }

    def _stream_logs(self, container, log_path: Path) -> None:
        with log_path.open("ab") as handle:
            for chunk in container.logs(stream=True, follow=True):
                handle.write(chunk)
                handle.flush()

    def _write_blocked_result(
        self,
        run_mount_dir: Path,
        challenge: ChallengeManifest,
        reason: str,
        status: str,
        *,
        failure_reason_code: str = "none",
    ) -> None:
        fallback = {
            "challenge_id": str(challenge.id),
            "challenge_name": challenge.name,
            "status": status,
            "stop_criterion_met": "none",
            "flag_verification": {"method": "none", "verified": False, "details": reason},
            "failure_reason_code": failure_reason_code,
            "failure_reason_detail": reason,
            "deliverables": [],
            "repro_steps": [],
            "key_findings": [],
            "evidence": [],
            "notes": reason,
        }
        (run_mount_dir / "README.md").write_text("# Run Output\n\nNo successful output produced.\n", encoding="utf-8")
        (run_mount_dir / "result.json").write_text(json.dumps(fallback, indent=2), encoding="utf-8")

    def _load_validated_result(
        self,
        run_mount_dir: Path,
        challenge: ChallengeManifest,
    ) -> tuple[dict[str, Any], SandboxResult, bool, str, str]:
        result_path = run_mount_dir / "result.json"
        contract_valid = True
        failure_reason_code = "none"
        failure_reason_detail = ""

        try:
            result_data = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception as exc:
            contract_valid = False
            failure_reason_code = "result_validation_failed"
            failure_reason_detail = f"Invalid result.json content: {exc}"
            self._write_blocked_result(
                run_mount_dir=run_mount_dir,
                challenge=challenge,
                reason=failure_reason_detail,
                status="blocked",
                failure_reason_code=failure_reason_code,
            )
            result_data = json.loads(result_path.read_text(encoding="utf-8"))

        try:
            validated = SandboxResult.model_validate(result_data)
            return result_data, validated, contract_valid, failure_reason_code, failure_reason_detail
        except Exception as exc:
            contract_valid = False
            failure_reason_code = "result_validation_failed"
            failure_reason_detail = f"Invalid result.json schema: {exc}"
            self._write_blocked_result(
                run_mount_dir=run_mount_dir,
                challenge=challenge,
                reason=failure_reason_detail,
                status="blocked",
                failure_reason_code=failure_reason_code,
            )
            result_data = json.loads(result_path.read_text(encoding="utf-8"))
            validated = SandboxResult.model_validate(result_data)
            return result_data, validated, contract_valid, failure_reason_code, failure_reason_detail

    def _build_finalization_metadata(
        self,
        *,
        result_data: dict[str, Any],
        status_code: int,
        timed_out: bool,
        contract_valid: bool,
        contract_failure_code: str,
        contract_failure_detail: str,
        result_status_before_stop_eval: str,
        result_status_after_stop_eval: str,
    ) -> dict[str, Any]:
        reason_code = "none"
        reason_detail = ""
        if timed_out:
            reason_code = "timeout"
            reason_detail = "Run timed out before completion"
        elif contract_failure_code != "none":
            reason_code = contract_failure_code
            reason_detail = contract_failure_detail
        elif isinstance(result_data.get("failure_reason_code"), str) and result_data.get("failure_reason_code"):
            reason_code = str(result_data.get("failure_reason_code"))
            reason_detail = str(result_data.get("failure_reason_detail") or result_data.get("notes") or "")
        elif status_code != 0:
            reason_code = "sandbox_exit_nonzero"
            reason_detail = f"Sandbox exited with status code {status_code}"
        elif result_status_after_stop_eval == "blocked":
            reason_code = "stop_criteria_not_met"
            reason_detail = str(result_data.get("notes") or "")

        return {
            "contract_valid": contract_valid,
            "sandbox_exit_code": status_code,
            "timed_out": timed_out,
            "result_status_before_stop_eval": result_status_before_stop_eval,
            "result_status_after_stop_eval": result_status_after_stop_eval,
            "failure_reason_code": reason_code,
            "failure_reason_detail": reason_detail,
        }

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
