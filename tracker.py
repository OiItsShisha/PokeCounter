import mss
import mss.tools
from PIL import Image
from threading import Thread, Event
import winocr
import pandas as pd
from typing import Tuple, Optional, Any, Protocol


# Simple structural type interfaces for the UI widgets to ensure strict type safety
class TableComponent(Protocol):
    model: Any
    def redraw(self) -> None: ...

class TkWidget(Protocol):
    def config(self, **kwargs: Any) -> None: ...
    def cget(self, index: str) -> Any: ...
    def __setitem__(self, key: str, value: Any) -> None: ...


class Tracker:
    """
    Automated screen-scraping system that tracks game encounters via OCR.

    Monitors a specific bounding region of the user's desktop, extracts 
    in-game encounter names via Windows OCR, matches occurrences against a 
    provided catalog terrain database, and updates user metrics dynamically.
    Optimized to use native hardware screen hooks and pre-calculated memory arrays.
    """

    def __init__(
        self,
        session_table: TableComponent,
        historical_table: TableComponent,
        json_name: str,
        session_label: TkWidget,
        history_label: TkWidget,
        search_area: Optional[Tuple[int, int, int, int]] = None,
        terrain_var: Optional[Any] = None,
    ) -> None:
        """
        Initializes the Tracker engine with required UI elements and file states.

        Args:
            session_table: The live UI table manager displaying current session stats.
            historical_table: The UI table manager displaying all-time historical records.
            json_name: File system destination path to save historical records.
            session_label: UI label component showcasing active session counts/timers.
            history_label: UI label component showcasing overall historical counts.
            search_area: Bounding box coordinate configurations formatted as (x1, y1, x2, y2).
            terrain_var: A Tkinter variable instance tracking selected biomes/terrains.
        """
        self.thread: Optional[Thread] = None
        self.stop_threads: Event = Event()
        self.current_encounter: bool = False
        self.session_table: TableComponent = session_table
        self.historical_table: TableComponent = historical_table
        self.current_map: Optional[str] = None
        self.json_name: str = json_name
        self.session_label: TkWidget = session_label
        self.history_label: TkWidget = history_label
        self.current_location: Optional[str] = None
        self.current_poke: Optional[str] = None
        self.encounter_start_time: Optional[float] = None
        self.terrain_var: Optional[Any] = terrain_var
        self.search_area: Optional[Tuple[int, int, int, int]] = search_area
        
        # Initialize mss context manager once to avoid spinning it up repeatedly
        self.sct: mss.mss = mss.mss()

    def update_search_area(self, new_coords: Tuple[int, int, int, int]) -> None:
        """
        Updates the screenshot capture boundaries dynamically without restarting the system.

        Args:
            new_coords: A tuple of 4 absolute screen coordinates (x1, y1, x2, y2).
        """
        self.search_area = new_coords

    def take_screenshot(self) -> Image.Image:
        """
        Captures only the target bounding box natively using mss (Blazing Fast).

        Raises:
            TypeError: If `search_area` has not been defined yet.

        Returns:
            A PIL-based image surface object representing the target layout.
        """
        if not self.search_area:
            raise TypeError("Cannot take screenshot: search_area coordinates are not set.")

        x1, y1, x2, y2 = self.search_area
        
        # mss expects a monitor dictionary structure
        monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
        sct_img = self.sct.grab(monitor)
        
        # Convert raw screen bits cleanly to a PIL Image instance for winocr compatibility
        return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    def _set_button_states(
        self, 
        tracking_btn: TkWidget, 
        location_btn: TkWidget, 
        config_btn: TkWidget, 
        state: str
    ) -> None:
        """
        Helper method to switch interactive widget states between normal and disabled.

        Args:
            tracking_btn: Main execution switch component.
            location_btn: Location setup routing configuration element.
            config_btn: Custom property window setup trigger element.
            state: Core accessibility assignment rule (e.g., "disabled" or "normal").
        """
        tracking_btn["state"] = state
        location_btn["state"] = state
        config_btn["state"] = state

    def start_tracker(
        self, 
        tracking_button: TkWidget, 
        location_button: TkWidget, 
        config_button: TkWidget
    ) -> None:
        """
        Locks interface interaction buttons and initializes the background daemon loop.

        Args:
            tracking_button: Main toggle button managing tracking states.
            location_button: Setup configuration interface locking node.
            config_button: General settings configuration locking node.
        """
        self._set_button_states(tracking_button, location_button, config_button, "disabled")
        self.stop_threads.clear()

        self.thread = Thread(target=self.start_tracker_worker, daemon=True)
        self.thread.start()

    def stop_tracker(
        self, 
        tracking_button: TkWidget, 
        location_button: TkWidget, 
        config_button: TkWidget
    ) -> None:
        """
        Halts the operational worker thread safely and flushes the results cache to disk.

        Args:
            tracking_button: Main toggle button managing tracking states.
            location_button: Setup configuration interface node to unlock.
            config_button: General settings configuration node to unlock.
        """
        self.stop_threads.set()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

        self._set_button_states(tracking_button, location_button, config_button, "normal")
        self.stop_threads.clear()
        
        # Eagerly flush variables safely out to file on shutdown
        self.save_to_json()

    def start_tracker_worker(self) -> None:
        """
        Executes an ongoing loop that captures screens and processes text updates.

        Runs inside a worker background thread. Terminates when `stop_threads` Event is set.
        """
        while not self.stop_threads.is_set():
            screenshot = self.take_screenshot()
            self.run_action_on_change(screenshot)
            self.stop_threads.wait(timeout=0.5)

    def _process_table_metrics(self, table: TableComponent, total_sum: int) -> None:
        """
        Recalculates total percentage ratios and sorts table elements.

        Accepts pre-calculated sums to eliminate redundant O(N) array traversals.

        Args:
            table: Target interactive tracker data model to clean and structure.
            total_sum: Pre-computed sum total of encounters for this specific table.
        """
        df: pd.DataFrame = table.model.df
        if total_sum > 0:
            df["Total Percent"] = (df["Total"] / total_sum) * 100
            table.model.df = df.sort_values(by="Total Percent", ascending=False)

    def save_to_json(self) -> None:
        """
        Saves historical records. 
        
        Extracted to a dedicated method to enable batch-saving patterns instead of 
        spamming the disk on every tick loop.
        """
        self.historical_table.model.df.to_json(self.json_name, orient="records", indent=4)

    def update_table(self, encounter_name: str, terrain: str) -> None:
        """
        Increments totals for matching metrics and updates UI labels.

        Caches array calculations up front to drastically reduce metric processing times.

        Args:
            encounter_name: Clean identifier matching target name records.
            terrain: Explicit subcategory descriptor representing current environment context.
        """
        # Create separate masks for each table
        session_mask = (self.session_table.model.df["Pokemon"] == encounter_name) & \
                    (self.session_table.model.df["Terrain"] == terrain)

        hist_mask = (self.historical_table.model.df["Pokemon"] == encounter_name) & \
                    (self.historical_table.model.df["Terrain"] == terrain)

        # Apply updates independently
        self.session_table.model.df.loc[session_mask, "Total"] += 1
        self.historical_table.model.df.loc[hist_mask, "Total"] += 1

        # 3. Cache sums ONCE up-front to prevent 4x array iterations
        session_total: int = self.session_table.model.df["Total"].sum()
        historical_total: int = self.historical_table.model.df["Total"].sum()

        # 4. Process math logic leveraging optimized inputs
        self._process_table_metrics(self.session_table, session_total)
        self._process_table_metrics(self.historical_table, historical_total)

        # 5. Flush structural changes out to UI views
        self.session_table.redraw()
        self.historical_table.redraw()

        # Isolate session layout configurations to protect ongoing background timers
        current_session_text: str = self.session_label.cget("text")
        if "Time:" in current_session_text:
            time_part: str = current_session_text.split(" | ")[-1]
            new_session_text: str = f"Session Tracker | Total Encounters: {session_total} | {time_part}"
        else:
            new_session_text = f"Session Tracker | Total Encounters: {session_total}"
        
        self.session_label.config(text=new_session_text)
        self.history_label.config(text=f"Historical Tracker | Total Encounters: {historical_total}")
        
        # Real-time incremental protection writing backups out on match update
        self.save_to_json()

    def run_action_on_change(self, ss: Image.Image) -> None:
        """
        Evaluates visual changes inside target capture frames and records new encounters.

        Uses a fast, synchronous OCR look-up mechanism to analyze canvas data, 
        extracting entities matching encounter definitions.

        Args:
            ss: Input image snapshot object source generated by native screen hooks.
        """
        result = winocr.recognize_pil_sync(ss, "en")
        text: str = result.get("text", "")

        if "Wild " not in text:
            self.current_poke = None
            return

        if self.current_poke is None:
            parts = text.split("Wild ")
            print(parts)
            if len(parts) > 1:
                poke_name: str = parts[1].split(" ")[0]
                
                # Check for localized multi-token edge strings (e.g., Nidoran variants)
                if poke_name == "Nidoran" and "Nidoran " in text:
                    sub_parts = text.split("Nidoran ")[1].split(" ")
                    if sub_parts:
                        poke_name = f"Nidoran {sub_parts[0]}"
                
            self.current_poke = poke_name
            selected_terrain: str = self.terrain_var.get() if self.terrain_var else ""

            df: pd.DataFrame = self.session_table.model.df
            terrain_df = df[df["Terrain"] == selected_terrain]
            valid_names = terrain_df["Pokemon"].tolist()

            # 1. Generate OCR Candidates
            parsing_map = {"l": "I", "I": "l", "n": "h", "h": "n", "e": "a", "a": "e"}
            candidates = {poke_name}
            for char_from, char_to in parsing_map.items():
                if char_from in poke_name:
                    candidates.add(poke_name.replace(char_from, char_to))

            matched_poke: str | None = None

            # TIER 1: Exact Match (Safe for similar names)
            for candidate in candidates:
                if candidate in valid_names:
                    matched_poke = candidate
                    break

            # TIER 2: Substring Match with Length Guardrail (Only runs if Tier 1 fails)
            if not matched_poke:
                # Sort candidates by length (descending) so longer names match first
                sorted_candidates = sorted(candidates, key=len, reverse=True)
                
                for candidate in sorted_candidates:
                    for official_name in valid_names:
                        # Check if candidate is in official_name AND lengths are close
                        if candidate.lower() in official_name.lower():
                            if abs(len(candidate) - len(official_name)) <= 3:
                                matched_poke = official_name
                                break
                    if matched_poke:
                        break

            # 3. Update table if a safe match was found
            if matched_poke:
                self.update_table(matched_poke, selected_terrain)
                print("updated")