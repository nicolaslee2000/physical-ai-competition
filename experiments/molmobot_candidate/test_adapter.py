"""Mocked contract tests: NumPy + stdlib only, no model/server/Positronic imports."""
import threading
import time
import unittest

import numpy as np

from .adapter import MolmoBotAdapter, JOINTS, GRIP, EXTERIOR, WRIST, TASK, ACTION, CLOSED_QPOS


def observation(tick=0, stacked=False, joint=0):
    images = [np.full((2, 3, 3), tick, dtype=np.uint8), np.full((2, 3, 3), 100 + tick, dtype=np.uint8)]
    if stacked:
        images = [np.stack([value]) for value in images]
    return {JOINTS: np.full(7, joint, np.float32), GRIP: .5, EXTERIOR: images[0], WRIST: images[1], TASK: 'pick'}


class Model:
    def __init__(self):
        self.calls=[]
    def get_action_chunk(self, **inputs):
        self.calls.append(inputs)
        chunk=np.zeros((16,8),np.float32)
        chunk[:,:7]=np.arange(1,8)
        chunk[:,7]=np.arange(16)*32
        return chunk


class AdapterTests(unittest.TestCase):
    def test_sixteen_predicted_eight_used_one_returned_and_exact_history(self):
        model=Model();adapter=MolmoBotAdapter(model,history_mode='server_rpc')
        for tick in range(17):
            output=adapter(observation(tick),session_id='A')
            self.assertEqual(len(output),1);self.assertEqual(output[0][ACTION].shape,(8,))
        self.assertEqual(len(model.calls),3)
        self.assertEqual([int(image[0,0,0]) for image in model.calls[0]['images']],[0,100])
        self.assertEqual([int(image[0,0,0]) for image in model.calls[1]['images']],[0,8,100,108])
        self.assertEqual([int(image[0,0,0]) for image in model.calls[2]['images']],[8,16,108,116])
        np.testing.assert_allclose(model.calls[0]['state'],[0]*7+[CLOSED_QPOS*.5])

    def test_client_stack_camera_major_initial_no_padding(self):
        model=Model();adapter=MolmoBotAdapter(model)
        adapter(observation(stacked=True),session_id='A')
        self.assertEqual(len(model.calls[0]['images']),2)
        adapter.end_session('A')
        obs=observation(8,stacked=True)
        obs[EXTERIOR]=np.stack([observation(0)[EXTERIOR],observation(8)[EXTERIOR]])
        obs[WRIST]=np.stack([observation(0)[WRIST],observation(8)[WRIST]])
        adapter(obs,session_id='B')
        self.assertEqual([int(image[0,0,0]) for image in model.calls[1]['images']],[0,8,100,108])

    def test_clamp_uses_current_joints_each_rpc_and_threshold_strict(self):
        model=Model();adapter=MolmoBotAdapter(model,history_mode='server_rpc')
        first=adapter(observation(),session_id='A')[0][ACTION]
        np.testing.assert_allclose(first[:7],np.arange(1,8)/35,atol=1e-7)
        second=adapter(observation(1,joint=1),session_id='A')[0][ACTION]
        np.testing.assert_allclose(second[:7],1+(np.arange(1,8)-1)/30,atol=1e-7)
        self.assertEqual(len(model.calls),1)
        for tick in range(2,6):
            output=adapter(observation(tick),session_id='A')[0][ACTION]
            if tick==4:self.assertEqual(output[-1],0) # exactly128 remains open.
        self.assertEqual(output[-1],1) # row5 is160, >128.

    def test_sessions_history_and_close_reopen_independent(self):
        model=Model();adapter=MolmoBotAdapter(model,history_mode='server_rpc')
        adapter(observation(3),session_id='A');adapter(observation(9),session_id='B')
        self.assertEqual([len(value['images']) for value in model.calls],[2,2])
        adapter.end_session('A');adapter(observation(7),session_id='A')
        self.assertEqual(int(model.calls[-1]['images'][0][0,0,0]),7)
        self.assertEqual(len(model.calls[-1]['images']),2)
        adapter.close();self.assertEqual(adapter._sessions,{})

    def test_invalid_inputs_or_output_cannot_reuse_partial_state(self):
        model=Model();adapter=MolmoBotAdapter(model,history_mode='server_rpc')
        bad=observation();bad[JOINTS][0]=np.nan
        with self.assertRaises(ValueError):adapter(bad,session_id='A')
        self.assertEqual(model.calls,[])
        model.get_action_chunk=lambda **kwargs:np.zeros((8,8))
        with self.assertRaises(ValueError):adapter(observation(),session_id='A')
        self.assertNotIn('A',adapter._sessions)

    def test_shared_model_serialized_across_sessions(self):
        class LockedModel(Model):
            active=0
            max_active=0
            def get_action_chunk(self,**kwargs):
                self.active+=1;self.max_active=max(self.max_active,self.active)
                time.sleep(.01)
                result=super().get_action_chunk(**kwargs);self.active-=1;return result
        model=LockedModel();adapter=MolmoBotAdapter(model,history_mode='server_rpc')
        threads=[threading.Thread(target=adapter, args=(observation(),),kwargs={'session_id':str(i)}) for i in range(4)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(model.max_active,1);self.assertEqual(len(model.calls),4)


if __name__=='__main__':unittest.main()
