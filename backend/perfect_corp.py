"""
Perfect Corp skin analysis API client — v2.1
...
"""

import time
import httpx
from dataclasses import dataclass

BASE_URL = "https://yce-api-01.makeupar.com"

POLL_INTERVAL_SECONDS = 2
DEFAULT_TIMEOUT_SECONDS = 60
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # Perfect Corp hard limit — 10MB

HD_ACTIONS = [
    "hd_wrinkle", "hd_pore", "hd_texture", "hd_acne", "hd_oiliness",
    "hd_radiance", "hd_eye_bag", "hd_age_spot", "hd_dark_circle",
    "hd_droopy_upper_eyelid", "hd_droopy_lower_eyelid", "hd_firmness",
    "hd_moisture", "hd_redness", "hd_skin_type",
]

CONCERN_NAME_MAP = {
    "hd_wrinkle": "wrinkle", "hd_pore": "pore", "hd_texture": "texture",
    "hd_acne": "acne", "hd_oiliness": "oiliness", "hd_radiance": "radiance",
    "hd_eye_bag": "eye_bag", "hd_age_spot": "age_spot",
    "hd_dark_circle": "dark_circle", "hd_droopy_upper_eyelid": "droopy_upper_eyelid",
    "hd_droopy_lower_eyelid": "droopy_lower_eyelid", "hd_firmness": "firmness",
    "hd_moisture": "moisture", "hd_redness": "redness",
}

class PerfectCorpError(Exception): pass
class AnalysisTimeoutError(PerfectCorpError): pass
class NoFaceDetectedError(PerfectCorpError): pass
class AnalysisFailedError(PerfectCorpError): pass
class ImageTooLargeError(PerfectCorpError): pass

@dataclass
class SkinConcern:
    name: str
    score: float

@dataclass
class SkinAnalysisResult:
    skin_type: str
    skin_score: float
    concerns: list[SkinConcern]

def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

def _register_file(image_bytes: bytes, api_key: str) -> tuple[str, str, dict]:
    url = f"{BASE_URL}/s2s/v2.1/file/skin-analysis"
    payload = {"files": [{"content_type": "image/jpg", "file_name": "selfie.jpg", "file_size": len(image_bytes)}]}
    with httpx.Client() as client:
        response = client.post(url, headers=_headers(api_key), json=payload, timeout=30.0)
    if response.status_code != 200:
        raise PerfectCorpError(f"File registration failed: {response.status_code} — {response.text}")
    data = response.json()
    file_entry = data["data"]["files"][0]
    upload_request = file_entry["requests"][0]
    return file_entry["file_id"], upload_request["url"], upload_request.get("headers", {})

def _upload_to_s3(image_bytes: bytes, upload_url: str, upload_headers: dict) -> None:
    with httpx.Client() as client:
        response = client.put(upload_url, content=image_bytes, headers=upload_headers, timeout=60.0)
    if response.status_code not in (200, 204):
        raise PerfectCorpError(f"S3 upload failed: {response.status_code} — {response.text}")

def upload_image(image_bytes: bytes, api_key: str) -> str:
    file_id, upload_url, upload_headers = _register_file(image_bytes, api_key)
    _upload_to_s3(image_bytes, upload_url, upload_headers)
    return file_id

def run_analysis(file_id: str, api_key: str) -> str:
    url = f"{BASE_URL}/s2s/v2.1/task/skin-analysis"
    payload = {"src_file_id": file_id, "dst_actions": HD_ACTIONS, "format": "json"}
    with httpx.Client() as client:
        response = client.post(url, headers=_headers(api_key), json=payload, timeout=30.0)
    if response.status_code != 200:
        raise PerfectCorpError(f"Task creation failed: {response.status_code} — {response.text}")
    return response.json()["data"]["task_id"]

def poll_until_complete(task_id: str, api_key: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    url = f"{BASE_URL}/s2s/v2.1/task/skin-analysis/{task_id}"
    deadline = time.time() + timeout
    get_headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client() as client:
        while time.time() < deadline:
            response = client.get(url, headers=get_headers, timeout=15.0)
            if response.status_code != 200:
                raise PerfectCorpError(f"Poll failed: {response.status_code} — {response.text}")
            data = response.json()
            task_status = data.get("data", {}).get("task_status")
            if task_status == "success":
                return data
            if task_status and task_status not in ("processing", "pending", "queued", "running"):
                error_code = data.get("data", {}).get("error", "")
                if error_code == "error_src_face_too_small":
                    raise NoFaceDetectedError("Face too small — use a closer photo with your face filling most of the frame.")
                if error_code == "error_below_min_image_size":
                    raise NoFaceDetectedError("Image resolution too low — use a higher quality photo of at least 640x480 pixels.")
                if error_code == "NO_FACE_DETECTED":
                    raise NoFaceDetectedError("No face detected — try a well-lit, front-facing photo.")
                if error_code == "exceed_max_filesize":
                    raise ImageTooLargeError("Image file is too large — please use a photo under 10MB.")
                raise AnalysisFailedError(f"Task failed: {data}")
            time.sleep(POLL_INTERVAL_SECONDS)
    raise AnalysisTimeoutError(f"Analysis did not complete within {timeout}s")

def parse_result(raw: dict) -> SkinAnalysisResult:
    output = raw.get("data", {}).get("results", {}).get("output", [])
    overall_score = 0.0
    for item in output:
        if item.get("type") == "all" and "score" in item:
            overall_score = float(item["score"]) / 100.0
            break
    skin_type = "unknown"
    for item in output:
        if item.get("type") == "hd_skin_type":
            skin_type = item.get("skin_type") or item.get("value") or "unknown"
            break
    concern_scores: dict[str, float] = {}
    for item in output:
        item_type = item.get("type", "")
        if item_type not in CONCERN_NAME_MAP:
            continue
        concern_name = CONCERN_NAME_MAP[item_type]
        raw_score = item.get("raw_score")
        if raw_score is None:
            continue
        region = item.get("region", "")
        if region == "whole" or concern_name not in concern_scores:
            concern_scores[concern_name] = float(raw_score) / 100.0
    concerns = [SkinConcern(name=name, score=score) for name, score in concern_scores.items()]
    concerns.sort(key=lambda c: c.score, reverse=True)
    return SkinAnalysisResult(skin_type=skin_type, skin_score=overall_score, concerns=concerns)

def analyse(image_bytes: bytes, api_key: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> SkinAnalysisResult:
    if len(image_bytes) > MAX_FILE_SIZE_BYTES:
        raise ImageTooLargeError(
            f"Image is {len(image_bytes)} bytes — exceeds the {MAX_FILE_SIZE_BYTES} byte (10MB) limit."
        )
    file_id = upload_image(image_bytes, api_key)
    task_id = run_analysis(file_id, api_key)
    raw = poll_until_complete(task_id, api_key, timeout=timeout)
    return parse_result(raw)
