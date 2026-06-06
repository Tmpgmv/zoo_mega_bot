from django.core.validators import FileExtensionValidator
from django.db import models
from solo.models import SingletonModel


class TelegramSettings(SingletonModel):
    webhook_url = models.URLField()

    def __str__(self):
        return "Telegram Configuration"

    class Meta:
        verbose_name = "Telegram Configuration"


class Question(models.Model):
    text = models.CharField(max_length=500, verbose_name="Текст вопроса")
    image = models.ImageField(upload_to='questions/', blank=True, null=True, verbose_name="Изображение")
    order = models.IntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ['order']


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    text = models.CharField(max_length=200, verbose_name="Текст ответа")
    animal = models.CharField(max_length=100, verbose_name="Тотемное животное")
    points = models.IntegerField(default=0, verbose_name="Очки")

    def __str__(self):
        return f"{self.text} -> {self.animal}"


class UserSession(models.Model):
    user_id = models.BigIntegerField(verbose_name="ID пользователя")
    username = models.CharField(max_length=255, blank=True)
    current_question = models.IntegerField(default=0)
    answers = models.JSONField(default=dict)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user_id']