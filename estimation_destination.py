import os
import asyncio

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pathlib import Path

from browser_use import Agent, Controller
from browser_use.agent.views import ActionResult
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import BrowserContext

# Load environment variables
load_dotenv()

# Initialize controller and browser
browser = Browser(
    config=BrowserConfig(
        headless=True,
        disable_security=True,
    )
)

browser_context = BrowserContext(browser=browser)

controller = Controller()

file_name = "aspire_upload_sample.xlsx"
base_dir = Path(__file__).resolve().parent

# Recursively find the file
file_path = next(base_dir.rglob(file_name), None)

available_file_paths = [str(file_path)]
print(available_file_paths)

# variables
aspire_login_url = os.getenv('ASPIRE_LOGIN_URL')
aspire_login_email = os.getenv('ASPIRE_LOGIN_EMAIL')
aspire_login_password = os.getenv('ASPIRE_LOGIN_PASSWORD')
aspire_login_pin = os.getenv('ASPIRE_LOGIN_PIN')
aspire_login_device_name = os.getenv('ASPIRE_LOGIN_DEVICE_NAME')
aspire_estimation_id = os.getenv('ASPIRE_ESTIMATION_ID')
aspire_estimation_base_url = os.getenv('ASPIRE_ESTIMATION_BASE_URL')

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


async def main():
    try:
        task = """
            1. Click on the first ellipsis button and wait for 3 seconds.
            2. Select the Import option and wait for 3 seconds.
            3. Use selector 'input[type="file"]' to upload the file.
            4. Click on the Import button and wait for 10 seconds.
        """

        model = ChatOpenAI(model='gpt-4o')
        agent = Agent(
            task=task,
            llm=model,
            controller=controller,
            browser=browser,
            browser_context=browser_context,
            available_file_paths=available_file_paths,
            initial_actions=initial_actions_for_estimation_destination,
        )

        await agent.run()
    
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
    asyncio.run(main())