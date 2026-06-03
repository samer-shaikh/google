from enum import Enum

class Plan(str, Enum):
    normal = "normal"
    pro = "pro"
    plus = "plus"