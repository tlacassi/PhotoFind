"""Host tests for scale conversion and duplicate face suppression."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
import numpy as np
import support
import app


def face(x,y,width,height,score=.95):
    return np.array([x,y,width,height,x+width*.3,y+height*.35,x+width*.7,y+height*.35,x+width*.5,y+height*.5,x+width*.35,y+height*.7,x+width*.65,y+height*.7,score],dtype=np.float32)


class Detector:
    def __init__(self, detections): self.detections=detections;self.visited=[]
    def setInputSize(self,size): self.size=size;self.visited.append(size)
    def detect(self,image):
        value=self.detections.get(self.size)
        return 0,None if value is None else np.array(value)


class FaceDetectionTests(unittest.TestCase):
    def test_large_face_uses_reduced_scale_and_native_landmarks(self):
        detector=Detector({(640,640):[face(80,120,180,180)],(320,320):[face(40,60,90,90)]})
        faces=app.detect_faces(np.zeros((1600,1600,3),dtype=np.uint8),detector)
        self.assertEqual(len(faces),1)
        np.testing.assert_allclose(faces[0][:4],[200,300,450,450])
        np.testing.assert_allclose(faces[0][4:14],face(80,120,180,180)[4:14]*2.5)
        self.assertEqual(detector.visited,[(1600,1600),(640,640),(320,320)])

    def test_native_faces_remain_unchanged_and_distinct_people_are_preserved(self):
        native=face(100,100,120,120,.91)
        detector=Detector({(1000,500):[native],(640,320):[face(64,64,76.8,76.8,.99),face(400,64,76.8,76.8)]})
        faces=app.detect_faces(np.zeros((500,1000,3),dtype=np.uint8),detector)
        self.assertEqual(len(faces),2)
        np.testing.assert_array_equal(faces[0],native)
        np.testing.assert_allclose(faces[1][:4],[625,100,120,120],rtol=1e-6)

    def test_no_face_and_small_image_do_not_require_unbounded_attempts(self):
        detector=Detector({})
        self.assertEqual(app.detect_faces(np.zeros((240,300,3),dtype=np.uint8),detector),[])
        self.assertEqual(detector.visited,[(300,240)])
