import json
import os

import requests
from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from telegram.models import Animal, Answer, Question, TelegramSettings, UserSession
from zoo.secret import TELEGRAM_ACCESS_TOKEN


class HelpView(TemplateView):
    template_name = "telegram/webhook.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["BOT_TOKEN"] = TELEGRAM_ACCESS_TOKEN
        context["HTTPS_URL"] = TelegramSettings.objects.first().webhook_url
        return context





class TelegramBot:
    """Класс-утилита для работы с Telegram API"""

    @staticmethod
    def send_message(chat_id, text, reply_markup=None):
        url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        try:
            response = requests.post(url, json=data, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Error sending message: {e}")
            return None

    @staticmethod
    def send_photo(chat_id, photo_path, caption=None, reply_markup=None):
        """Отправка фото с подписью и клавиатурой"""
        url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/sendPhoto"
        try:
            # Проверяем существование файла
            if not os.path.exists(photo_path):
                print(f"Photo not found: {photo_path}")
                # Если фото нет, отправляем просто текст
                return TelegramBot.send_message(chat_id, caption, reply_markup)

            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                data = {'chat_id': chat_id}
                if caption:
                    data['caption'] = caption
                    data['parse_mode'] = 'HTML'
                if reply_markup:
                    data['reply_markup'] = json.dumps(reply_markup)
                response = requests.post(url, files=files, data=data, timeout=10)
                return response.json()
        except Exception as e:
            print(f"Error sending photo: {e}")
            # В случае ошибки отправляем текст
            return TelegramBot.send_message(chat_id, caption, reply_markup)

    @staticmethod
    def answer_callback(callback_id):
        url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/answerCallbackQuery"
        try:
            response = requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
            return response.json()
        except Exception as e:
            print(f"Error answering callback: {e}")
            return None


class QuizSession:
    """Класс для управления сессией теста"""

    def __init__(self, user_id, username=None):
        self.user_id = user_id
        self.session, self.created = UserSession.objects.get_or_create(
            user_id=user_id,
            defaults={'username': username or ''}
        )

    def calculate_result_advanced(self):
        """Расширенный подсчет результатов с топ-3 животными"""
        answers_data = self.session.answers or {}
        animal_scores = {}
        animal_details = {}

        for answer_id in answers_data.values():
            try:
                answer = Answer.objects.select_related('animal').get(id=int(answer_id))
                animal = answer.animal

                animal_scores[animal.name] = animal_scores.get(animal.name, 0) + answer.points
                animal_details[animal.name] = animal

            except (Answer.DoesNotExist, ValueError):
                continue

        if not animal_scores:
            return None

        # Сортируем животных по очкам
        sorted_animals = sorted(
            animal_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Топ-3 животных (дополняем до 3 если нужно)
        top_animals = sorted_animals[:3]
        while len(top_animals) < 3:
            top_animals.append((None, 0))

        return {
            'primary': top_animals[0],  # Главный тотем
            'secondary': top_animals[1],  # Второстепенный
            'tertiary': top_animals[2],  # Дополнительный
            'all_scores': animal_scores,
            'total_questions': len(self.get_all_questions())  # Добавляем total_questions
        }


    def reset(self):
        """Сброс сессии"""
        self.session.current_question = 0
        self.session.answers = {}
        self.session.completed = False
        self.session.save()

    def save_answer(self, question_index, answer_id):
        """Сохранение ответа"""
        answers = self.session.answers or {}
        answers[str(question_index)] = answer_id
        self.session.answers = answers
        self.session.save()

    def advance_question(self):
        """Переход к следующему вопросу"""
        self.session.current_question += 1
        self.session.save()

    def is_completed(self):
        """Проверка завершен ли тест"""
        return self.session.completed

    def get_current_question_index(self):
        return self.session.current_question

    def get_all_questions(self):
        return list(Question.objects.all().order_by('order'))

    def get_current_question(self):
        questions = self.get_all_questions()
        if self.session.current_question < len(questions):
            return questions[self.session.current_question]
        return None

    def calculate_result(self):
        """Подсчет результатов с агрегацией по животным"""
        answers_data = self.session.answers or {}
        animal_scores = {}
        animal_details = {}

        for answer_id in answers_data.values():
            try:
                answer = Answer.objects.select_related('animal').get(id=int(answer_id))
                animal = answer.animal

                animal_scores[animal.id] = animal_scores.get(animal.id, 0) + answer.points
                animal_details[animal.id] = animal

            except (Answer.DoesNotExist, ValueError):
                continue

        if not animal_scores:
            return None

        # Находим животное с максимальным количеством очков
        top_animal_id = max(animal_scores, key=animal_scores.get)
        totem_animal = animal_details[top_animal_id]

        return {
            'animal': totem_animal,
            'points': animal_scores[top_animal_id],
            'total_questions': len(self.get_all_questions()),
            'all_scores': animal_scores
        }

    def complete(self):
        """Завершение теста"""
        self.session.completed = True
        self.session.save()


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(View):
    """Основной webhook для обработки сообщений"""

    bot = TelegramBot()

    def post(self, request):
        try:
            # Парсим входящие данные
            body = request.body.decode('utf-8')
            if not body:
                return JsonResponse({"status": "ok", "message": "Empty body"}, status=200)

            data = json.loads(body)

            # Обрабатываем разные типы update
            if 'message' in data:
                self.handle_message(data['message'])
            elif 'callback_query' in data:
                self.handle_callback(data['callback_query'])

            # Всегда возвращаем 200 OK для Telegram
            return JsonResponse({"status": "ok"}, status=200)

        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return JsonResponse({"status": "error", "error": "Invalid JSON"}, status=200)
        except Exception as e:
            print(f"Error in webhook: {e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({"status": "error", "error": str(e)}, status=200)

    def handle_message(self, message):
        """Обработка текстовых сообщений"""
        try:
            chat_id = message['chat']['id']
            text = message.get('text', '')
            username = message.get('from', {}).get('username', '')

            if text == '/start':
                self.handle_start(chat_id, username)
            elif text == '/animals':
                self.handle_animals(chat_id)
            else:
                self.bot.send_message(
                    chat_id,
                    "Используйте /start чтобы начать тест или /animals чтобы увидеть всех животных"
                )
        except Exception as e:
            print(f"Error handling message: {e}")

    def handle_start(self, chat_id, username):
        """Обработка команды /start"""
        try:
            session = QuizSession(chat_id, username)
            session.reset()

            welcome_text = """🐺 <b>Добро пожаловать в тест "Тотемное животное"!</b>

Ответьте на несколько вопросов, и я расскажу, какое животное является вашим тотемом.

🌿 <b>Готовы?</b> Нажмите кнопку ниже чтобы начать!"""

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🌿 Начать тест", "callback_data": "start_quiz"}],
                    [{"text": "🐾 Посмотреть всех животных", "callback_data": "show_animals"}]
                ]
            }

            self.bot.send_message(chat_id, welcome_text, keyboard)
        except Exception as e:
            print(f"Error in handle_start: {e}")

    def handle_animals(self, chat_id):
        """Показать список животных"""
        try:
            print(f"Showing animals for chat_id: {chat_id}")

            animals = Animal.objects.all()
            print(f"Found {animals.count()} animals")

            if not animals:
                self.bot.send_message(
                    chat_id,
                    "Животные пока не добавлены. Сначала выполните python manage.py init_quiz"
                )
                return

            keyboard = {
                "inline_keyboard": [
                    [{"text": f"🐾 {animal.name}", "callback_data": f"animal_{animal.id}"}]
                    for animal in animals
                ]
            }

            self.bot.send_message(
                chat_id,
                "🐘 <b>Все тотемные животные</b>\n\nВыберите животное чтобы узнать подробнее:",
                keyboard

            )
        except Exception as e:
            print(f"Error in handle_animals: {e}")
            import traceback
            traceback.print_exc()

    def handle_callback(self, callback):
        """Обработка callback запросов"""
        try:
            chat_id = callback['message']['chat']['id']
            callback_id = callback['id']
            callback_data = callback.get('data', '')

            print(f"Callback received: {callback_data}")

            # Отвечаем на callback
            self.bot.answer_callback(callback_id)

            if callback_data == "start_quiz":
                session = QuizSession(chat_id)
                self.start_quiz(session, chat_id)
            elif callback_data == "show_animals":
                self.handle_animals(chat_id)
            elif callback_data.startswith("animal_"):
                animal_id = int(callback_data.split('_')[1])
                self.show_animal_detail(chat_id, animal_id)
            elif callback_data.startswith("ans_"):
                session = QuizSession(chat_id)
                self.process_answer(session, chat_id, callback_data)
            elif callback_data == "restart_quiz":
                session = QuizSession(chat_id)
                session.reset()
                self.start_quiz(session, chat_id)
            else:
                print(f"Unknown callback: {callback_data}")

        except Exception as e:
            print(f"Error handling callback: {e}")
            import traceback
            traceback.print_exc()

    def start_quiz(self, session, chat_id):
        """Начало теста"""
        try:
            session.reset()
            self.send_current_question(session, chat_id)
        except Exception as e:
            print(f"Error in start_quiz: {e}")

    def process_answer(self, session, chat_id, callback_data):
        """Обработка ответа пользователя"""
        try:
            if session.is_completed():
                self.bot.send_message(
                    chat_id,
                    "Вы уже прошли тест! Напишите /start чтобы пройти заново."
                )
                return

            answer_id = int(callback_data.split("_")[1])
            current_index = session.get_current_question_index()

            session.save_answer(current_index, answer_id)
            session.advance_question()

            next_question = session.get_current_question()

            if next_question:
                self.send_current_question(session, chat_id)
            else:
                self.send_result(session, chat_id)

        except Exception as e:
            print(f"Error in process_answer: {e}")
            import traceback
            traceback.print_exc()

    def send_current_question(self, session, chat_id):
        """Отправка текущего вопроса пользователю"""
        try:
            question = session.get_current_question()
            if not question:
                self.send_result(session, chat_id)
                return

            # Создаем клавиатуру с вариантами ответов
            keyboard = {
                "inline_keyboard": [
                    [{"text": answer.text, "callback_data": f"ans_{answer.id}"}]
                    for answer in question.answers.all()
                ]
            }

            question_number = session.get_current_question_index() + 1
            total_questions = len(session.get_all_questions())

            caption = f"❓ <b>Вопрос {question_number}/{total_questions}</b>\n\n{question.text}\n\nВыберите вариант:"

            # Отправляем вопрос
            self.bot.send_message(chat_id, caption, keyboard)

        except Exception as e:
            print(f"Error in send_current_question: {e}")
            import traceback
            traceback.print_exc()
            self.bot.send_message(
                chat_id,
                "Извините, произошла ошибка при загрузке вопроса. Попробуйте /start"
            )

    def send_result(self, session, chat_id):
        """Отправка результата теста с фото животного и топ-3 тотемов"""
        try:
            result = session.calculate_result_advanced()

            if not result or not result['primary']:
                self.bot.send_message(
                    chat_id,
                    "😕 Что-то пошло не так. Попробуйте /start заново."
                )
                return

            primary_animal_name, primary_points = result['primary']
            secondary_animal_name, secondary_points = result['secondary'] if result['secondary'] else (None, 0)
            tertiary_animal_name, tertiary_points = result['tertiary'] if result['tertiary'] else (None, 0)

            # Получаем объект животного по имени
            try:
                primary_animal = Animal.objects.get(name=primary_animal_name)
            except Animal.DoesNotExist:
                self.bot.send_message(
                    chat_id,
                    f"😕 Животное '{primary_animal_name}' не найдено. Попробуйте /start заново."
                )
                return

            total_questions = result['total_questions']
            max_points = total_questions * 4

            # Вычисляем процент соответствия для главного тотема
            percentage = int((primary_points / max_points) * 100)

            # Определяем силу связи
            if percentage >= 80:
                strength_message = "🔮 <b>Это идеальное попадание!</b> Животное идеально отражает вашу сущность."
            elif percentage >= 60:
                strength_message = "✨ <b>Очень сильная связь!</b> Вы действительно похожи на это животное."
            elif percentage >= 40:
                strength_message = "🌿 <b>Хорошее соответствие.</b> У вас много общих черт."
            else:
                strength_message = "💫 <b>Частичное совпадение.</b> Возможно, стоит пройти тест еще раз."

            # Формируем текст результата
            result_text = f"""🎯 <b>Ваше тотемное животное - {primary_animal.name}!</b>

    📊 <b>Степень соответствия:</b> {percentage}%
    ✨ <b>Набрано очков:</b> {primary_points} из {max_points}
    {strength_message}

    📖 <b>Описание:</b>
    {primary_animal.description}

    ━━━━━━━━━━━━━━━━━━━━
    <b>🏆 Ваши топ-3 тотемных животных:</b>

    1️⃣ <b>{primary_animal_name if primary_animal_name else '—'}</b> — {primary_points} очков
    2️⃣ <b>{secondary_animal_name if secondary_animal_name else '—'}</b> — {secondary_points} очков
    3️⃣ <b>{tertiary_animal_name if tertiary_animal_name else '—'}</b> — {tertiary_points} очков
    ━━━━━━━━━━━━━━━━━━━━

    💡 <b>Совет:</b> 
    {self._get_animal_advice(primary_animal.name)}
    """

            # Создаем клавиатуру для перезапуска
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔄 Пройти заново", "callback_data": "restart_quiz"}],
                    [{"text": "🐾 Все животные", "callback_data": "show_animals"}]
                ]
            }

            # Отправляем результат с фото животного
            if primary_animal.photo and primary_animal.photo.name:
                photo_path = os.path.join(settings.MEDIA_ROOT, primary_animal.photo.name)
                print(f"Sending animal photo from: {photo_path}")
                if os.path.exists(photo_path):
                    self.bot.send_photo(chat_id, photo_path, result_text, keyboard)
                else:
                    print(f"Animal photo not found: {photo_path}")
                    self.bot.send_message(chat_id, result_text, keyboard)
            else:
                self.bot.send_message(chat_id, result_text, keyboard)

            session.complete()

        except Exception as e:
            print(f"Error in send_result: {e}")
            import traceback
            traceback.print_exc()
            self.bot.send_message(
                chat_id,
                "Извините, произошла ошибка при подсчете результатов. Попробуйте /start"
            )

    def _get_animal_advice(self, animal_name):
        """Получить совет на основе тотемного животного"""
        advice = {
            "Волк": "Развивайте независимость и верность стае. Доверяйте своей интуиции.",
            "Орел": "Смотрите на мир с высоты. Не бойтесь расширять свои горизонты.",
            "Лев": "Проявляйте лидерские качества. Будьте смелы в своих решениях.",
            "Сова": "Используйте свою мудрость. Доверяйте знаниям и опыту.",
            "Медведь": "Найдите баланс между силой и спокойствием. Защищайте близких.",
            "Дельфин": "Сохраняйте радость и легкость. Цените дружбу и общение."
        }
        return advice.get(animal_name, "Слушайте свое сердце и следуйте своей интуиции.")

    def show_animal_detail(self, chat_id, animal_id):
        """Показать детальную информацию о животном"""
        try:
            animal = Animal.objects.get(id=animal_id)

            text = f"""<b>🦊 {animal.name}</b>

📖 <b>Описание:</b>
{animal.description}

💫 <b>Характеристики:</b>
• Символизм: {self._get_animal_symbolism(animal.name)}
• Сильные стороны: {self._get_animal_strengths(animal.name)}
• Когда появляется: {self._get_animal_when_appears(animal.name)}

Пройти тестирование заново? Нажмите /start

Все животные /animals
"""

            if animal.photo and animal.photo.name:
                photo_path = os.path.join(settings.MEDIA_ROOT, animal.photo.name)
                if os.path.exists(photo_path):
                    self.bot.send_photo(chat_id, photo_path, text)
                else:
                    self.bot.send_message(chat_id, text)
            else:
                self.bot.send_message(chat_id, text)

        except Animal.DoesNotExist:
            self.bot.send_message(chat_id, "Животное не найдено")
        except Exception as e:
            print(f"Error in show_animal_detail: {e}")

    def _get_animal_symbolism(self, animal_name):
        """Получить символизм животного"""
        symbols = {
            "Волк": "Свобода, независимость, верность, интуиция",
            "Орел": "Власть, свобода, духовное видение, трансформация",
            "Лев": "Сила, мужество, лидерство, благородство",
            "Сова": "Мудрость, знания, интуиция, проницательность",
            "Медведь": "Сила, защита, внутренняя гармония, исцеление",
            "Дельфин": "Дружба, радость, свобода, интеллект"
        }
        return symbols.get(animal_name, "Мудрость и сила")

    def _get_animal_strengths(self, animal_name):
        """Получить сильные стороны животного"""
        strengths = {
            "Волк": "Верность, выносливость, командный дух",
            "Орел": "Видение, решительность, смелость",
            "Лев": "Харизма, уверенность, защита",
            "Сова": "Аналитический ум, терпение, наблюдательность",
            "Медведь": "Стойкость, заботливость, самоанализ",
            "Дельфин": "Коммуникабельность, оптимизм, креативность"
        }
        return strengths.get(animal_name, "Уникальные качества")

    def _get_animal_when_appears(self, animal_name):
        """Когда появляется животное-тотем"""
        appearances = {
            "Волк": "Когда вам нужна защита и верность близких",
            "Орел": "Когда вы стоите перед важным решением",
            "Лев": "Когда нужно проявить лидерские качества",
            "Сова": "Когда ищете ответы на сложные вопросы",
            "Медведь": "Когда нужна внутренняя сила и спокойствие",
            "Дельфин": "Когда требуется радость и легкость в жизни"
        }
        return appearances.get(animal_name, "В моменты важных жизненных выборов")


@method_decorator(csrf_exempt, name='dispatch')
class WebhookInfoView(View):
    """View для получения информации о webhook"""

    def get(self, request):
        from zoo.secret import TELEGRAM_ACCESS_TOKEN

        url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/getWebhookInfo"
        response = requests.get(url)
        return JsonResponse(response.json())


@method_decorator(csrf_exempt, name='dispatch')
class WebhookInfoView(View):
    """View для получения информации о webhook"""

    def get(self, request):
        from zoo.secret import TELEGRAM_ACCESS_TOKEN

        url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/getWebhookInfo"
        response = requests.get(url)
        return JsonResponse(response.json())
