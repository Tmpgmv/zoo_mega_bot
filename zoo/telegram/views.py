import json

import requests
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from telegram.models import TelegramSettings
from zoo.secret import TELEGRAM_ACCESS_TOKEN


@method_decorator(csrf_exempt, name="dispatch")
class TelegramWebhookView(View):
    def post(self, request, *args, **kwargs):
        # Parse incoming payload
        data = json.loads(request.body.decode("utf-8"))

        # Safely extract message details
        message = data.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        user_text = message.get("text")

        # If it is a valid text message, reply
        if chat_id and user_text:
            payload = {
                "chat_id": chat_id,
                "text": f"You said: {user_text} (via CBV)"
            }
            url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/sendMessage"
            requests.post(url, json=payload)

        return HttpResponse("OK")



class HelpView(TemplateView):
    template_name = "telegram/webhook.html"

    def get_context_data(self, **kwargs):
        context = super(HelpView, self).get_context_data(**kwargs)
        context["BOT_TOKEN"] = TELEGRAM_ACCESS_TOKEN
        context["HTTPS_URL"] = TelegramSettings.objects.first().webhook_url
        return context