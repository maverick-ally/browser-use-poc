import asyncio
import os
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
from playwright.async_api import async_playwright

from browser_use import Agent, Browser, BrowserConfig, BrowserContextConfig, Controller
from browser_use.agent.views import ActionResult
from browser_use.agent.service import BrowserContext
from langchain_openai import ChatOpenAI
from portkey_ai import createHeaders, PORTKEY_GATEWAY_URL
from slack import Slack

# Load environment variables
load_dotenv()

# Initialize Slack instance
s = Slack()

# Timestamp and folder for logs
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
folder_name = f"logs-{timestamp}"
log_file = f"api_logs_{timestamp}.txt"

# Load Portkey headers for LLM
portkey_headers = createHeaders(
    api_key=os.getenv('PORT_KEY_API'),
    virtual_key=os.getenv('PORT_KEY_VIRTUAL_KEY')
)

llm = ChatOpenAI(
    model=os.getenv('OPENAI_LLM_MODEL'),
    api_key="",
    base_url=PORTKEY_GATEWAY_URL,
    default_headers=portkey_headers
)

# variables
aspire_login_url = os.getenv('ASPIRE_LOGIN_URL')
aspire_login_email = os.getenv('ASPIRE_LOGIN_EMAIL')
aspire_login_password = os.getenv('ASPIRE_LOGIN_PASSWORD')
aspire_login_pin = os.getenv('ASPIRE_LOGIN_PIN')
aspire_login_device_name = os.getenv('ASPIRE_LOGIN_DEVICE_NAME')
aspire_estimation_id = os.getenv('ASPIRE_ESTIMATION_ID')
aspire_estimation_base_url = os.getenv('ASPIRE_ESTIMATION_BASE_URL')

file_name = "aspire_upload_example.xlsx"
base_dir = Path(__file__).resolve().parent

# Recursively find the file
file_path = next(base_dir.rglob(file_name), None)

available_file_paths = [str(file_path)]

# Configure browser with stealth options
config = BrowserConfig(
    headless=True,  # Run in headless mode (can be False for debugging)
    disable_security=True,
    extra_chromium_args=[
        "--disable-blink-features=AutomationControlled", # Removes navigator.webdriver = true
    ]
)

# Define a realistic and modern user-agent
realistic_user_agent = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)

# Context configuration to spoof headers
context_config = BrowserContextConfig(
    user_agent=realistic_user_agent,
)

browser = Browser(config)
browser_context = BrowserContext(browser=browser, config=context_config)

controller = Controller()

# Initial browser actions to log in and reach target page
initial_actions_for_estimation_destination = [
    {"go_to_url": {"url": "{aspire_login_url}".format(aspire_login_url=aspire_login_url)}},
    {"wait": {"seconds": 10}},
    {"input_text": {"index": 1, "text": "{aspire_login_email}".format(aspire_login_email=aspire_login_email)}},
    {"input_text": {"index": 2, "text": "{aspire_login_password}".format(aspire_login_password=aspire_login_password)}},
    {"input_text": {"index": 3, "text": "{aspire_login_pin}".format(aspire_login_pin=aspire_login_pin)}},
    {"input_text": {"index": 4, "text": "{aspire_login_device_name}".format(aspire_login_device_name=aspire_login_device_name)}},
    {"click_element": {"index": 6}},
    {"wait": {"seconds": 10}},
    {"go_to_url": {"url": "{aspire_estimation_base_url}/{aspire_estimation_id}".format(aspire_estimation_base_url=aspire_estimation_base_url, aspire_estimation_id=aspire_estimation_id)}},
    {"wait": {"seconds": 20}},
]


@controller.action('Upload file directly via selector')
async def upload_file_directly(selector: str, path: str, browser: BrowserContext, available_file_paths: list[str]):
    if path not in available_file_paths:
        return ActionResult(error=f'File path {path} is not in available_file_paths')
    if not os.path.exists(path):
        return ActionResult(error=f'File {path} does not exist')

    page = await browser.get_current_page()

    try:
        file_input = page.locator(selector).first
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.evaluate("el => { el.style.display = 'block'; el.style.visibility = 'visible'; }")
        await file_input.set_input_files(path)

        msg = f"✅ Successfully uploaded file using selector '{selector}'"
        return ActionResult(extracted_content=msg, include_in_memory=True)

    except Exception as e:
        msg = f"❌ Failed to upload file with selector '{selector}': {str(e)}"
        return ActionResult(error=msg)

# === Logging Functions ===
async def log_request_headers(request):
    try:
        with open(log_file, "a") as f:
            f.write(f"\n🔹 [API] {request.method} {request.url}\n")
            f.write("Headers:\n")
            for k, v in request.headers.items():
                f.write(f"  {k}: {v}\n")
            if request.method in ["POST", "PUT", "PATCH", "GET"]:
                try:
                    post_data = request.post_data
                    if post_data:
                        f.write("\nBody:\n")
                        f.write(f"{post_data}\n")
                except Exception as e:
                    f.write(f"\n⚠️ Failed to get request body: {e}\n")
    except Exception as e:
        print(f"⚠️ Request log error: {e}")

async def log_response_headers(response):
    try:
        headers = await response.all_headers()
        content_type = headers.get("content-type", "")
        status = response.status
        url = response.url

        with open(log_file, "a") as f:
            f.write(f"\nResponse [{status}] for {url}\n")
            f.write("Headers:\n")
            for k, v in headers.items():
                f.write(f"  {k}: {v}\n")
            if "application/json" in content_type:
                try:
                    body = await response.body()
                    decoded = body.decode("utf-8", errors="ignore")
                    f.write("\nResponse Body:\n")
                    f.write(f"{decoded}\n")
                except Exception as e:
                    f.write(f"\n⚠️ Failed to decode JSON body: {e}\n")
    except Exception as e:
        print(f"⚠️ Response log error: {e}")

async def estimation_destination():
    try:
        async with async_playwright():

            page = await browser_context.get_current_page()

            # Patch headers right after page is created
            await page.set_extra_http_headers({
                "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            })

            # Attach stealth anti-detection patches
            await page.add_init_script("""
                // Hide webdriver
                Object.defineProperty(navigator, 'webdriver', { get: () => false });

                // Spoof browser environment
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """)

            # Attach logging before any actions
            page.on("request", lambda request: asyncio.create_task(log_request_headers(request)))
            page.on("response", lambda response: asyncio.create_task(log_response_headers(response)))

            task = """
                1. Click on the first ellipsis button and wait for 3 seconds.
                2. Select the Import option and wait for 3 seconds.
                3. Use selector 'input[type="file"]' to upload the file.
                4. Click on the Import button and wait for 10 seconds.
            """

            agent = Agent(
                task=task,
                llm=llm,
                controller=controller,
                browser=browser,
                browser_context=browser_context,
                available_file_paths=available_file_paths,
                initial_actions=initial_actions_for_estimation_destination,
            )

            s.sendMessageToChannel("Preparing the excel file for estimation destination.")
            await agent.run()
            s.sendMessageToChannel("File has been uploaded successfully.")
    
    except Exception as e:
        print(f"❌ Error occurred: {e}")

    finally:
        if browser:
            try:
                await browser_context.close()
                await browser.close()
                print("✅ Browser closed successfully.")
            except Exception as close_error:
                print(f"⚠️ Warning: Failed to close the browser - {close_error}")


if __name__ == '__main__':
    asyncio.run(estimation_destination())