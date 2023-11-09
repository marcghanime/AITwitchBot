from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
import base64

from models import Config
import io
import time

class ImageAPI:
    browser: webdriver.Chrome
    video_element: WebElement

    def __init__(self, config: Config):
        print("Initializing Image API...")
        
        # Set up the browser
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        self.browser = webdriver.Chrome(options=chrome_options)

        # Maximize the browser window
        self.browser.set_window_size(1920, 1080)
        self.browser.maximize_window()

        # Navigate to the Twitch stream
        self.browser.get("https://www.twitch.tv/" + config.target_channel)
        
        # Wait for the stream to load
        time.sleep(10)

        # Get the body element
        body = self.browser.find_element(by=By.TAG_NAME, value='body')

        # Unmute the stream
        body.send_keys('m')

        # Get the video element
        self.video_element = self.browser.find_element(by=By.TAG_NAME, value='video')

        print("Image API Initialized")
    
    # Take screenshot of twitch stream
    def take_screenshot(self):       
        # Get the screenshot as bytes
        screenshot_bytes = io.BytesIO(self.video_element.screenshot_as_png)

        # Convert the bytes to an image object
        image = Image.open(screenshot_bytes).convert('RGB')

        return image
    
    # Get the screenshot as a base64 string
    def get_base64_screenshot(self):
        image = self.take_screenshot()
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    # Close the browser
    def shutdown(self):
        self.browser.close()