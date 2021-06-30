from co2_trigger import CO2Trigger
from enum import Enum
from dotenv import load_dotenv
from os import getenv
from pathlib import Path
import requests
from rich.console import Console
from sense_energy import Senseable
from time import sleep

from co2_trigger import CO2Trigger


DEVICE_DRAW_THRESHOLD = 50 # Watts


class DeviceState(Enum):
    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


class Controller:
    def __init__(self, co2_trigger:CO2Trigger, sense_client: Senseable, webhook_key:str, sense_device: str, console: Console):
        self.sense_client = sense_client
        self.console = console
        self.sense_device = sense_device
        self.device_state = DeviceState.UNKNOWN
        self.webhook_key = webhook_key
        self.co2_trigger = co2_trigger

    def run(self):
        while(True):
            with self.console.status("Fetching CO2 data"):
                self.co2_trigger.update_data()

            co2_is_high = self.co2_trigger.is_co2_high()
            dehumidifier_should_be_on = not co2_is_high and not self.is_device_on()
            self.update_device(dehumidifier_should_be_on)

            sleep_duration = 120
            if co2_is_high:
                sleep_duration = 1800
                self.console.log("CO2 is high. Will pause and check back in 30 minutes")

            sleep(sleep_duration)

    
    def is_device_on(self):
        with self.console.status("Fetching Sense data"):
            self.sense_client.update_realtime()
            realtime_data = self.sense_client.get_realtime()

        for device in realtime_data["devices"]:
            device_name = device["name"]
            if device_name != self.sense_device:
                continue

            device_draw = device["w"]
            device_is_on = device_draw > DEVICE_DRAW_THRESHOLD
            check = ":x:" if device_is_on else ":heavy_check_mark:"
            self.console.log(f"{check} {device_name} ({device_draw:.1f} Watts) should be less than {DEVICE_DRAW_THRESHOLD} Watts")
            return device_is_on

        self.console.log(f":heavy_check_mark: {device_name} missing, inferred (0W) < {DEVICE_DRAW_THRESHOLD}W")
        return False


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
            with self.console.status(f"Emitting '{event}' to affect change"):
                requests.get(webhook_url)

            self.console.log(f"Dehumidifier should be {'on' if on else 'off'}, but was {self.device_state.value}, so fired event")
            self.device_state = next_state


if __name__ == "__main__":
    load_dotenv()

    console = Console()
    sense_client = Senseable(getenv("SENSE_USERNAME"), getenv("SENSE_PASSWORD"))

    co2_trigger_data_path = Path("co2_readings.json")
    co2_trigger = CO2Trigger(getenv("CO2SIGNAL_REGION"), getenv("CO2SIGNAL_KEY"), co2_trigger_data_path, console)

    if co2_trigger_data_path.exists():
        co2_trigger.load_data()

    controller = Controller(co2_trigger, sense_client, getenv("WEBHOOK_KEY"), getenv("TRIGGER_DEVICE"), console)
    controller.run()
