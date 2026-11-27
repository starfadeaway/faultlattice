"""FaultLattice 研发控制台 API；仅提供本地研发视图所需接口。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from console.server.authoring import (
    AdapterDraftRequest,
    AIAuthoringService,
    SaveAdapterDraftRequest,
    TaskAuthoringService,
    TaskDraftRequest,
    TextFileUploadRequest,
)
from console.server.experiments import AnalysisRequest, ExperimentService
from console.server.external_agents import ExternalAgentService
from console.server.service import ProjectService
from faultlattice.errors import ConfigurationError, FaultLatticeError

ROOT = Path(__file__).resolve().parents[2]

# 直接启动 uvicorn 与 run_all 使用同一份本机配置；热更新子进程也能读取 .env。
# 只加载到后端进程环境，公开 API 永远不返回密钥。
from run_all import load_env  # noqa: E402

load_env(ROOT / ".env")

service = ProjectService(ROOT)
experiment_service = ExperimentService(ROOT)
external_agent_service = ExternalAgentService(ROOT)
task_authoring_service = TaskAuthoringService(ROOT, external_agent_service)
ai_authoring_service = AIAuthoringService(ROOT, task_authoring_service)
app = FastAPI(title="FaultLattice Console", version="0.1.0")


class RunSuiteRequest(BaseModel):
    suite_id: str
    model_option_id: str | None = None


class AdviceRequest(BaseModel):
    advisor_option_id: str | None = None


class ExternalAgentRegisterRequest(BaseModel):
    agent_id: str
    name: str
    entrypoint: str
    class_name: str


class ExternalAgentRunRequest(BaseModel):
    task_path: str
    model_option_id: str | None = None


class CustomTaskSaveRequest(BaseModel):
    agent_id: str
    draft: dict


class StandardTaskPackRequest(BaseModel):
    agent_id: str


_check_lock = asyncio.Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "project": "FaultLattice"}


@app.get("/api/project")
async def project() -> dict:
    # 验收会启动真实子进程；锁避免重复刷新在同一后端叠加执行测试。
    async with _check_lock:
        try:
            return await asyncio.to_thread(service.project_snapshot)
        except (OSError, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/naming")
def naming() -> dict[str, str]:
    try:
        return service.naming()
    except OSError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/source")
def source(path: str = Query(min_length=1)) -> dict[str, str]:
    try:
        return service.source(path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/artifacts")
def artifacts() -> list[dict]:
    return service.artifacts()


@app.get("/api/artifacts/{run_id}/report", response_class=PlainTextResponse)
def artifact_report(run_id: str) -> str:
    try:
        _, content = service.artifact_report(run_id)
        return content
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/public-reports")
def public_reports() -> list[dict]:
    return service.public_reports()


@app.get("/api/public-reports/content", response_class=PlainTextResponse)
def public_report(path: str = Query(min_length=1)) -> str:
    try:
        _, content = service.public_report(path)
        return content
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/experiments/suites")
def experiment_suites() -> list[dict]:
    try:
        return experiment_service.suites()
    except FaultLatticeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/experiments/models")
def experiment_models() -> list[dict]:
    return experiment_service.model_options()


@app.get("/api/experiments/history")
def experiment_history() -> list[dict]:
    return experiment_service.history()


@app.post("/api/experiments/analysis")
def experiment_analysis(request: AnalysisRequest) -> dict:
    try:
        return experiment_service.generate_analysis(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/experiments/run")
def run_experiment_suite(request: RunSuiteRequest) -> dict:
    try:
        return experiment_service.start_suite(request.suite_id, request.model_option_id)
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/experiments/history/{batch_id}")
def experiment_detail(batch_id: str) -> dict:
    try:
        return experiment_service.get(batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/experiments/history/{batch_id}/tasks/{task_id}/advice")
def experiment_advice(batch_id: str, task_id: str, request: AdviceRequest | None = None) -> dict:
    try:
        return experiment_service.generate_advice(
            batch_id, task_id, request.advisor_option_id if request else None
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/experiments/history/{batch_id}/report", response_class=PlainTextResponse)
def experiment_report(batch_id: str) -> str:
    try:
        return experiment_service.report(batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# 外部宿主与实验服务分离：加载预检在接入层，执行与产物仍由实验层负责。
@app.get("/api/external-agents")
def external_agents() -> list[dict]:
    try:
        return external_agent_service.list()
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/external-agents/register")
def register_external_agent(request: ExternalAgentRegisterRequest) -> dict:
    try:
        return external_agent_service.register(
            agent_id=request.agent_id,
            name=request.name,
            entrypoint=request.entrypoint,
            class_name=request.class_name,
        )
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/external-agents/{agent_id}/preflight")
def preflight_external_agent(agent_id: str) -> dict:
    try:
        registration = next((item for item in external_agent_service.list() if item["id"] == agent_id), None)
        if registration is None:
            raise HTTPException(status_code=404, detail=f"未知外部 Agent: {agent_id}")
        if registration["status"] != "ready":
            raise ConfigurationError(registration["error"] or "外部适配器预检失败")
        return registration
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/external-agents/{agent_id}/run")
def run_external_agent(agent_id: str, request: ExternalAgentRunRequest) -> dict:
    try:
        host, task, public = external_agent_service.binding(agent_id, request.task_path)
        return experiment_service.start_external_task(
            host=host,
            task=task,
            task_path=request.task_path,
            public=public,
            model_option_id=request.model_option_id,
        )
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# 任务与适配器草案：AI 不自动登记或运行，保存与执行始终是独立用户操作。
@app.get("/api/task-authoring")
def custom_tasks() -> list[dict]:
    return task_authoring_service.list_custom()


@app.post("/api/task-authoring")
def create_custom_task(request: CustomTaskSaveRequest) -> dict:
    try:
        return task_authoring_service.create(request.agent_id, request.draft)
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/task-authoring/{task_id}")
def delete_custom_task(task_id: str) -> dict[str, bool]:
    try:
        task_authoring_service.delete(task_id)
        return {"deleted": True}
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/task-authoring/pack")
def create_standard_task_pack(request: StandardTaskPackRequest) -> dict:
    try:
        return task_authoring_service.standard_pack(request.agent_id)
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/task-authoring/import")
def import_task_file(request: TextFileUploadRequest) -> dict:
    try:
        return task_authoring_service.import_draft(request)
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/task-authoring/ai-draft")
def generate_task_draft(request: TaskDraftRequest) -> dict:
    try:
        return ai_authoring_service.task_draft(request)
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/adapter-authoring/upload")
def upload_adapter_source(request: TextFileUploadRequest) -> dict:
    try:
        return ai_authoring_service.upload_source(request)
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/adapter-authoring/draft")
def generate_adapter_draft(request: AdapterDraftRequest) -> dict:
    try:
        return ai_authoring_service.adapter_draft(request)
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/adapter-authoring/save")
def save_adapter_draft(request: SaveAdapterDraftRequest) -> dict:
    try:
        return ai_authoring_service.save_adapter(request)
    except FaultLatticeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
