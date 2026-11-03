"""Pure NumPy, model-injected MolmoBot contract. No checkpoint or server loading."""
from collections import deque
from dataclasses import dataclass, field
from threading import RLock

import numpy as np

JOINTS = 'robot_state.q'
GRIP = 'grip'
EXTERIOR = 'image.exterior'
WRIST = 'image.wrist'
TASK = 'task'
ACTION = 'action'
CLOSED_QPOS = 0.824033


@dataclass
class Session:
    task: str
    history: deque = field(default_factory=lambda: deque(maxlen=9))
    chunk: np.ndarray | None = None
    index: int = 0
    calls: int = 0


class MolmoBotAdapter:
    """One action per RPC, private episode state, one shared locked model.

    `model` exposes official get_action_chunk(images, task_description, state).
    client_stack mode requires native TemporalStack(...,pad_start=False) before
    the one-step ChunkedSchedule. server_rpc mode samples RPC history instead;
    its eight-request gap is faithful only if every control tick reaches us.
    """
    def __init__(self, model, *, history_mode='client_stack'):
        if history_mode not in ('client_stack', 'server_rpc'):
            raise ValueError('Unknown observation history contract')
        self.model = model
        self.history_mode = history_mode
        self._sessions = {}
        self._lock = RLock()

    @staticmethod
    def _image(value, stacked):
        image = np.asarray(value)
        expected = 4 if stacked else 3
        if image.dtype != np.uint8 or image.ndim != expected or image.shape[-1] != 3 or min(image.shape) <= 0:
            raise ValueError('Expected uint8 RGB image or temporal image stack')
        if stacked and image.shape[0] not in (1, 2):
            raise ValueError('Expected one initial frame or two temporal frames per camera')
        return image.copy()

    def __call__(self, obs, *, session_id):
        if not isinstance(session_id, str) or not session_id:
            raise ValueError('Explicit session ID required')
        joints = np.asarray(obs[JOINTS], dtype=np.float32)
        grip = np.asarray(obs[GRIP], dtype=np.float32)
        if joints.shape != (7,) or not np.isfinite(joints).all() or grip.size != 1 or not np.isfinite(grip).all():
            raise ValueError('Expected seven finite measured joints and one finite grip')
        if not isinstance(obs[TASK], str) or not obs[TASK]:
            raise ValueError('Task instruction required')
        stacked = self.history_mode == 'client_stack'
        frames = (self._image(obs[EXTERIOR], stacked), self._image(obs[WRIST], stacked))
        if stacked and frames[0].shape[0] != frames[1].shape[0]:
            raise ValueError('Both cameras must share the temporal frame count')
        with self._lock:
            state = self._sessions.setdefault(session_id, Session(obs[TASK]))
            if state.task != obs[TASK]:
                raise ValueError('Task changed inside an existing session; end/reset it first')
            if not stacked:
                state.history.append(frames)
            if state.chunk is None or state.index >= 8:
                if stacked:
                    # Camera-major, each camera chronological, exactly as official wrapper.
                    images = [frame for camera in frames for frame in camera]
                else:
                    selected = [state.history[-9], state.history[-1]] if len(state.history) == 9 else [state.history[-1]]
                    images = [item[camera] for camera in (0, 1) for item in selected]
                model_state = np.concatenate([joints, [CLOSED_QPOS * float(np.clip(grip.item(), 0, 1))]]).astype(np.float32)
                try:
                    chunk = np.asarray(self.model.get_action_chunk(images=images, task_description=state.task, state=model_state), dtype=np.float32)
                    if chunk.shape != (16, 8) or not np.isfinite(chunk).all():
                        raise ValueError('Official checkpoint must return finite (16,8) chunk')
                except BaseException:
                    self._sessions.pop(session_id, None)  # Never reuse half-mutated state after failure.
                    raise
                state.chunk, state.index = chunk.copy(), 0
                state.calls += 1
            row = state.chunk[state.index].copy()
            delta = row[:7] - joints
            scale = float(np.max(np.abs(delta) / 0.2))
            target = joints + delta / max(1.0, scale)
            closure = float(row[7] > 128)
            state.index += 1
            # Exactly ONE row per native schedule chunk; no nested action matrix.
            return [{ACTION: np.concatenate([target, [closure]]).astype(np.float32)}]

    def end_session(self, session_id):
        with self._lock:
            self._sessions.pop(session_id, None)

    def close(self):
        with self._lock:
            self._sessions.clear()

    def meta(self):
        return {'type': 'molmobot-source-candidate', 'history_mode': self.history_mode,
                'predicted_chunk': 16, 'executed_before_replan': 8, 'rpc_action_steps': 1,
                'status': 'unmeasured_mock_contract_only'}
