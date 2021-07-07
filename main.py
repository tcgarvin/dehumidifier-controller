from enum import Enum
from os import getenv
from pathlib import Path
import requests
import socket
from time import sleep

from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.table import Table
from sense_energy import Senseable
from sense_energy.sense_exceptions import SenseAPITimeoutException

from co2_trigger import CO2Trigger
from decision import Decision


DEVICE_DRAW_THRESHOLD = 50 # Watts


class DeviceState(Enum):
    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


class Controller:
    def __init__(self, co2_trigger:CO2Trigger, sense_client: Senseable, webhook_key:str, sense_device: str, live: Live):
        self.sense_client = sense_client
        self.live = live
        self.sense_device = sense_device
        self.device_state = DeviceState.UNKNOWN
        self.webhook_key = webhook_key
        self.co2_trigger = co2_trigger

    def run(self):
        while(True):
            #with self.live.console.status("Fetching CO2 data"):
            self.co2_trigger.update_data()

            decisions = [self.co2_trigger.decide(), self.decide_device()]
            dehumidifier_should_be_on = decisions[0].decision and decisions[1].decision
            self.update_device(dehumidifier_should_be_on)

            sleep_duration = 120
            co2_is_high = not decisions[0].decision
            if co2_is_high:
                sleep_duration = 1800
                self.live.console.log("CO2 is high. Will pause and check back in 30 minutes")

            live.update(self.generate_table(decisions), refresh=True)
            sleep(sleep_duration)

    
    def decide_device(self) -> Decision:
        decision = Decision(
            name=self.sense_device,
            criteria="Projector should be off",
            units="W",
            threshold=50,
            measurement=0,
            decision=True
        )

        #with self.live.console.status("Fetching Sense data"):
        try:
            self.sense_client.update_realtime()
            realtime_data = self.sense_client.get_realtime()
        except (SenseAPITimeoutException, socket.timeout) as e:
            self.live.console.log(f"Transient Exception connecting to Sense API.  Reading as {self.sense_device} off for now: {e}")
            return decision


        for device in realtime_data["devices"]:
            device_name = device["name"]
            if device_name != self.sense_device:
                continue

            device_draw = device["w"]
            device_is_on = device_draw > DEVICE_DRAW_THRESHOLD
            check = ":heavy_multiplication_x:" if device_is_on else ":heavy_check_mark:"
            self.live.console.log(f"{check} {device_name} ({device_draw:.1f} Watts) should be less than {DEVICE_DRAW_THRESHOLD} Watts")
            decision.measurement = device_draw
            decision.decision = not device_is_on
            return decision

        self.live.console.log(f":heavy_check_mark: {device_name} missing, inferred (0W) < {DEVICE_DRAW_THRESHOLD}W")
        return decision


    def generate_table(self, decisions) -> Table:
        result = Table(
            "Item",
            "Criteria",
            "Threshold",
            "Current Value",
            "Go / No Go"
        )
        for decision in decisions:
            result.add_row(
                decision.name, 
                decision.criteria, 
                f"{decision.threshold} {decision.units}",
                f"{decision.measurement} {decision.units}",
                ":heavy_check_mark:" if decision.decision else ":heavy_multiplication_x:"
            )

        return result


    def update_device(self, on:bool):
        event = "dehumidifier_on" if on else "dehumidifier_off"
        next_state = DeviceState.ON if on else DeviceState.OFF
        webhook_url = f"https://maker.ifttt.com/trigger/{event}/with/key/{self.webhook_key}"

        fire_update = False
        if self.device_state == DeviceState.ON and not on:
            fire_update = True

        elif self.device_state == DeviceState.OFF and on:
            fire_update = True

        elif self.device_state == DeviceState.UNKNOWN:
            fire_update = True

        if fire_update:
            #with self.live.console.status(f"Emitting '{event}' to affect change"):
            requests.get(webhook_url)

            self.live.console.log(f"Dehumidifier should be {'on' if on else 'off'}, but was {self.device_state.value}, so fired event")
            self.device_state = next_state


if __name__ == "__main__":
    load_dotenv()

    with Live(Table(), auto_refresh=False) as live:
        console = live.console
        sense_client = Senseable(getenv("SENSE_USERNAME"), getenv("SENSE_PASSWORD"))

        co2_trigger_data_path = Path("co2_readings.json")
        co2_trigger = CO2Trigger(getenv("CO2SIGNAL_REGION"), getenv("CO2SIGNAL_KEY"), co2_trigger_data_path, console)

        if co2_trigger_data_path.exists():
            co2_trigger.load_data()

        controller = Controller(co2_trigger, sense_client, getenv("WEBHOOK_KEY"), getenv("TRIGGER_DEVICE"), live)
        controller.run()
