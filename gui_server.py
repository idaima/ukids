"""ukids 本地 Web GUI 后端。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import VideoAPI
from auth import TOKEN_FILE, load_token, login_with_sms, save_token, send_sms_code
from download import process_json_file
from gui_services.file_service import PROJECT_ROOT, safe_output_path, scan_json_files, scan_season_dirs, to_project_relative
from gui_services.metadata_service import collect_metadata
from gui_services.task_manager import TaskManager
from merge import check_ffmpeg, process_season_dir

WEB_DIR = PROJECT_ROOT / "web"
GUI_STORE_DIR = PROJECT_ROOT / "outputs" / ".gui"

task_manager = TaskManager(max_workers=3, store_path=GUI_STORE_DIR / "tasks.json")
app = FastAPI(title="小小优趣助手", version="0.1.0")


class SmsRequest(BaseModel):
    mobile: str = Field(min_length=5)


class LoginRequest(BaseModel):
    mobile: str = Field(min_length=5)
    verify_code: str = Field(min_length=1)


class TokenRequest(BaseModel):
    token: str = Field(min_length=1)


class MetadataTaskRequest(BaseModel):
    mode: Literal["all", "age"] = "all"
    lang: int = 2
    age_name: str | None = None
    animations: list[dict[str, Any]]


class DownloadTaskRequest(BaseModel):
    json_paths: list[str]


class DeleteFilesRequest(BaseModel):
    paths: list[str]


class MergeTaskRequest(BaseModel):
    season_dirs: list[str]
    embed_subtitle: bool = True


def require_token() -> str:
    token = load_token()
    if not token:
        raise HTTPException(status_code=401, detail="未登录或 token 不存在")
    return token


def normalize_event(event: dict[str, Any] | None) -> dict[str, Any]:
    return event or {}


def cleanup_sidecar_for_file(target: Path) -> list[str]:
    """删除 JSON 对应的同名下载目录。"""
    removed: list[str] = []
    sidecar_dir = target.with_suffix("")
    if sidecar_dir.exists() and sidecar_dir.is_dir():
        shutil.rmtree(sidecar_dir)
        removed.append(to_project_relative(sidecar_dir))
    return removed


def cleanup_task_artifacts(task: dict[str, Any]) -> list[str]:
    """根据任务 result 清理采集/下载/合并产生的 outputs 产物。"""
    removed: list[str] = []
    result = task.get("result") or {}
    candidates: list[str] = []
    candidates.extend(result.get("output_files") or [])
    candidates.extend(result.get("output_dirs") or [])
    for path in candidates:
        try:
            target = safe_output_path(path, must_exist=False)
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.is_file():
                    target.unlink()
                    removed.extend(cleanup_sidecar_for_file(target))
                removed.append(to_project_relative(target))
        except Exception:
            continue
    return removed


@app.get("/api/auth/status")
def auth_status():
    token = load_token()
    return {
        "has_token": bool(token),
        "token_preview": f"{token[:12]}...{token[-6:]}" if token and len(token) > 24 else (token or ""),
    }


@app.post("/api/auth/sms")
def auth_sms(req: SmsRequest):
    ok = send_sms_code(req.mobile)
    return {"success": ok, "message": "验证码已发送" if ok else "验证码发送失败"}


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    token = login_with_sms(req.mobile, req.verify_code)
    if not token:
        raise HTTPException(status_code=400, detail="登录失败，请检查验证码")
    save_token(token)
    return {"success": True, "has_token": True}


@app.post("/api/auth/token")
def auth_token(req: TokenRequest):
    save_token(req.token.strip())
    return {"success": True, "has_token": True}


@app.post("/api/auth/logout")
def auth_logout():
    token_path = PROJECT_ROOT / TOKEN_FILE
    if token_path.exists():
        token_path.unlink()
    return {"success": True, "has_token": False}


@app.get("/api/age-types")
def age_types():
    api = VideoAPI(require_token())
    return {"items": api.get_age_types()}


@app.get("/api/animations")
def animations(
    mode: Literal["all", "age"] = "all",
    lang: int = Query(default=2),
    age_type: int | None = Query(default=None),
):
    api = VideoAPI(require_token())
    if mode == "age":
        if age_type is None:
            raise HTTPException(status_code=400, detail="分龄模式缺少 age_type")
        items = api.get_age_animation_list(age_type, filter_lang=lang)
    else:
        items = api.get_animation_list(filter_lang=lang)
    return {"items": items}


@app.get("/api/files/json")
def json_files(source: Literal["all", "age", "both"] = "both"):
    return {"items": scan_json_files(source)}


@app.post("/api/files/delete")
def delete_files(req: DeleteFilesRequest):
    if not req.paths:
        raise HTTPException(status_code=400, detail="未选择要删除的文件")
    deleted = []
    failed = []
    for path in req.paths:
        try:
            target = safe_output_path(path)
            if not target.is_file():
                raise ValueError("只允许删除文件")
            target.unlink()
            deleted.append(to_project_relative(target))
            deleted.extend(cleanup_sidecar_for_file(target))
        except Exception as exc:  # noqa: BLE001
            failed.append({"path": path, "error": str(exc)})
    return {"success": len(failed) == 0, "deleted": deleted, "failed": failed}


@app.get("/api/files/seasons")
def season_dirs(source: Literal["all", "age", "both"] = "both"):
    return {"items": scan_season_dirs(source)}


@app.get("/api/system/ffmpeg")
def system_ffmpeg():
    return {"available": check_ffmpeg()}


@app.post("/api/tasks/metadata")
def create_metadata_task(req: MetadataTaskRequest):
    token = require_token()
    if not req.animations:
        raise HTTPException(status_code=400, detail="未选择动画")

    def runner(task_id, update, is_cancelled):
        return collect_metadata(
            token=token,
            animations=req.animations,
            mode=req.mode,
            age_name=req.age_name,
            progress_cb=update,
            cancel_cb=is_cancelled,
        )

    return {"task_id": task_manager.create_task("metadata", runner)}


@app.post("/api/tasks/download")
def create_download_task(req: DownloadTaskRequest):
    if not req.json_paths:
        raise HTTPException(status_code=400, detail="未选择 JSON 文件")
    json_paths = [safe_output_path(path) for path in req.json_paths]

    def runner(task_id, update, is_cancelled):
        total_files = len(json_paths)
        total_success = 0
        total_failed = 0
        total_size = 0
        update(total=total_files, done=0, progress=0.0, message="开始下载", log=f"共 {total_files} 个 JSON 文件")
        for index, json_path in enumerate(json_paths, 1):
            if is_cancelled():
                update(status="cancelled", message="下载已取消")
                break
            source_dir = json_path.parent
            update(
                current=json_path.name,
                message=f"下载 {index}/{total_files}: {json_path.name}",
                log=f"开始下载 JSON: {to_project_relative(json_path)}",
            )

            def on_event(event):
                event = normalize_event(event)
                message = event.get("message") or f"正在下载 {json_path.name}"
                current = event.get("episode") or event.get("json_name") or json_path.name
                update(current=current, message=message, log=message if event.get("stage") in {"json_start", "episode_done", "episode_failed"} else None)

            success, failed, size = process_json_file(
                str(json_path),
                str(source_dir),
                file_num=index,
                total_files=total_files,
                progress_cb=on_event,
                cancel_cb=is_cancelled,
            )
            total_success += success
            total_failed += failed
            total_size += size
            update(
                done=index,
                total=total_files,
                success=total_success,
                failed=total_failed,
                progress=round((index / total_files) * 100, 2),
                message=f"已完成文件 {index}/{total_files}",
            )
        return {"success": total_success, "failed": total_failed, "total_size": total_size}

    return {"task_id": task_manager.create_task("download", runner)}


@app.post("/api/tasks/merge")
def create_merge_task(req: MergeTaskRequest):
    if not req.season_dirs:
        raise HTTPException(status_code=400, detail="未选择季目录")
    if not check_ffmpeg():
        raise HTTPException(status_code=400, detail="ffmpeg 不可用，请先安装 ffmpeg")
    season_paths = [safe_output_path(path) for path in req.season_dirs]

    def runner(task_id, update, is_cancelled):
        total_dirs = len(season_paths)
        total_success = 0
        total_failed = 0
        update(total=total_dirs, done=0, progress=0.0, message="开始合并", log=f"共 {total_dirs} 个季目录")
        for index, season_path in enumerate(season_paths, 1):
            if is_cancelled():
                update(status="cancelled", message="合并已取消")
                break
            update(current=season_path.name, message=f"合并 {index}/{total_dirs}: {season_path.name}", log=f"开始合并: {to_project_relative(season_path)}")

            def on_event(event):
                event = normalize_event(event)
                message = event.get("message") or f"正在合并 {season_path.name}"
                current = event.get("episode") or event.get("season") or season_path.name
                update(current=current, message=message, log=message if event.get("stage") in {"merge_done", "merge_failed", "merge_skipped"} else None)

            success, failed = process_season_dir(
                str(season_path),
                embed_subtitle=req.embed_subtitle,
                progress_cb=on_event,
                cancel_cb=is_cancelled,
            )
            total_success += success
            total_failed += failed
            update(
                done=index,
                total=total_dirs,
                success=total_success,
                failed=total_failed,
                progress=round((index / total_dirs) * 100, 2),
                message=f"已完成目录 {index}/{total_dirs}",
            )
        return {"success": total_success, "failed": total_failed}

    return {"task_id": task_manager.create_task("merge", runner)}


@app.get("/api/tasks")
def list_tasks():
    return {"items": task_manager.list_tasks()}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    try:
        return task_manager.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc


@app.delete("/api/tasks")
def clear_tasks():
    for task in task_manager.list_tasks():
        cleanup_task_artifacts(task)
    task_manager.clear_tasks()
    return {"success": True}


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    try:
        task = task_manager.get_task(task_id)
        cleanup_task_artifacts(task)
        task_manager.delete_task(task_id)
        return {"success": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    try:
        task_manager.cancel_task(task_id)
        return {"success": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc


@app.post("/api/tasks/{task_id}/logs/clear")
def clear_task_logs(task_id: str):
    try:
        task_manager.clear_logs(task_id)
        return {"success": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc


@app.get("/")
def index():
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="web/index.html 不存在")
    return FileResponse(index_file)


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("gui_server:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), reload=False)
