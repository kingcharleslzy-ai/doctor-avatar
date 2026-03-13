import asyncio
import io
import json
import os
import queue
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import soundfile as sf
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

DITTO_DIR = Path("/home/charles/ditto-talkinghead")
if str(DITTO_DIR) not in sys.path:
    sys.path.insert(0, str(DITTO_DIR))

from stream_pipeline_online import StreamSDK  # noqa: E402


DATA_ROOT = DITTO_DIR / "checkpoints" / "ditto_trt_Ampere_Plus"
CFG_PKL = DITTO_DIR / "checkpoints" / "ditto_cfg" / "v0.4_hubert_cfg_trt_online.pkl"
SOURCE_IMAGE = DITTO_DIR / "doctor_photo_new.png"
JPEG_QUALITY = 85
CHUNK_SIZE = (3, 5, 2)
DEFAULT_SAMPLE_RATE = 16000
MAX_SESSION_FRAMES = 10000

app = FastAPI()
session_guard = asyncio.Lock()


class FrameStreamSDK(StreamSDK):
    def __init__(self, cfg_pkl, data_root, **kwargs):
        self.output_frame_queue = queue.Queue(maxsize=256)
        super().__init__(cfg_pkl, data_root, **kwargs)

    def _writer_worker(self):
        while not self.stop_event.is_set():
            try:
                item = self.writer_queue.get(timeout=1)
            except queue.Empty:
                continue

            if item is None:
                self.output_frame_queue.put(None)
                break

            self.output_frame_queue.put(item)
            self.writer_pbar.update()


class StreamSession:
    def __init__(self):
        self.sdk = FrameStreamSDK(str(CFG_PKL), str(DATA_ROOT))
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.format = "pcm_s16le"
        self.started = False
        self.closed = False
        tmp_path = Path(tempfile.gettempdir()) / f"ditto-stream-{os.getpid()}.mp4"
        self.sdk.setup(str(SOURCE_IMAGE), str(tmp_path), online_mode=True)
        self.sdk.setup_Nd(MAX_SESSION_FRAMES)

    def decode_audio_chunk(self, chunk: bytes) -> np.ndarray:
        if chunk[:4] == b"RIFF":
            audio, sr = sf.read(io.BytesIO(chunk), dtype="float32", always_2d=False)
            if isinstance(audio, tuple):
                audio = audio[0]
            if getattr(audio, "ndim", 1) > 1:
                audio = np.mean(audio, axis=1)
            if sr != DEFAULT_SAMPLE_RATE:
                import librosa

                audio = librosa.resample(audio, orig_sr=sr, target_sr=DEFAULT_SAMPLE_RATE)
            return np.asarray(audio, dtype=np.float32)

        audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        return audio

    def push_audio(self, chunk: bytes) -> None:
        audio = self.decode_audio_chunk(chunk)
        if audio.size == 0:
            return
        self.started = True
        self.sdk.run_chunk(audio, chunksize=CHUNK_SIZE)

    def drain_frames(self) -> list[bytes]:
        frames = []
        while True:
            try:
                frame = self.sdk.output_frame_queue.get_nowait()
            except queue.Empty:
                break

            if frame is None:
                break

            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if ok:
                frames.append(encoded.tobytes())
        return frames

    def finish(self) -> list[bytes]:
        if self.closed:
            return []
        self.closed = True
        if self.started:
            self.sdk.close()
        return self.drain_frames()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": "ditto-trt-online",
        "source": str(SOURCE_IMAGE),
        "cfg": str(CFG_PKL.name),
    }


@app.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()

    if session_guard.locked():
        await websocket.send_text('{"error":"busy","detail":"GPU 正在处理另一条流式视频会话。"}')
        await websocket.close(code=1013)
        return

    async with session_guard:
        session = StreamSession()
        try:
            while True:
                packet = await websocket.receive()
                if "text" in packet and packet["text"] is not None:
                    text = packet["text"].strip()
                    if text == "END":
                        for frame in session.finish():
                            if websocket.application_state == WebSocketState.CONNECTED:
                                await websocket.send_bytes(frame)
                        await websocket.send_text('{"done":true}')
                        break
                if "bytes" in packet and packet["bytes"] is not None:
                    if packet["bytes"] == b"END":
                        for frame in session.finish():
                            if websocket.application_state == WebSocketState.CONNECTED:
                                await websocket.send_bytes(frame)
                        await websocket.send_text('{"done":true}')
                        break
                    await asyncio.to_thread(session.push_audio, packet["bytes"])
                    frames = await asyncio.to_thread(session.drain_frames)
                    for frame in frames:
                        await websocket.send_bytes(frame)
        except WebSocketDisconnect:
            session.finish()
        except Exception as exc:  # pragma: no cover
            try:
                await websocket.send_text(json.dumps({"error": "runtime", "detail": str(exc)}, ensure_ascii=False))
            finally:
                session.finish()
                await websocket.close(code=1011)
        finally:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")
