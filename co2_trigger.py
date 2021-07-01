from collections import deque
import json
import requests
from pathlib import Path
from rich.console import Console
from statistics import stdev, mean
from time import monotonic

from decision import Decision


UPDATE_INTERVAL = 30 * 60  # 30 minutes
DEQUE_SIZE = 24 * 7 * 2    # 2 readings an hour for a week.  One week of data


class CO2Trigger:
    def __init__(self, region:str, api_key:str, data_location:Path, console:Console):
        self._key = api_key
        self.data_location = data_location
        self.next_update = monotonic()
        self.data = deque([], DEQUE_SIZE)
        self.region = region
        self.console = console


    def load_data(self):
        with open(self.data_location) as in_file:
            self.data = deque(json.load(in_file), DEQUE_SIZE)


    def update_data(self):
        if monotonic() < self.next_update:
            return

        api_response = requests.get(
            f"https://api.co2signal.com/v1/latest?countryCode={self.region}",
            headers={"auth-token": self._key})

        #self.console.print(api_response.json())

        co2eq = api_response.json()["data"]["carbonIntensity"]

        self.next_update = monotonic() + UPDATE_INTERVAL
        self.data.append(co2eq)
        with open(self.data_location, "w") as out_file:
            json.dump(list(self.data), out_file)

    def decide(self) -> Decision:
        if len(self.data) < 2:
            self.console.log(f":heavy_check_mark: Still initializing CO2 thresholds")
            return False

        last_co2 = int(self.data[-1])
        threshold = int(mean(self.data) + stdev(self.data))
        is_high = last_co2 >= threshold
        check = ":heavy_multiplication_x:" if is_high else ":heavy_check_mark:"
        self.console.log(f"{check} Current CO2eq/kWh ({last_co2:.1f}) should be less than threshold {threshold:.1f}")

        return Decision(
            name="Carbon Cost",
            criteria="Local carbon cost should be less than x̅ + σ",
            units="CO2eq/kWh",
            threshold=int(threshold),
            measurement=int(last_co2),
            decision=(not is_high)
        )
