from django.core.management.base import BaseCommand
from telegram.models import Question, Answer, Animal


class Command(BaseCommand):
    help = 'Initialize quiz questions, answers and animals'

    def handle(self, *args, **options):
        # Очищаем старые данные
        Question.objects.all().delete()
        Animal.objects.all().delete()

        # Создаем животных
        wolf = Animal.objects.create(
            name="Волк",
            photo="animals/wolf.jpg",
            description="Волк - символ свободы, независимости и верности стае."
        )

        eagle = Animal.objects.create(
            name="Орел",
            photo="animals/eagle.jpg",
            description="Орел - символ власти, свободы и духовного видения."
        )

        lion = Animal.objects.create(
            name="Лев",
            photo="animals/lion.jpg",
            description="Лев - символ силы, мужества и лидерства."
        )

        owl = Animal.objects.create(
            name="Сова",
            photo="animals/owl.jpg",
            description="Сова - символ мудрости, знаний и интуиции."
        )

        bear = Animal.objects.create(
            name="Медведь",
            photo="animals/bear.jpg",
            description="Медведь - символ силы, защиты и внутренней гармонии."
        )

        dolphin = Animal.objects.create(
            name="Дельфин",
            photo="animals/dolphin.jpg",
            description="Дельфин - символ дружбы, радости и свободы."
        )

        # Вопрос 1
        q1 = Question.objects.create(text="Какое время суток вам ближе?", order=1)
        Answer.objects.create(question=q1, text="🌅 Утро", animal=eagle, points=1)
        Answer.objects.create(question=q1, text="☀️ День", animal=lion, points=2)
        Answer.objects.create(question=q1, text="🌆 Вечер", animal=wolf, points=3)
        Answer.objects.create(question=q1, text="🌙 Ночь", animal=owl, points=4)

        # Вопрос 2
        q2 = Question.objects.create(text="Что вы цените в людях больше всего?", order=2)
        Answer.objects.create(question=q2, text="🤝 Честность и верность", animal=wolf, points=1)
        Answer.objects.create(question=q2, text="💪 Силу и решительность", animal=lion, points=2)
        Answer.objects.create(question=q2, text="📚 Мудрость и знания", animal=owl, points=3)
        Answer.objects.create(question=q2, text="🕊️ Свободу и независимость", animal=eagle, points=4)

        # Вопрос 3
        q3 = Question.objects.create(text="Какая стихия вам ближе?", order=3)
        Answer.objects.create(question=q3, text="🌍 Земля", animal=bear, points=1)
        Answer.objects.create(question=q3, text="💨 Воздух", animal=eagle, points=2)
        Answer.objects.create(question=q3, text="🔥 Огонь", animal=lion, points=3)
        Answer.objects.create(question=q3, text="💧 Вода", animal=dolphin, points=4)

        # Вопрос 4
        q4 = Question.objects.create(text="Какое место вы бы выбрали для отдыха?", order=4)
        Answer.objects.create(question=q4, text="🏔️ Горы", animal=eagle, points=1)
        Answer.objects.create(question=q4, text="🌲 Лес", animal=bear, points=2)
        Answer.objects.create(question=q4, text="🌊 Океан", animal=dolphin, points=3)
        Answer.objects.create(question=q4, text="🏜️ Пустыня", animal=lion, points=4)

        self.stdout.write(self.style.SUCCESS('Quiz initialized successfully with animals!'))
        self.stdout.write(f'Created {Animal.objects.count()} animals')
        self.stdout.write(f'Created {Question.objects.count()} questions')
        self.stdout.write(f'Created {Answer.objects.count()} answers')