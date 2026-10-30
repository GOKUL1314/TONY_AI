"""
Asynchronous Video Job Manager for TONY AI (Stage 7).
Executes long-running video generation in background threads with status transitions,
concurrency limits, cancellation support, and transient failure retries.
"""
import time
import logging
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Callable, List
from video_generation.models import VideoJob, VideoGenerationRequest, VideoMetadata
from video_generation.base import VideoProvider
from video_generation.storage import VideoStorage
from video_generation.history import VideoHistoryManager
from video_generation.progress import ProgressTracker, ProgressUpdate
from video_generation.errors import (
    VideoCancelledError,
    VideoAuthenticationError,
    ProviderUnavailableError,
    LocalVideoUnavailableError,
    FreeQuotaUnavailableError,
    PaidProviderBlockedError,
    SafetyViolationError,
    UnsupportedVideoCapabilityError,
    VideoValidationError
)

logger = logging.getLogger("tony.video_generation.jobs")


class VideoJobManager:
    """Manages execution, status, and lifecycle of asynchronous video synthesis jobs."""

    def __init__(
        self,
        provider: VideoProvider,
        storage: VideoStorage,
        history: VideoHistoryManager,
        max_concurrent_jobs: int = 1,
        max_retries: int = 2
    ):
        self.provider = provider
        self.storage = storage
        self.history = history
        self.max_concurrent_jobs = max_concurrent_jobs
        self.max_retries = max_retries
        self._lock = threading.Lock()
        self._jobs: Dict[str, VideoJob] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_jobs, thread_name_prefix="TonyVideoWorker")

    def submit_job(
        self,
        request: VideoGenerationRequest,
        generation_id: Optional[str] = None,
        source_image_bytes: Optional[bytes] = None
    ) -> VideoJob:
        """
        Create and submit an asynchronous video generation job.

        :param request: VideoGenerationRequest containing parameters.
        :param generation_id: Optional custom generation ID.
        :param source_image_bytes: Optional raw image bytes for image-to-video.
        :return: Initialized VideoJob in QUEUED status.
        """
        if not generation_id:
            gen_id, _, _ = self.storage.generate_video_identifiers()
            generation_id = gen_id

        job = VideoJob(
            generation_id=generation_id,
            status="queued",
            progress=None,
            progress_message="Job queued for processing",
            created_at=datetime.now().isoformat(),
            request=request
        )

        with self._lock:
            self._jobs[generation_id] = job

        logger.info(f"Video job '{generation_id}' created and queued.")
        # Dispatch to background thread pool
        self._executor.submit(self._run_job, generation_id, source_image_bytes)
        return job

    def get_job(self, generation_id: str) -> Optional[VideoJob]:
        """Retrieve job status object by generation ID."""
        with self._lock:
            return self._jobs.get(generation_id)

    def list_jobs(self, limit: int = 50) -> List[VideoJob]:
        """List active and recently completed jobs."""
        with self._lock:
            jobs = list(self._jobs.values())
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]

    def cancel_job(self, generation_id: str) -> bool:
        """Cancel an in-flight or queued video job."""
        with self._lock:
            job = self._jobs.get(generation_id)
            if not job:
                return False

            if job.status in ("completed", "failed", "cancelled"):
                return False

            job.is_cancelled = True
            job.status = "cancelled"
            job.progress_message = "Generation cancelled by operator"
            job.completed_at = datetime.now().isoformat()

        # Notify provider
        try:
            self.provider.cancel(generation_id)
        except Exception as e:
            logger.warning(f"Error signalling provider cancellation for '{generation_id}': {e}")

        logger.info(f"Video job '{generation_id}' marked as CANCELLED.")
        return True

    def _run_job(self, generation_id: str, source_image_bytes: Optional[bytes] = None) -> None:
        """Internal worker execution loop with safe retry logic."""
        with self._lock:
            job = self._jobs.get(generation_id)
            if not job or job.is_cancelled:
                return
            job.status = "processing"
            job.started_at = datetime.now().isoformat()
            job.progress_message = "Synthesizing video..."

        def _on_progress(pct: Optional[int], msg: str):
            with self._lock:
                current_job = self._jobs.get(generation_id)
                if current_job and not current_job.is_cancelled:
                    current_job.progress = pct
                    current_job.progress_message = msg

        retries = 0
        last_error = None

        while retries <= self.max_retries:
            # Check for cancellation before executing
            with self._lock:
                current_job = self._jobs.get(generation_id)
                if not current_job or current_job.is_cancelled:
                    logger.info(f"Job '{generation_id}' aborting due to cancellation.")
                    return

            try:
                # Execute generation
                if source_image_bytes is not None:
                    video_bytes, meta = self.provider.generate_image_to_video(
                        request=job.request,
                        image_bytes=source_image_bytes,
                        progress_callback=_on_progress
                    )
                else:
                    video_bytes, meta = self.provider.generate_text_to_video(
                        request=job.request,
                        progress_callback=_on_progress
                    )

                # Check if job was cancelled while provider was executing
                with self._lock:
                    if job.is_cancelled:
                        logger.info(f"Discarding generated output for cancelled job '{generation_id}'.")
                        return

                # Save generated video to disk
                vid_id, vname, vpath, fsize, tname, tpath = self.storage.save_video_bytes(
                    video_bytes=video_bytes,
                    video_id=generation_id
                )

                # Build full metadata
                metadata = VideoMetadata(
                    video_id=generation_id,
                    filename=vname,
                    file_path=str(vpath),
                    url=f"/api/videos/{generation_id}/file",
                    thumbnail_url=f"/api/videos/{generation_id}/thumbnail" if tname else None,
                    thumbnail_path=str(tpath) if tpath else None,
                    prompt=job.request.prompt,
                    revised_prompt=meta.get("revised_prompt", job.request.prompt),
                    width=meta.get("width", job.request.width),
                    height=meta.get("height", job.request.height),
                    duration=meta.get("duration", job.request.duration),
                    fps=meta.get("fps", job.request.fps),
                    format="mp4",
                    parent_image_id=job.request.parent_image_id,
                    provider=self.provider.provider_name,
                    model=self.provider.model_name,
                    generation_time_ms=meta.get("generation_time_ms", 0),
                    file_size_bytes=fsize,
                    simulated=bool(meta.get("simulated", False)),
                    status="completed"
                )

                # Persist to history
                self.history.add_record(metadata)

                # Mark job as completed
                with self._lock:
                    job.status = "completed"
                    job.progress = 100
                    job.progress_message = "Video generation complete"
                    job.completed_at = datetime.now().isoformat()
                    job.video_metadata = metadata

                logger.info(f"Video job '{generation_id}' completed successfully ({fsize} bytes).")
                return

            except (ProviderUnavailableError, VideoAuthenticationError, LocalVideoUnavailableError,
                    FreeQuotaUnavailableError, PaidProviderBlockedError, SafetyViolationError,
                    UnsupportedVideoCapabilityError, VideoValidationError, VideoCancelledError) as fatal_err:
                # Fatal, auth/unconfigured, or cost/safety errors MUST NOT be retried
                logger.warning(f"Job '{generation_id}' halted with fatal error: {fatal_err}")
                last_error = fatal_err
                break

            except Exception as transient_err:
                # Check cancellation
                with self._lock:
                    if job.is_cancelled:
                        return

                retries += 1
                last_error = transient_err
                if retries <= self.max_retries:
                    logger.warning(f"Job '{generation_id}' attempt {retries} failed ({transient_err}). Retrying in 1s...")
                    with self._lock:
                        job.retries = retries
                        job.progress_message = f"Transient error, retrying attempt {retries}/{self.max_retries}..."
                    time.sleep(1.0)
                else:
                    logger.error(f"Job '{generation_id}' exceeded max retries: {transient_err}")
                    break

        # If loop finishes without returning, job failed
        with self._lock:
            if not job.is_cancelled:
                job.status = "failed"
                job.completed_at = datetime.now().isoformat()
                job.error = str(last_error) if last_error else "Generation failed"
                job.progress_message = f"Failed: {job.error}"
