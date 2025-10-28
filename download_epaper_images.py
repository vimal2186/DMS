import requests
import os
import time
import shutil
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def download_epaper_images(base_url, start_page, end_page, output_dir):
    """
    Downloads e-paper images from a given base URL and page range using a headless Chrome browser.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Starting image download from {base_url} (pages {start_page} to {end_page}) using headless browser...")

    # Set up Chrome options for headless browsing
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    # Initialize WebDriver
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30) # Set page load timeout to 30 seconds

        for page_num in range(start_page, end_page + 1):
            page_url = f"{base_url.rsplit('/', 1)[0]}/page/{page_num}"
            
            try:
                print(f"  Navigating to {page_url}...")
                driver.get(page_url)
                
                # Wait for the main image to be present on the page
                # This XPath might need adjustment based on the actual structure of the e-paper site
                # Looking for an img tag with class 'img-fluid' or similar that is visible
                img_element = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//img[contains(@class, 'img-fluid') or contains(@class, 'page-image')]"))
                )
                
                image_url = img_element.get_attribute('src')

                if not image_url:
                    print(f"  Could not find image URL for page {page_num} at {page_url}. Skipping.")
                    continue

                if not image_url.startswith('http'):
                    # If it's a relative URL, construct the absolute URL
                    base_domain = "/".join(base_url.split('/')[:3])
                    image_url = f"{base_domain}{image_url}"

                print(f"  Found image URL for page {page_num}: {image_url}")

                # Download the image using requests, as selenium's direct download can be complex
                # Use the same headers as the browser to avoid 403 errors
                img_response = requests.get(image_url, stream=True, headers={'User-Agent': chrome_options.arguments[-1].split('=')[1]})
                img_response.raise_for_status()
                
                image_filename = f"page_{page_num}.jpg"
                image_path = os.path.join(output_dir, image_filename)
                
                with open(image_path, 'wb') as out_file:
                    shutil.copyfileobj(img_response.raw, out_file)
                print(f"  Downloaded {image_filename}")
                
                time.sleep(2) # Be polite to the server and allow time for next page load

            except Exception as e:
                print(f"  Error processing page {page_num} from {page_url}: {e}")
                # Attempt to take a screenshot on error for debugging
                error_screenshot_path = os.path.join(output_dir, f"error_page_{page_num}.png")
                driver.save_screenshot(error_screenshot_path)
                print(f"  Screenshot saved to {error_screenshot_path}")
                continue

    except Exception as e:
        print(f"  An error occurred during WebDriver initialization or main loop: {e}")
    finally:
        if driver:
            driver.quit()
            print("Headless browser closed.")

    print("Image download complete.")

if __name__ == "__main__":
    base_epaper_url = "https://epaper.vijayavani.net/edition/Bengaluru/VVAANINEW_BEN/VVAANINEW_BEN_20250917"
    start_page_num = 2
    end_page_num = 20
    output_directory = "kannada_training_data/images"
    
    download_epaper_images(base_epaper_url, start_page_num, end_page_num, output_directory)
