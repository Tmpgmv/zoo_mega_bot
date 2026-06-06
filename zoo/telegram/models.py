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
    order = models.IntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ['order']

class Animal(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название животного")
    photo = models.ImageField(upload_to='animals/', verbose_name="Фото животного")
    description = models.TextField(blank=True, verbose_name="Описание")

    class Meta:
        verbose_name = "Животное"
        verbose_name_plural = "Животные"

    def __str__(self):
        return self.name

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    text = models.CharField(max_length=200, verbose_name="Текст ответа")
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='answers',
                               verbose_name="Тотемное животное")
    points = models.IntegerField(default=1, verbose_name="Очки")

    class Meta:
        verbose_name = "Ответ"
        verbose_name_plural = "Ответы"

    def __str__(self):
        return f"{self.text} -> {self.animal.name}"


class UserSession(models.Model):
    user_id = models.BigIntegerField(verbose_name="ID пользователя")
    username = models.CharField(max_length=255, blank=True)
    current_question = models.IntegerField(default=0)
    answers = models.JSONField(default=dict)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user_id']
        verbose_name = "Сессия пользователя"
        verbose_name_plural = "Сессии пользователей"

    def __str__(self):
        return f"{self.username or self.user_id} - {'Завершен' if self.completed else 'В процессе'}"

