from django.contrib import admin

from telegram.models import TelegramSettings, Question, Answer, Photo, AboutZoo


class TelegramSettingsAdmin(admin.ModelAdmin):
    exclude = []


admin.site.register(TelegramSettings, TelegramSettingsAdmin)


class QuestionAdmin(admin.ModelAdmin):
    exclude = []


admin.site.register(Question, QuestionAdmin)


class AnswerAdmin(admin.ModelAdmin):
    exclude = []


admin.site.register(Answer, AnswerAdmin)


class PhotoAdmin(admin.ModelAdmin):
    exclude = []


admin.site.register(Photo, PhotoAdmin)


class AboutZooAdmin(admin.ModelAdmin):
    exclude = []


admin.site.register(AboutZoo, AboutZooAdmin)