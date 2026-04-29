from dataclasses import dataclass
from datetime import datetime


@dataclass
class TempReading:
    time: datetime
    temperature_c: float
