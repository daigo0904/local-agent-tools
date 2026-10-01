import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mathx import div
assert div(3, 2) == 1.5
assert div(9, 3) == 3
print('test_div ok')
