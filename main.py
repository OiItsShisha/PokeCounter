"""
TODO:
    Add a popup window as warning for deleting data for both session and history
    Add option to track trace'd abilities
    Figure out how to have the app appear over the top of the PRO application
    Sort out Morning day and night to update the table
    Try to add a notification for encounter
    Try to screenread PRO client specifically
        - may be able to use pyautogui instead of PIL
    Add Session timer
"""

import tkinter as tk
import pandas as pd
from tkinter import ttk
from pathlib import Path
from pandastable import Table
import time
from tracker import Tracker


class MainApplication(tk.Tk):
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pokemon Encounter Tracker")
        self.top = tk.Frame(self.root)
        self.top.pack(side=tk.TOP)

        self.session_label = tk.Label(
            self.root, text=f"Session Tracker", font=("Arial", 12, "bold")
        )
        self.session_label.pack()
        self.bottom_t1 = tk.Frame(self.root)
        self.bottom_t1.pack(fill=tk.BOTH)
        self.historical_label = tk.Label(
            self.root, text="Historical Tracker", font=("Arial", 12, "bold")
        )
        self.historical_label.pack()
        self.bottom_t2 = tk.Frame(self.root)
        self.bottom_t2.pack(fill=tk.BOTH, expand=1)  # Expand here to stretch to bottom

        self.history_table = None
        self.session_table = None
        self.top_cb = None
        self.location_button = None
        self.tracking_button = None
        self.tracker = None
        with open("huntable_locations.txt", "r") as f:
            self.huntable_locations = f.readlines()
            self.huntable_locations = [x.strip() for x in self.huntable_locations]

        self.create_elements()
        self.json_name = None

    def create_elements(self):
        # Combo box
        self.top_cb = ttk.Combobox(self.top, values=self.huntable_locations)
        self.top_cb.set("Select a Hunting Location")
        self.top_cb.pack()

        # Buttons
        self.location_button = tk.Button(
            self.top, text="Show Selection", command=self.load_location_data
        )
        self.location_button.pack(side=tk.LEFT)
        self.tracking_button = tk.Button(self.top, text="Begin Tracking")
        self.tracking_button.config(
            command=lambda: self.tracker.start_tracker(self.tracking_button)
        )
        self.tracking_button.pack(side=tk.LEFT)
        self.end_tracking_bt = tk.Button(self.top, text="Stop Tracking")
        self.end_tracking_bt.config(
            command=lambda: self.tracker.stop_tracker(self.tracking_button)
        )
        self.end_tracking_bt.pack(side=tk.LEFT)
        self.clear_session_bt = tk.Button(
            self.top, text="Clear Session Data", command=self.clear_session_data
        )
        self.clear_session_bt.pack(side=tk.LEFT)
        self.clear_historical_bt = tk.Button(
            self.top, text="Clear Historical Data", command=self.clear_historical
        )
        self.clear_historical_bt.pack(side=tk.LEFT)

        session_default_table = pd.DataFrame(
            {
                "Pokemon": ["Default"],
                "Total": [0],
                "Total Percent": [0],
                "Morning": [0],
                "Day": [0],
                "Night": [0],
            }
        )
        history_default_table = pd.DataFrame(
            {
                "Pokemon": ["Default"],
                "Total": [0],
                "Total Percent": [0],
                "Morning": [0],
                "Day": [0],
                "Night": [0],
            }
        )

        self.session_table = Table(self.bottom_t1, dataframe=session_default_table)
        self.session_table.show()

        self.history_table = Table(self.bottom_t2, dataframe=history_default_table)
        self.history_table.show()

    def clear_session_data(self):
        self.session_table.model.df = pd.DataFrame(
            {
                "Pokemon": ["Default"],
                "Total": [0],
                "Total Percent": [0],
                "Morning": [0],
                "Day": [0],
                "Night": [0],
            }
        )
        self.session_table.redraw()

    def clear_historical(self):
        self.history_table.model.df = pd.DataFrame(
            {
                "Pokemon": ["Default"],
                "Total": [0],
                "Total Percent": [0],
                "Morning": [0],
                "Day": [0],
                "Night": [0],
            }
        )
        self.history_table.model.df.to_json(self.json_name, orient="records", index=4)
        self.history_table.redraw()

    def load_location_data(self) -> None:
        """Method used as callable to update the table data

        The original table has a default state and this method invokes when the
            'Show Selection' button is clicked. It then updated the global state of the
            pandas table.

        Args:
            None

        Returns:
            None
        """
        # Pulling the map poke data from the selector and loading the corresponding JSON file.
        loc_name = [x.lower() for x in self.top_cb.get().split(" ")]
        self.json_name = "_".join(loc_name).strip()
        self.json_name = (
            Path(__file__).resolve().parent / "data" / f"{self.json_name}.json"
        )
        self.tracker = Tracker(
            self.session_table,
            self.history_table,
            self.json_name,
            self.session_label,
            self.historical_label,
            self.huntable_locations
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
        self.historical_label.config(
            text=f"Historical Tracker | Total Encounters: {update_df["Total"].sum()}"
        )
        self.history_table.model.df = update_df.sort_values(
            by="Total Percent", ascending=False
        )
        self.history_table.redraw()


def main() -> None:
    """The main method

    Args:
        None

    Returns:
        None
    """
    app = MainApplication()
    app.root.mainloop()


if __name__ == "__main__":
    main()
