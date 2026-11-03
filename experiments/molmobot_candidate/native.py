"""Build a client declaration using ONLY registered upstream Positronic components.

Not an executable model server. Inject an already-loaded official model into the
pure adapter, then pass it to the reviewed native server separately. No download.
"""
from .adapter import JOINTS, GRIP, EXTERIOR, WRIST, TASK


def deployment(*, fps=15.0, history_mode='client_stack'):
    from positronic import keys
    from positronic.offboard.spec import PolicyDeployment
    from positronic.policy import Sequential
    from positronic.policy.processors import ChunkedSchedule, TemporalStack
    from positronic.policy.codecs.observation import SelectObservationFields
    from positronic.policy.codecs.action import AbsoluteJointsAction
    fields = SelectObservationFields({name: name for name in (JOINTS, GRIP, EXTERIOR, WRIST, TASK)})
    action = AbsoluteJointsAction(keys.TARGET_JOINTS, keys.TARGET_GRIP, num_joints=7)
    schedule = ChunkedSchedule(fps, horizon_sec=1 / fps, replan_on_error=False)
    inner = Sequential(schedule, fields & action)
    if history_mode == 'client_stack':
        inner = Sequential(TemporalStack((EXTERIOR, WRIST), (-8 / fps, 0.0), pad_start=False), inner)
    elif history_mode != 'server_rpc':
        raise ValueError('Unknown history contract')
    # codec=None: action dictionaries pass over native wire; built-in action decoder runs on client.
    return PolicyDeployment(inner, codec=None, compress_images=False)
