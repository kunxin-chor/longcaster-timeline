"""Reconcile persisted jobs with ComfyUI, independently of browser events."""
from datetime import datetime, timezone


def reconcile(store, queue):
    jobs = store.load()["jobs"]
    for job in jobs.values():
        prompt_id = job.get("prompt_id")
        if not prompt_id or job["status"] not in ("queued", "running", "persisting", "cancel_requested", "succeeded", "failed"):
            continue
        if job["status"] == "failed" and job.get("error"):
            continue
        if job["status"] == "succeeded" and (job.get("progress") or {}).get("stage") not in ("decoding", "saving_media", "building_preview"):
            continue
        running, pending = queue.get_current_queue()
        if any(row[1] == prompt_id for row in running + pending):
            continue
        history = queue.get_history(prompt_id).get(prompt_id)
        if history:
            status = history.get("status") or {}
            messages = status.get("messages") or []
            interrupted = any(message[0] == "execution_interrupted" for message in messages)
            errors = [message[1].get("exception_message", "ComfyUI execution failed") for message in messages if message[0] == "execution_error"]
            if interrupted:
                store.execution_ended(job["id"], prompt_id, "cancelled", "Generation cancelled in ComfyUI.")
            elif errors or status.get("status_str") == "error":
                store.execution_ended(job["id"], prompt_id, "failed", errors[-1] if errors else "ComfyUI execution failed.")
            elif status.get("completed"):
                store.execution_ended(job["id"], prompt_id, "failed", "ComfyUI finished without completing this generation.")
        else:
            # Dispatch may still be binding its prompt ID. Do not infer cancellation
            # from a newly queued job or the queue/history handoff alone.
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(job["updated_at"])).total_seconds()
            if age < 10:
                continue
            running, pending = queue.get_current_queue()
            if any(row[1] == prompt_id for row in running + pending) or queue.get_history(prompt_id):
                continue
            store.execution_ended(job["id"], prompt_id, "cancelled", "ComfyUI prompt was removed from the queue or is no longer available.")
