from PIL import Image, ImageChops
import pyautogui
from threading import Thread, Event
import pytesseract
import pandas as pd
from pathlib import Path
import sys
import pygetwindow as gw

# Conditionally import Windows-specific libraries
if sys.platform == 'win32':
    import win32gui
    import win32ui
    import win32con

"""
TODO
    - Add proper closing protocol for X button of application
"""


class Tracker:
    """
    Tracker class for the Pokemon Encounter Tracker.

    This class handles the screen reading and encounter tracking logic.
    """

    def __init__(
        self, session_table, historical_table, json_name, session_label, history_label, huntable_locations, all_spawns
    ):
        """
        Initializes the Tracker class.
        """
        self.thread = None
        self.stop_threads = Event()
        pytesseract.pytesseract.tesseract_cmd = (
            "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
        )
        self.current_encounter = False
        self.session_table = session_table
        self.historical_table = historical_table
        self.current_map = None
        self.json_name = json_name
        self.session_label = session_label
        self.history_label = history_label
        self.huntable_locations = huntable_locations
        self.current_location = None
        self.all_spawns = all_spawns

    def start_tracker(self, tracking_button):
        """
        Starts the screen tracker thread.
        """
        # To continuously monitor and trigger an action:
        tracking_button["state"] = "disabled"
        global worker_thread
        self.stop_threads.clear()
        worker_thread = Thread(
            target=self.start_tracker_worker, args=(self.stop_threads,)
        )
        worker_thread.start()

    def stop_tracker(self, tracking_button):
        """
        Stops the screen tracker thread.
        """
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
        """
        The worker method for the screen tracker thread.
        """
        # This hidden window capture implementation is for Windows only.
        if sys.platform != 'win32':
            print("ERROR: Hidden window capture is only supported on Windows.")
            return

        pro_window = None
        while not pro_window and not event.is_set():
            try:
                pro_window_list = gw.getWindowsWithTitle("PROClient")
                if pro_window_list:
                    pro_window = pro_window_list[0]
                else:
                    print("PROClient window not found. Retrying in 5 seconds...")
                    event.wait(timeout=5)
            except Exception as e:
                print(f"An error occurred while finding the window: {e}")
                event.wait(timeout=5)

        if not pro_window:
            return

        while not event.is_set():
            try:
                # Check if the window handle is still valid
                if not win32gui.IsWindow(pro_window._hWnd):
                    print("PROClient window was closed. Stopping tracker.")
                    break
            except Exception:  # Catches errors if window is destroyed
                print("PROClient window not found. Stopping tracker.")
                break

            detect_f, detect_ss = self.detect_screen_change(
                hwnd=pro_window._hWnd,
                threshold=1000
            )
            if detect_f:
                self.run_action_on_change(detect_ss)
            event.wait(timeout=0.5)

    def _capture_window_win32(self, hwnd):
        """
        Captures a screenshot of a window using the Win32 API.
        This method works even if the window is hidden or occluded, but not minimized.
        NOTE: This implementation is untested due to environment limitations.
        """
        try:
            left, top, right, bot = win32gui.GetClientRect(hwnd)
            w = right - left
            h = bot - top

            if w <= 0 or h <= 0:
                return None

            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()

            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)

            saveDC.SelectObject(saveBitMap)

            result = win32gui.PrintWindow(hwnd, saveDC.GetSafeHdc(), win32con.PW_CLIENTONLY)

            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)

            im = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1)

            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)

            return im if result == 1 else None
        except Exception as e:
            print(f"Error capturing window: {e}")
            return None

    def detect_screen_change(self, hwnd, threshold=10):
        """
        Detects changes in a specified window using Win32 API.

        Args:
            hwnd (int): The handle of the window to monitor.
            threshold (int): The maximum difference allowed between pixels
                            before a change is detected. Lower values mean higher sensitivity.

        Returns:
            tuple: A tuple containing a boolean indicating if a change was detected
                   and the screenshot image.
        """
        # Capture the initial screenshot
        initial_screenshot = self._capture_window_win32(hwnd)

        while True:
            current_screenshot = self._capture_window_win32(hwnd)

            # If capture fails (e.g., window minimized), return no change.
            if initial_screenshot is None or current_screenshot is None:
                initial_screenshot = current_screenshot
                return (False, None)

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
        """
        Updates the percentage of each pokemon seen in the session and historical tables.
        """
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
        """
        Updates the session and historical tables with the new encounter.
        """
        self.session_table.model.df.loc[
            self.session_table.model.df["Pokemon"] == encounter_name, "Total"
        ] = (
            self.session_table.model.df.loc[
                self.session_table.model.df["Pokemon"] == encounter_name, "Total"
            ]
            + 1
        )

        self.historical_table.model.df.loc[
            self.historical_table.model.df["Pokemon"] == encounter_name, "Total"
        ] = (
            self.historical_table.model.df.loc[
                self.historical_table.model.df["Pokemon"] == encounter_name, "Total"
            ]
            + 1
        )
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
        """
        Automatically changes the location when the player moves to a new location.
        """
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
            temp = self.all_spawns[self.all_spawns["Map"] == self.location_cb.get()]
            if not Path(self.json_name).exists():
                t_df = pd.DataFrame(
                    {
                        "Pokemon": temp["Pokemon"].to_list(),
                        "Rarity": temp["Tier"].to_list(),
                        "Total": [0] * len(temp),
                        "Total Percent": [0] * len(temp),
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

    def run_action_on_change(self, ss):
        """If there was a change detected between screenshots, this is invoked.

        Currently, this pulls out the wild pokemon (name) from the encounter box.

        Args:
            ss:

        Returns:
            None
        """
        ss = ss.convert("L")  # Screencapture and greyscale it
        text = pytesseract.image_to_string(
            ss, config="--psm 6"
        )  # Parse the text from ss
        wild_encounter_flag = False  # set true if parsed text has wild
        clean_newl = text.split("\n")
        # Check if the text is a wild encounter.
        for i in clean_newl:
            if "Wild" in i:
                wild_encounter_flag = True
                poke_line = i.split(" ")
        if wild_encounter_flag:
            if not self.current_encounter:
                location_text = pytesseract.image_to_string(ss, config="--psm 3")
                clean_location_text = location_text.split("\n")
                for i in clean_location_text:
                    if i in self.huntable_locations:
                        self.auto_change_location(i)
                self.current_encounter = True
                for word in poke_line:
                    if word in self.session_table.model.df["Pokemon"].to_list():
                        self.update_table(word)
        else:
            self.current_encounter = False
