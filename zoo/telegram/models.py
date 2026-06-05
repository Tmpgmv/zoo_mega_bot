from django.core.validators import FileExtensionValidator
from django.db import models

class TelegramSettings(models.Model):
    webhook_url = models.URLField()
    logo = models.ImageField(validators=[FileExtensionValidator(['png', ])])

    def __str__(self):
        return self.webhook_url
