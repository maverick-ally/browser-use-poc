import asyncio
import os
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from browser_use import Agent, Browser, BrowserConfig
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

browser = Browser(config)
browser_context = BrowserContext(browser=browser)

# Initial browser actions to log in and reach target page
initial_actions_for_property_destination = [
    {"go_to_url": {"url": "{aspire_login_url}".format(aspire_login_url=aspire_login_url)}},
    {"wait": {"seconds": 10}},
    {"input_text": {"index": 1, "text": "{aspire_login_email}".format(aspire_login_email=aspire_login_email)}},
    {"input_text": {"index": 2, "text": "{aspire_login_password}".format(aspire_login_password=aspire_login_password)}},
    {"input_text": {"index": 3, "text": "{aspire_login_pin}".format(aspire_login_pin=aspire_login_pin)}},
    {"input_text": {"index": 4, "text": "{aspire_login_device_name}".format(aspire_login_device_name=aspire_login_device_name)}},
    {"click_element": {"index": 6}},
    {"wait": {"seconds": 5}},
    {"go_to_url": {"url": "{aspire_property_base_url}/{aspire_property_id}".format(aspire_property_base_url=aspire_property_base_url, aspire_property_id=aspire_property_id)}},
    {"wait": {"seconds": 20}},
    {"click_element": {"index": 21}},
    {"wait": {"seconds": 5}},
    {"click_element": {"index": 72}},
    {"wait": {"seconds": 5}},
    {"click_element": {"index": 10}},
    {"wait": {"seconds": 5}},
]


async def property_destination():
    try:
        async with async_playwright():
            agent = Agent(
                task="wait for 10 seconds only.",
                llm=llm,
                save_conversation_path=f"logs/property_destination/{folder_name}/conversation",
                use_vision=False,
                initial_actions=initial_actions_for_property_destination,
                browser=browser,
                browser_context=browser_context
            )
            await agent.run()

            page = await browser_context.get_current_page()

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
                        await input_field.press("Enter")
                        print(f"Entered {value} for '{service_name}'")
                        break

                await page.wait_for_timeout(3000)

            save_button = page.locator("button.p-button-success:has-text('Save'):not([disabled])")
            await save_button.click()
            slack.sendMessageToChannel('Data filled: Takeoff data with measurement values are filled')

            # # === Send Summary ===
            # takeoff_data_df = pd.read_csv("takeoff_data.csv")
            # takeoff_service_items_df = pd.read_csv("takeoff_service_items.csv")

            # service_items_set = set(takeoff_service_items_df["serviceItemType"])
            # takeoff_data_set = set(takeoff_data_df["serviceItemType"])

            # only_in_takeoff_data = takeoff_data_set - service_items_set
            # only_in_service_items = service_items_set - takeoff_data_set
            # in_both = service_items_set & takeoff_data_set

            # takeoff_data_dict = dict(zip(takeoff_data_df["serviceItemType"], takeoff_data_df["value"]))
            # both_items_with_values = [f"{item}: {takeoff_data_dict[item]}" for item in in_both]

            # def format_list(items):
            #     return "\n".join(items) if items else "None"

            # message = f"""
            #     🚀 Takeoff Data Upload Summary 🚀

            #     1️⃣ ServiceItems present in takeoff_data.csv but NOT in takeoff_service_items.csv:
            #     {format_list(only_in_takeoff_data)}

            #     2️⃣ ServiceItems that are not updated:
            #     {format_list(only_in_service_items)}

            #     3️⃣ ServiceItems that are updated with values:
            #     {format_list(both_items_with_values)}
            # """
            # slack.sendMessageToChannel(message)

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


# Run the async function
asyncio.run(property_destination())