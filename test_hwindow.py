import win32gui
import win32ui
from PIL import Image
from ctypes import windll

def get_minimized_window_screenshot(window_title):
    """
    Takes a screenshot of a minimized window given its title.
    """
    hwnd = win32gui.FindWindow(None, window_title)
    if not hwnd:
        print(f"Window '{window_title}' not found.")
        return None

    # Get the window dimensions
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top

    # Create a device context for the window
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    # Create a bitmap to store the screenshot
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)

    # Select the bitmap into the device context
    saveDC.SelectObject(saveBitMap)

    # Copy the window's content to the bitmap
    # Note: PrintWindow is often more reliable for minimized/hidden windows
    windll.user32.PrintWindow(hwnd, saveDC.GetHandleAttrib(), 0)

    # Convert the bitmap to a PIL Image
    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)
    img = Image.frombuffer(
        'RGB',
        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
        bmpstr, 'raw', 'BGRX', 0, 1
    )

    # Clean up resources
    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    return img

# Example usage:
if __name__ == "__main__":
    # Replace 'Untitled - Notepad' with the actual title of your minimized window
    window_name = "PROClient" 
    screenshot = get_minimized_window_screenshot(window_name)

    if screenshot:
        screenshot.save(f"{window_name}_minimized_screenshot.png")
        print(f"Screenshot saved for '{window_name}'.")
    else:
        print(f"Failed to capture screenshot for '{window_name}'.")