from django.db import models

class TelegramSettings(models.Model):
    webhook_url = models.URLField()
    logo = models.FileField()

    def __str__(self):
        return self.webhook_url
