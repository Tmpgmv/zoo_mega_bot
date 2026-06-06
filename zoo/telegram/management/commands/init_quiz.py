from django.core.management.base import BaseCommand
from telegram.models import Question, Answer


class Command(BaseCommand):
    help = 'Initialize quiz questions and answers'

    def handle(self, *args, **options):
        # Очищаем старые данные
        Question.objects.all().delete()

        # Вопрос 1
        q1 = Question.objects.create(text="Какое время суток вам ближе?", order=1)
        Answer.objects.create(question=q1, text="Утро", animal="Орел", points=1)
        Answer.objects.create(question=q1, text="День", animal="Лев", points=2)
        Answer.objects.create(question=q1, text="Вечер", animal="Волк", points=3)
        Answer.objects.create(question=q1, text="Ночь", animal="Сова", points=4)

        # Вопрос 2
        q2 = Question.objects.create(text="Что вы цените в людях больше всего?", order=2)
        Answer.objects.create(question=q2, text="Честность", animal="Волк", points=1)
        Answer.objects.create(question=q2, text="Силу", animal="Лев", points=2)
        Answer.objects.create(question=q2, text="Мудрость", animal="Сова", points=3)
        Answer.objects.create(question=q2, text="Свободу", animal="Орел", points=4)

        # Вопрос 3
        q3 = Question.objects.create(text="Какая стихия вам ближе?", order=3)
        Answer.objects.create(question=q3, text="Земля", animal="Медведь", points=1)
        Answer.objects.create(question=q3, text="Воздух", animal="Орел", points=2)
        Answer.objects.create(question=q3, text="Огонь", animal="Лев", points=3)
        Answer.objects.create(question=q3, text="Вода", animal="Дельфин", points=4)

        self.stdout.write(self.style.SUCCESS('Quiz initialized successfully'))