from django.contrib import admin

from telegram.models import TelegramSettings


class TelegramSettingsAdmin(admin.ModelAdmin):
    exclude = []


admin.site.register(TelegramSettings, TelegramSettingsAdmin)
