from decimal import Decimal

from django.core.validators import FileExtensionValidator, RegexValidator, MinValueValidator
from django.db import models
from solo.models import SingletonModel


class TelegramSettings(SingletonModel):
    webhook_url = models.URLField()

    def __str__(self):
        return "Telegram Configuration"

    class Meta:
        verbose_name = "Опции"
        verbose_name_plural = "Опции"


class Question(models.Model):
    text = models.CharField(max_length=500, verbose_name="Текст вопроса")
    order = models.IntegerField(default=0, verbose_name="Порядок")

    def __str__(self):
        return f"{self.text}"

    class Meta:
        ordering = ['order']
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"


class Animal(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название животного")
    photo = models.ImageField(upload_to='animals/', verbose_name="Фото животного")
    description = models.TextField(blank=True, verbose_name="Описание")
    emoji = models.CharField(max_length=1000, blank=True, default="", verbose_name="Емодзи")

    class Meta:
        verbose_name = "Животное"
        verbose_name_plural = "Животные"

    def __str__(self):
        return self.name


class Answer(models.Model):
    points = models.IntegerField(
        choices=[
            (0, 'Совсем не подходит'),
            (1, 'Слабо подходит'),
            (2, 'Частично подходит'),
            (3, 'Хорошо подходит'),
            (4, 'Идеально подходит'),
        ],
        default=1,
        verbose_name="Степень соответствия")
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

    class Meta:
        verbose_name = "Сессия"
        verbose_name_plural = "Сессии"


class Photo(models.Model):
    photo = models.ImageField(upload_to='photos/',
                              validators=[FileExtensionValidator(['jpg', 'png', 'webp', ])],
                              verbose_name="Изображение")
    caption = models.CharField(max_length=100, default="", blank=True, )

    archived = models.BooleanField(default=False)

    def __str__(self):
        return self.caption

    class Meta:
        verbose_name = "Изображение"
        verbose_name_plural = "Изображения"


class AboutZoo(SingletonModel):
    description = models.TextField(verbose_name="Описание", default="")
    advantages = models.TextField(verbose_name="Преимущества", default="")
    email = models.EmailField(verbose_name="Емейл")
    phone = models.CharField(
        verbose_name="Телефон",
        max_length=11,
        validators=[
            RegexValidator(
                regex=r'^\d{11}$',
                message='Телефон должен содержать ровно 11 цифр без пробелов и знаков',
                code='invalid_phone'
            )
        ],
        help_text="Введите ровно 11 цифр (например: 79123456789)"
    )

    adult_price = models.DecimalField(max_digits=10,
                                      decimal_places=2,
                                      validators=[MinValueValidator(Decimal('0.1'))],
                                      verbose_name="Цена взрослого билета",
                                      default=0)
    reduced_price = models.DecimalField(max_digits=10,
                                        decimal_places=2,
                                        validators=[MinValueValidator(Decimal('0.1'))],
                                        verbose_name="Цена льготного билета",
                                        default=0)

    def get_phone(self):
        return f"+{self.phone[0]}-{self.phone[1:4]}-{self.phone[4:7]}-{self.phone[7:9]}-{self.phone[9:]}"

    def __str__(self):
        return f"Описание зоопарка"

    class Meta:
        verbose_name = "О зоопарке"
        verbose_name_plural = "О зоопарке"


class GuardianProgram(SingletonModel):
    description = models.TextField(verbose_name="Описание", default="")

    def __str__(self):
        return f"Программа опеки"

    class Meta:
        verbose_name = "Программа опеки"
        verbose_name_plural = "Программа опеки"


class Feedback(models.Model):
    RATING_CHOICES = [
        (5, '⭐ Отлично'),
        (4, '👍 Хорошо'),
        (3, '😐 Нормально'),
        (2, '😕 Плохо'),
        (1, '👎 Ужасно'),
    ]

    user_id = models.BigIntegerField(verbose_name="ID пользователя")
    username = models.CharField(max_length=255, blank=True, verbose_name="Имя пользователя")
    rating = models.IntegerField(choices=RATING_CHOICES, verbose_name="Оценка")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    def __str__(self):
        return f"Отзыв от {self.username or self.user_id} - {self.get_rating_display()}"

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ['-created_at']
