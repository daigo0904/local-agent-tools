import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mathx import mul
assert mul(3, 4) == 12
assert mul(0, 5) == 0
print('test_mul ok')
