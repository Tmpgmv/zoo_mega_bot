from django.contrib import admin

from telegram.models import TelegramSettings, Question, Answer, Photo, AboutZoo, GuardianProgram, Animal, Feedback


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
    list_display = ["pk", "caption", ]


admin.site.register(Photo, PhotoAdmin)


class AboutZooAdmin(admin.ModelAdmin):
    exclude = []


admin.site.register(AboutZoo, AboutZooAdmin)


class GuardianProgramAdmin(admin.ModelAdmin):
    exclude = []


admin.site.register(GuardianProgram, GuardianProgramAdmin)


class AnimalAdmin(admin.ModelAdmin):
    exclude = []
    list_display = ["pk", "name", "emoji"]


admin.site.register(Animal, AnimalAdmin)


class FeedbackAdmin(admin.ModelAdmin):
    exclude = []


admin.site.register(Feedback, FeedbackAdmin)
