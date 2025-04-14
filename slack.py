import os
import requests

from dotenv import load_dotenv

load_dotenv()

class Slack:

    def __init__(self):
        self.token = os.getenv('SLACK_TOKEN')
        self.channel = os.getenv('SLACK_CHANNEL')
        self.slack_post_message_url = os.getenv('SLACK_POST_MESSAGE_URL')
    
    def sendMessageToChannel(self, message):

        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {"channel": self.channel, "text": message}

        response = requests.post(self.slack_post_message_url, headers=headers, json=payload)

        if response.status_code == 200 and response.json().get("ok"):
            print("Message sent successfully!")
        else:
            print(f"Failed to send message: {response.text}")