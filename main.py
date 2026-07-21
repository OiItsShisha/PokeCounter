import os
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import pandas as pd
from pandastable import Table
from screeninfo import get_monitors
from tracker import Tracker


def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller.

    Args:
        relative_path (str): The relative path to the desired asset or file.

    Returns:
        str: The absolute path string mapped correctly depending on compilation execution.
    """
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller extracts bundled files to the sys._MEIPASS root directory
        base_path = Path(sys._MEIPASS) / "spawn_data"
    else:
        # Development mode path relative to workspace
        base_path = Path(".").resolve() / "spawn_data"

    return str(base_path / relative_path)


class ScreenSelector:
    """
    A full-screen transparent overlay canvas utilized for screen-capture selection.

    Allows users to draw a bounded rectangle on any monitor in a multi-display setup 
    by mapping the absolute boundaries of the virtual desktop matrix.

    Best used resolution - 1024x768 or higher
    """

    def __init__(self, callback):
        """
        Initializes the selection overlay window across all active monitors.

        Args:
            callback (function): The method to pass the execution coordinates to upon click release.
        """
        self.callback = callback
        self.root = tk.Tk()

        # 1. Fetch all monitors and calculate the global bounding box
        monitors = get_monitors()
        
        # Track the absolute outermost coordinates of your combined displays
        min_x = min(m.x for m in monitors)
        min_y = min(m.y for m in monitors)
        max_x = max(m.x + m.width for m in monitors)
        max_y = max(m.y + m.height for m in monitors)
        
        virtual_width = max_x - min_x
        virtual_height = max_y - min_y

        # 2. Position the window at the true global origin (handles negative offsets)
        self.root.geometry(f"{virtual_width}x{virtual_height}+{min_x}+{min_y}")
        
        # 3. Strip window borders to make it feel full-screen
        self.root.overrideredirect(True) 
        
        # 4. Standard settings for transparency overlay
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.3)
        self.root.config(cursor="cross")

        self.canvas = tk.Canvas(self.root, cursor="cross", bg="grey")
        self.canvas.pack(fill="both", expand=True)

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def on_button_press(self, event):
        """Captures the starting coordinates when the user presses down the left-click."""
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, 1, 1, outline="red", width=2
        )

    def on_move_press(self, event):
        """Redraws the selection bounding box in real time as the mouse drags."""
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_button_release(self, event):
        """Normalizes drag points, closes the overlay, and pushes bounded data out to the callback."""
        # Adjust coordinates relative to the virtual screen space offset
        # This ensures the final coordinates match what your OCR/Screenshot tool expects globally
        monitors = get_monitors()
        min_x = min(m.x for m in monitors)
        min_y = min(m.y for m in monitors)

        x1 = min(self.start_x, event.x) + min_x
        y1 = min(self.start_y, event.y) + min_y
        x2 = max(self.start_x, event.x) + min_x
        y2 = max(self.start_y, event.y) + min_y

        self.root.destroy()
        self.callback((x1, y1, x2, y2))


class MainApplication(tk.Tk):
    """
    Main application window for the Pokemon Encounter Tracker.

    This class creates the main window and all the UI elements,
    and handles the main logic of the application.
    """

    def __init__(self):
        """
        Initializes the main application window and its variables.
        """
        super().__init__()

        self.title("PokePulse - A Pokemon Encounter Tracker developed by Shishagames.")
        self.geometry("900x700")

        self.top = tk.Frame(self)
        self.top.pack(side=tk.TOP)

        self.session_label = tk.Label(
            self, text="Session Tracker", font=("Arial", 12, "bold")
        )
        self.session_label.pack()

        self.bottom_t1 = tk.Frame(self)
        self.bottom_t1.pack(fill=tk.BOTH)
        
        self.historical_label = tk.Label(
            self, text="Historical Tracker", font=("Arial", 12, "bold")
        )
        self.historical_label.pack()
        
        self.bottom_t2 = tk.Frame(self)
        self.bottom_t2.pack(fill=tk.BOTH, expand=True)

        self.session_start_time = None
        self.elapsed_time = 0
        self.timer_running = False
        self.after_id = None
        
        self.history_table = None
        self.session_table = None
        self.location_cb = None
        self.location_button = None
        self.tracking_button = None
        self.search_area = None
        self.tracker = None
        self.location_df = None
        self.json_name = None
        
        # EFFICIENCY: Cache read CSV dataframes to avoid repetitive Disk I/O overhead
        self._csv_cache = {}

        self.create_elements()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_elements(self):
        """
        Creates all the UI layout architecture, dropdowns, tables, and buttons in the main window.

        Args:
            None

        Returns:
            None
        """
        dropdown_frame = tk.Frame(self.top)
        dropdown_frame.pack(side=tk.TOP)
        button_frame = tk.Frame(self.top)
        button_frame.pack(side=tk.TOP)

        regions = [
            "Kanto", "Johto", "Hoenn", "Sinnoh", "Sevii Islands", 
            "Pinkan Island", "Easter Event Map", "Summer Event Map", 
            "Valentine Event Map", "Halloween Event Map", 
            "Christmas Event Map", "Excavation"
        ]
        
        self.region_cb = ttk.Combobox(dropdown_frame, values=regions, state="readonly")
        self.region_cb.set("Select a Region")
        self.region_cb.pack(side=tk.LEFT)
        self.region_cb.bind("<<ComboboxSelected>>", self.update_locations)

        self.location_cb = ttk.Combobox(dropdown_frame, values=[], width=45, state="readonly")
        self.location_cb.set("Select a Hunting Location")
        self.location_cb.pack(side=tk.LEFT)

        self.terrain_cb = ttk.Combobox(dropdown_frame, values=["Land", "Water"], width=10, state="readonly")
        self.terrain_cb.set("Land")
        self.terrain_cb.pack(side=tk.LEFT, padx=5)

        self.location_button = tk.Button(
            button_frame, text="Show Selection", command=self.load_location_data, bg="#4EBDBD"
        )
        self.location_button.pack(side=tk.LEFT)

        self.config_button = tk.Button(
            button_frame, text="Set Wild Poke Name Area", command=self.start_selection, bg="#4EBDBD"
        )
        self.config_button.pack(side=tk.LEFT)

        self.tracking_button = tk.Button(
            button_frame, text="Begin Tracking", state="disabled", bg="#4EBDBD",
            command=self.start_tracking_flow
        )
        self.tracking_button.pack(side=tk.LEFT)
        
        self.end_tracking_bt = tk.Button(
            button_frame, text="Stop Tracking", bg="#4EBDBD", command=self.stop_tracking_flow
        )
        self.end_tracking_bt.pack(side=tk.LEFT)
        
        self.clear_session_bt = tk.Button(
            button_frame, text="Clear Session Data", command=self.clear_session_data, bg="#4EBDBD"
        )
        self.clear_session_bt.pack(side=tk.LEFT)
        
        self.clear_historical_bt = tk.Button(
            button_frame, text="Clear Historical Data", command=self.clear_historical, bg="#4EBDBD"
        )
        self.clear_historical_bt.pack(side=tk.LEFT)

        default_df = pd.DataFrame({
            "Pokemon": ["Default"], "Terrain": ["Default"], "Total": [0], "Total Percent": [0]
        })

        self.session_table = Table(self.bottom_t1, dataframe=default_df)
        self.session_table.show()

        self.history_table = Table(self.bottom_t2, dataframe=default_df)
        self.history_table.show()

    def start_tracking_flow(self):
        """
        Triggers the underlying tracker processing threads and kicks off the session clock.

        Args:
            None

        Returns:
            None
        """
        if self.tracker:
            self.tracker.start_tracker(self.tracking_button, self.location_button, self.config_button)
            self.toggle_timer(start=True)

    def stop_tracking_flow(self):
        """
        Signals tracking threads to cease work safely and pauses the operational clock.

        Args:
            None

        Returns:
            None
        """
        if self.tracker:
            self.tracker.stop_tracker(self.tracking_button, self.location_button, self.config_button)
            self.toggle_timer(start=False)

    def update_timer(self):
        """
        Executes a recurring window loop to calculate, process, and display tracking runtime.

        Args:
            None

        Returns:
            None
        """
        if self.timer_running:
            current_session = time.time() - self.session_start_time
            total_seconds = int(self.elapsed_time + current_session)
            
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            total_encounters = self.session_table.model.df['Total'].sum()
            self.session_label.config(
                text=f"Session Tracker | Total Encounters: {total_encounters} | Time: {hours:02}:{minutes:02}:{seconds:02}"
            )
            self.after_id = self.after(1000, self.update_timer)

    def toggle_timer(self, start=True):
        """
        Switches the execution states of the update_timer loops and tracks accrued runtime.

        Args:
            start (bool): Determines whether to engage or cease active session tracking clocks.

        Returns:
            None
        """
        if start:
            self.session_start_time = time.time()
            self.timer_running = True
            self.update_timer()
        else:
            if self.timer_running:
                self.elapsed_time += (time.time() - self.session_start_time)
                self.timer_running = False
                if self.after_id:
                    self.after_cancel(self.after_id)

    def start_selection(self):
        """
        Minimizes main display windows out of view to initiate a clean screen coordinates selector.

        Args:
            None

        Returns:
            None
        """
        self.withdraw()
        ScreenSelector(self.save_coordinates)

    def save_coordinates(self, coords):
        """
        Restores windows and processes generated coordinate pairs from active bounding overlays.

        Args:
            coords (tuple): Contains custom bounded dimensions formatted as (x1, y1, x2, y2).

        Returns:
            None
        """
        self.deiconify()
        x1, y1, x2, y2 = coords
        if x2 - x1 > 5 and y2 - y1 > 5:
            self.search_area = coords
            self.tracking_button.config(state=tk.NORMAL)
            if self.tracker:
                self.tracker.update_search_area(coords)
            messagebox.showinfo("Success", "Search area set!")
        else:
            messagebox.showwarning("Selection Error", "Area too small.")

    def update_locations(self, event) -> None:
        """
        Updates the location combobox based on the selected region and loads the appropriate data
        after a location has been selected. Uses cached data to optimize resource lookup.

        Args:
            event (tk.Event): The triggered selection container from changing UI values.

        Returns:
            None
        """
        selected_region = self.region_cb.get()
        
        region_file_map = {
            "Kanto": "kanto_spawns.csv",
            "Johto": "johto_spawns.csv",
            "Hoenn": "hoenn_spawns.csv",
            "Sinnoh": "sinnoh_spawns.csv",
            "Excavation": "excavation_spawns.csv",
            "Sevii Islands": "sevii_islands_spawns.csv",
            "Pinkan Island": "pinkan_spawns.csv",
            "Easter Event Map": "breezy_spawns.csv",
            "Valentine Event Map": "aphrodia_spawns.csv",
            "Summer Event Map": "vulcan_spawns.csv",
            "Halloween Event Map": "phantasm_spawns.csv",
            "Christmas Event Map": "evergreen_spawns.csv",
        }

        filename = region_file_map.get(selected_region)
        if filename:
            # EFFICIENCY: Serve from memory cache if file was previously opened
            if filename not in self._csv_cache:
                self._csv_cache[filename] = pd.read_csv(resource_path(filename))
            
            self.location_df = self._csv_cache[filename]
            self.location_cb["values"] = self.location_df["Map"].unique().tolist()
            self.location_cb.set("Select a Hunting Location")

    def clear_session_data(self):
        """
        Clears the current volatile runtime session data table parameters.

        Args:
            None

        Returns:
            None
        """
        if messagebox.askyesno("Clear Session Data", "Are you sure you wish you clear this data?"):
            current_df = self.session_table.model.df
            poke_list = current_df["Pokemon"].to_list()
            
            new_data = {
                "Pokemon": poke_list,
                "Total": [0] * len(poke_list),
                "Total Percent": [0] * len(poke_list),
            }
            if "Night" in current_df.columns:
                new_data["Night"] = current_df["Night"].map({1: "Yes", 0: "No"}).to_list()
            elif "Terrain" in current_df.columns:
                new_data["Terrain"] = current_df["Terrain"].to_list()

            self.session_table.model.df = pd.DataFrame(new_data)
            self.session_table.redraw()
            
            self.toggle_timer(start=False)
            self.elapsed_time = 0
            current_text = self.session_label.cget("text").split(" | ")[0]
            self.session_label.config(text=f"{current_text} | Total Encounters: 0 | Time: 00:00:00")

    def clear_historical(self):
        """
        Resets tracking totals inside data models and clears out persistent local JSON files.

        Args:
            None

        Returns:
            None
        """
        if messagebox.askyesno("Clear Historical Data", "Are you sure you wish you clear this data?"):
            current_df = self.history_table.model.df
            poke_list = current_df["Pokemon"].to_list()
            
            self.history_table.model.df = pd.DataFrame({
                "Pokemon": poke_list,
                "Terrain": current_df["Terrain"].to_list() if "Terrain" in current_df.columns else ["Default"] * len(poke_list),
                "Total": [0] * len(poke_list),
                "Total Percent": [0] * len(poke_list),
            })
            
            if self.json_name:
                self.history_table.model.df.to_json(self.json_name, orient="records", indent=4)
            self.history_table.redraw()

    def load_location_data(self) -> None:
        """
        Builds, maps, verifies, and sets up JSON templates and frames for targeted locations.

        Args:
            None

        Returns:
            None
        """
        location_selection = self.location_cb.get()
        if not location_selection or location_selection == "Select a Hunting Location":
            messagebox.showwarning("Selection Error", "Please select a valid location first.")
            return

        # EFFICIENCY: Faster low-level string replacement over parsing lists
        filename = location_selection.lower().replace(" ", "_").strip() + ".json"

        template_path = Path(resource_path("data")) / filename
        persistent_data_dir = Path(".").resolve() / "data"
        self.json_name = str(persistent_data_dir / filename)

        persistent_data_dir.mkdir(parents=True, exist_ok=True)
        
        # EFFICIENCY: Cache slice query immediately to minimize multiple lookups
        temp = self.location_df[self.location_df["Map"] == location_selection]

        if not Path(self.json_name).exists():
            if template_path.exists():
                t_df = pd.read_json(template_path)
            else:
                t_df = pd.DataFrame({
                    "Pokemon": temp["Pokemon"].to_list(),
                    "Terrain": temp["Terrain"].to_list(),
                    "Total": [0] * len(temp),
                    "Total Percent": [0] * len(temp),
                })
            t_df.to_json(self.json_name, orient="records", indent=4)
        self.tracker = Tracker(
            self.session_table,
            self.history_table,
            self.json_name,
            self.session_label,
            self.historical_label,
            search_area=self.search_area,
            terrain_var=self.terrain_cb
        )

        update_df = pd.read_json(self.json_name)
        
        if "Terrain" not in update_df.columns:
            terrain_data = update_df.merge(temp, on="Pokemon")["Terrain"].to_list()
            update_df["Terrain"] = terrain_data
        if list(update_df.columns) != ["Pokemon", "Terrain", "Total", "Total Percent"]:
            update_df = update_df[["Pokemon", "Terrain", "Total", "Total Percent"]]

        self.session_label.config(text="Session Tracker | Total Encounters: 0")
        self.session_table.model.df = pd.DataFrame({
            "Pokemon": temp["Pokemon"].to_list(),
            "Terrain": temp["Terrain"].to_list(),
            "Total": [0] * len(temp),
            "Total Percent": [0] * len(temp),
        })
        self.session_table.redraw()

        self.historical_label.config(
            text=f"Historical Tracker | Total Encounters: {update_df['Total'].sum()}"
        )
        self.history_table.model.df = update_df.sort_values(by="Total Percent", ascending=False)
        self.history_table.redraw()

    def on_closing(self) -> None:
        """
        Protocol handling cleanly joining threads and shutting down windows when clicking X.

        Args:
            None

        Returns:
            None
        """
        if self.tracker and hasattr(self.tracker, 'thread') and self.tracker.thread and self.tracker.thread.is_alive():
            self.tracker.stop_threads.set()
            self.tracker.thread.join(timeout=1.0)
        self.destroy()
        sys.exit(0)


def main() -> None:
    """
    The main app entry point initializer.

    Args:
        None

    Returns:
        None
    """
    app = MainApplication()
    app.mainloop()


if __name__ == "__main__":
    main()