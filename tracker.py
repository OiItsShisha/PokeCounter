from PIL import ImageGrab, ImageChops
import pyautogui
from threading import Thread, Event
import pytesseract
import pandas as pd
from pandastable import Table, TableModel
from pathlib import Path

"""
TODO
    - Add proper closing protocol for X button of application
"""


class Tracker:
    def __init__(
        self, session_table, historical_table, json_name, session_label, history_label, huntable_locations
    ):
        self.thread = None
        self.stop_threads = Event()
        pytesseract.pytesseract.tesseract_cmd = (
            "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
        )
        with open("./data/poke_list.txt", "r") as f:
            self.poke_list = [line.strip() for line in f.readlines()]
        self.current_encounter = False
        self.session_table = session_table
        self.historical_table = historical_table
        self.current_map = None
        self.json_name = json_name
        self.session_label = session_label
        self.history_label = history_label
        self.huntable_locations = huntable_locations
        self.current_location = None

    def start_tracker(self, tracking_button):
        # To continuously monitor and trigger an action:
        tracking_button["state"] = "disabled"
        global worker_thread
        self.stop_threads.clear()
        worker_thread = Thread(
            target=self.start_tracker_worker, args=(self.stop_threads,)
        )
        worker_thread.start()

    def stop_tracker(self, tracking_button):
        self.stop_threads.set()
        if worker_thread.is_alive():
            worker_thread.join()
        if tracking_button["state"] == "disabled":
            tracking_button["state"] = "normal"
        self.stop_threads.clear()
        self.historical_table.model.df.to_json(
            self.json_name, orient="records", indent=4
        )

    def start_tracker_worker(self, event):
        while not event.is_set():
            detect_f, detect_ss = self.detect_screen_change(
                threshold=1000
            )  # Sensitivity Threshold
            if detect_f:
                self.run_action_on_change(detect_ss)
            event.wait(timeout=0.1)

    def detect_screen_change(self, region=None, threshold=10):
        """
        Detects changes in a specified region of the screen.

        Args:
            region (tuple, optional): A tuple (left, top, width, height) defining
                                    the area of the screen to monitor. If None,
                                    the entire screen is monitored.
            threshold (int): The maximum difference allowed between pixels
                            before a change is detected. Lower values mean higher sensitivity.

        Returns:
            bool: True if a significant change is detected, False otherwise.
        """
        # Capture the initial screenshot
        initial_screenshot = pyautogui.screenshot(region=region)

        while True:
            current_screenshot = pyautogui.screenshot(region=region)
            # Compare the two screenshots
            diff = ImageChops.difference(initial_screenshot, current_screenshot)
            # Calculate the sum of absolute differences for all pixels
            # A higher sum indicates a greater change
            if diff.getbbox():  # Check if there are any differing pixels
                # Sum the absolute differences of all color channels for each pixel
                # and then sum across all pixels.
                diff_sum = sum(
                    pixel_value
                    for pixel_channel in diff.getdata()
                    for pixel_value in pixel_channel
                )

                if diff_sum > threshold:
                    return (
                        True,
                        current_screenshot,
                    )  # Indicate that a change was detected

            # Update the initial screenshot for the next comparison
            initial_screenshot = current_screenshot

    def update_percentage(self):
        session_total = self.session_table.model.df["Total"].sum()
        history_total = self.historical_table.model.df["Total"].sum()
        self.session_table.model.df["Total Percent"] = (
            self.session_table.model.df["Total"] / session_total
        ) * 100
        self.historical_table.model.df["Total Percent"] = (
            self.historical_table.model.df["Total"] / history_total
        ) * 100
        self.session_table.model.df = self.session_table.model.df.sort_values(
            by="Total Percent", ascending=False
        )
        self.historical_table.model.df = self.historical_table.model.df.sort_values(
            by="Total Percent", ascending=False
        )

    def update_table(self, encounter_name):
        session_seen = list(self.session_table.model.df["Pokemon"])
        history_seen = list(self.historical_table.model.df["Pokemon"])
        if encounter_name in session_seen:
            self.session_table.model.df.loc[
                self.session_table.model.df["Pokemon"] == encounter_name, "Total"
            ] = (
                self.session_table.model.df.loc[
                    self.session_table.model.df["Pokemon"] == encounter_name, "Total"
                ]
                + 1
            )
        elif "Default" in session_seen and encounter_name not in session_seen:
            self.session_table.model.df = pd.DataFrame(
                {
                    "Pokemon": [encounter_name],
                    "Total": [1],
                    "Total Percent": [0],
                    "Morning": [0],
                    "Day": [0],
                    "Night": [0],
                }
            )
        else:
            self.session_table.model.df.loc[len(self.session_table.model.df)] = {
                "Pokemon": encounter_name,
                "Total": 1,
                "Total Percent": 0,
                "Morning": 0,
                "Day": 0,
                "Night": 0,
            }
        if encounter_name in list(self.historical_table.model.df["Pokemon"]):
            self.historical_table.model.df.loc[
                self.historical_table.model.df["Pokemon"] == encounter_name, "Total"
            ] = (
                self.historical_table.model.df.loc[
                    self.historical_table.model.df["Pokemon"] == encounter_name, "Total"
                ]
                + 1
            )
        elif "Default" in history_seen and encounter_name not in history_seen:
            self.historical_table.model.df = pd.DataFrame(
                {
                    "Pokemon": [encounter_name],
                    "Total": [1],
                    "Total Percent": [0],
                    "Morning": [0],
                    "Day": [0],
                    "Night": [0],
                }
            )
        else:
            self.historical_table.model.df.loc[len(self.historical_table.model.df)] = {
                "Pokemon": encounter_name,
                "Total": 1,
                "Total Percent": 0,
                "Morning": 0,
                "Day": 0,
                "Night": 0,
            }
        self.update_percentage()
        self.session_table.redraw()
        self.historical_table.redraw()
        self.session_label.config(
            text=f"Session Tracker | Total Encounters: {self.session_table.model.df["Total"].sum()}"
        )
        self.history_label.config(
            text=f"Historical Tracker | Total Encounters: {self.historical_table.model.df["Total"].sum()}"
        )

    def auto_change_location(self, location_str):
        if self.current_location is None:
            self.current_location = location_str
        elif self.current_location != location_str:
            self.historical_table.model.df.to_json(
                self.json_name, orient="records", indent=4
            )
            loc_str = [x.lower() for x in location_str.split(" ")]
            self.json_name = "_".join(loc_str).strip()
            self.json_name = (
                Path(__file__).resolve().parent / "data" / f"{self.json_name}.json"
            )
            if not Path(self.json_name).exists():
                t_df = pd.DataFrame(
                    {
                        "Pokemon": [0],
                        "Total": [0],
                        "Total Percent": [0],
                        "Morning": [0],
                        "Day": [0],
                        "Night": [0],
                    }
                )
                t_df.to_json(self.json_name, orient="records", indent=4)
            update_df = pd.read_json(self.json_name)
            self.history_label.config(
                text=f"Historical Tracker | Total Encounters: {update_df["Total"].sum()}"
            )
            self.historical_table.model.df = update_df.sort_values(
                by="Total Percent", ascending=False
            )
            self.historical_table.redraw()
            self.current_location = location_str

    def run_action_on_change(self, ss) -> None:
        """If there was a change detected between screenshots, this is invoked.

        Currently, this pulls out the wild pokemon (name) from the encounter box.

        TODO: Add support for pulling out the map name (also add map name list)

        Args:
            ss:

        Returns:
            None
        """

        bbox = (0, 0, 1920, 1080)  # Currently grabbing personal primary monitor
        ss = ImageGrab.grab(bbox=bbox).convert("L")  # Screencapture and greyscale it
        text = pytesseract.image_to_string(
            ss, config="--psm 6"
        )  # Parse the text from ss
        encounter = False  # set true if parsed text has wild
        clean_nl = text.split("\n")
        for i in clean_nl:
            if "Wild" in i:
                encounter = True
                poke = i
        if encounter:
            if not self.current_encounter:
                location_text = pytesseract.image_to_string(ss, config="--psm 3")
                clean_location_text = location_text.split("\n")
                for i in clean_location_text:
                    if i in self.huntable_locations:
                        self.auto_change_location(i)
                self.current_encounter = True
                temp = poke.split(" ")
                for k in temp:
                    if k in self.poke_list:
                        self.update_table(k)
        else:
            self.current_encounter = False
