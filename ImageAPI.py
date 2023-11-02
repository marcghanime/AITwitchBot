from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from models import Config
import io
import time

class ImageAPI:
    processor: BlipProcessor
    model: BlipForConditionalGeneration
    browser: webdriver.Chrome
    video_element: WebElement

    def __init__(self, config: Config):
        print("Initializing Image API...")
        
        # Set up the image captioning model
        self.processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        self.model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        
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
        self.browser.get("https://www.twitch.tv/" + config.twitch_channel)
        
        # Wait for the stream to load
        time.sleep(10)

        # Get the body element
        body = self.browser.find_element(by=By.TAG_NAME, value='body')

        # Unmute the stream
        body.send_keys('m')

        # Get the video element
        self.video_element = self.browser.find_element(by=By.TAG_NAME, value='video')

        print("Image API Initialized")


    # Generate caption for image
    def generate_caption(self, image: Image):
        inputs = self.processor(image, return_tensors="pt")
        out = self.model.generate(**inputs, max_length=64)
        description = self.processor.decode(out[0], skip_special_tokens=True)

        return description
    
    # Take screenshot of twitch stream
    def take_screenshot(self):       
        # Get the screenshot as bytes
        screenshot_bytes = io.BytesIO(self.video_element.screenshot_as_png)

        # Convert the bytes to an image object
        image = Image.open(screenshot_bytes).convert('RGB')

        return image
    
    # Close the browser
    def shutdown(self):
        self.browser.close()