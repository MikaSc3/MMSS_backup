
"""
occ_test.py
A simple test script to display a 3D box using pythonOCC
Requires occ-env
"""


from OCC.Display.SimpleGui import init_display
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
import threading, time

display, start_display, add_menu, add_function_to_menu = init_display()
shape = BRepPrimAPI_MakeBox(10., 20., 30.).Shape()
display.DisplayShape(shape, update=True)
start_display()
print("start_display returned")
