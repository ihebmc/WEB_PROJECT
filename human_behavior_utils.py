# human_behavior_utils.py

import random
import time
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def random_sleep(min_time=1.0, max_time=3.0):
    """Add random delay between actions"""
    time.sleep(random.uniform(min_time, max_time))


def human_like_scroll(driver, scroll_pause=1.0):
    """Perform human-like scrolling with random pauses"""
    total_height = driver.execute_script("return document.body.scrollHeight")
    viewport_height = driver.execute_script("return window.innerHeight")
    current_position = 0

    while current_position < total_height:
        # Random scroll amount between 100 and 400 pixels
        scroll_amount = random.randint(100, 400)
        current_position += scroll_amount

        # Scroll with easing effect
        driver.execute_script(f"""
            window.scrollTo({{
                top: {current_position},
                behavior: 'smooth'
            }});
        """)

        # Random pause between scrolls
        random_sleep(0.5, scroll_pause)

        # Occasionally scroll back up a little
        if random.random() < 0.2:  # 20% chance
            current_position -= random.randint(50, 100)
            driver.execute_script(f"window.scrollTo(0, {current_position})")
            random_sleep(0.3, 0.7)


def move_mouse_randomly(driver, element=None):
    """Move mouse in a human-like pattern"""
    action = ActionChains(driver)

    if element:
        # Move to element with random offset
        offset_x = random.randint(-10, 10)
        offset_y = random.randint(-10, 10)
        action.move_to_element_with_offset(element, offset_x, offset_y)
    else:
        # Move to random position on page
        viewport_width = driver.execute_script("return window.innerWidth")
        viewport_height = driver.execute_script("return window.innerHeight")
        random_x = random.randint(0, viewport_width)
        random_y = random.randint(0, viewport_height)
        action.move_by_offset(random_x, random_y)

    action.perform()
    random_sleep(0.1, 0.3)


def bypass_cloudflare(driver, timeout=30):
    """Wait for and bypass Cloudflare protection"""
    try:
        # Wait for Cloudflare check to complete
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Check for common Cloudflare elements
        cloudflare_elements = driver.find_elements(By.CSS_SELECTOR,
                                                   "#challenge-running, #challenge-stage, #cf-challenge-running"
                                                   )

        if cloudflare_elements:
            print("Detected Cloudflare challenge, waiting...")
            # Add random mouse movements
            move_mouse_randomly(driver)
            # Wait for challenge to disappear
            WebDriverWait(driver, timeout).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                                                "#challenge-running, #challenge-stage, #cf-challenge-running"))
            )

        random_sleep(2, 4)  # Additional wait after bypass
        return True

    except Exception as e:
        print(f"Error bypassing Cloudflare: {str(e)}")
        return False


def simulate_human_interaction(driver):
    """Simulate various human-like interactions on the page"""
    try:
        # Random mouse movements
        move_mouse_randomly(driver)

        # Occasionally highlight text
        if random.random() < 0.3:  # 30% chance
            elements = driver.find_elements(By.CSS_SELECTOR, "p, h1, h2, h3")
            if elements:
                element = random.choice(elements)
                move_mouse_randomly(driver, element)
                ActionChains(driver).click_and_hold(element).perform()
                random_sleep(0.2, 0.5)
                ActionChains(driver).release().perform()

        # Random tab pressing
        if random.random() < 0.2:  # 20% chance
            ActionChains(driver).send_keys('\t' * random.randint(1, 3)).perform()
            random_sleep(0.3, 0.6)

    except Exception as e:
        print(f"Error in human interaction simulation: {str(e)}")