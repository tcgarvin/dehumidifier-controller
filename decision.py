from dataclasses import dataclass

@dataclass
class Decision:
    name: str
    criteria: str
    units: str
    threshold: int
    measurement: int
    decision: bool
