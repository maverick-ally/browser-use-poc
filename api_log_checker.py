import asyncio
import os
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from browser_use import Agent, Browser, BrowserConfig, BrowserContextConfig
from browser_use.agent.service import BrowserContext
from langchain_openai import ChatOpenAI
from portkey_ai import createHeaders, PORTKEY_GATEWAY_URL
from slack import Slack

# Load environment variables
load_dotenv()

# Initialize Slack instance
slack = Slack()

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
aspire_property_id = os.getenv('ASPIRE_PROPERTY_ID')
aspire_property_base_url = os.getenv('ASPIRE_PROPERTY_BASE_URL')

# Configure browser
config = BrowserConfig(
    headless=True,
    disable_security=True,
)

context_config = BrowserContextConfig(
    
)

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

# === Main automation ===
async def property_destination():
    try:
        async with async_playwright() as playwright:
            browser = Browser(config)
            browser_context = BrowserContext(browser=browser, config=context_config)
            page = await browser_context.get_current_page()

            # Attach logging before any actions
            page.on("request", lambda request: asyncio.create_task(log_request_headers(request)))
            page.on("response", lambda response: asyncio.create_task(log_response_headers(response)))

            # Create and run Agent with this browser + context
            agent = Agent(
                task="Extract and fill takeoff data",
                llm=llm,
                save_conversation_path=f"logs/property_destination/{folder_name}/conversation",
                use_vision=False,
                initial_actions=[
                    {"go_to_url": {"url": aspire_login_url}},
                    {"wait": {"seconds": 10}},
                    {"input_text": {"index": 1, "text": aspire_login_email}},
                    {"input_text": {"index": 2, "text": aspire_login_password}},
                    {"input_text": {"index": 3, "text": aspire_login_pin}},
                    {"input_text": {"index": 4, "text": aspire_login_device_name}},
                    {"click_element": {"index": 6}},
                    {"wait": {"seconds": 5}},
                    {"go_to_url": {"url": f"{aspire_property_base_url}/{aspire_property_id}"}},
                    {"wait": {"seconds": 20}},
                    {"click_element": {"index": 21}},
                    {"wait": {"seconds": 5}},
                    {"click_element": {"index": 72}},
                    {"wait": {"seconds": 5}},
                    {"click_element": {"index": 10}},
                    {"wait": {"seconds": 5}},
                ],
                browser=browser,
                browser_context=browser_context
            )
            await agent.run()

            # === Extract Service Items ===
            slack.sendMessageToChannel('Extracting: Takeoff data with Service Items and Measurements')

            rows = await page.locator("tr.ng-star-inserted").all()
            data = []
            current_parent = None

            for row in rows:
                cells = row.locator("td")
                service_item = (await cells.nth(0).text_content() or "").strip()
                measurement = (await cells.nth(1).text_content() or "").strip()

                toggler_btn = row.locator('button.p-treetable-toggler')
                style = await toggler_btn.get_attribute("style") if await toggler_btn.count() > 0 else ""

                if "margin-left: 0px" in style:
                    current_parent = service_item
                elif "margin-left:" in style and current_parent:
                    data.append({
                        "serviceType": current_parent,
                        "serviceItemType": service_item,
                        "measurement": measurement
                    })

            df = pd.DataFrame(data)
            df.to_csv("takeoff_service_items.csv", index=False)
            print("✅ Data saved to takeoff_service_items.csv")
            slack.sendMessageToChannel('Extracted: Takeoff data with Service Items and Measurements')

            # === Fill Data ===
            df = pd.read_csv('takeoff_data.csv')
            slack.sendMessageToChannel('Data filling: Takeoff data with measurement values are filling...')

            for _, item in df.iterrows():
                service_name = item["serviceItemType"]
                value = str(item["value"])

                print(f"Processing: {service_name} -> {value}")
                row = page.locator("tr.ng-star-inserted").filter(has_text=service_name)
                input_fields = await row.locator("input.e-control.e-numerictextbox").all()

                for input_field in input_fields:
                    if await input_field.is_visible():
                        await input_field.clear()
                        await input_field.fill(value)
                        await input_field.press("Tab")
                        print(f"Entered {value} for '{service_name}'")
                        break

                await page.wait_for_timeout(3000)

            save_button = page.locator("button.p-button-success:has-text('Save'):not([disabled])")
            await save_button.click()
            await page.wait_for_timeout(3000)
            slack.sendMessageToChannel('Data filled: Takeoff data with measurement values are filled')

            await browser_context.close()
            await browser.close()
            print("✅ Browser closed successfully.")

    except Exception as e:
        print(f"❌ Error occurred: {e}")


# Run the async function
asyncio.run(property_destination())
