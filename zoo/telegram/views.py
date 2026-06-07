import json
import os
from django.core.cache import cache
import requests
from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from telegram.models import Animal, Answer, Question, TelegramSettings, UserSession, Photo, AboutZoo, GuardianProgram, \
    Feedback, PotentialGuardian

from zoo.secret import TELEGRAM_ACCESS_TOKEN




class HelpView(TemplateView):
    template_name = "telegram/webhook.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["BOT_TOKEN"] = TELEGRAM_ACCESS_TOKEN
        context["HTTPS_URL"] = TelegramSettings.objects.first().webhook_url if TelegramSettings.objects.first() else ""
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
            'total_questions': len(self.get_all_questions())
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

    def _get_temp_rating(self, chat_id):
        return cache.get(f'temp_rating_{chat_id}')

    def _set_temp_rating(self, chat_id, rating):
        cache.set(f'temp_rating_{chat_id}', rating, timeout=3600)  # 1 час

    def _clear_temp_rating(self, chat_id):
        cache.delete(f'temp_rating_{chat_id}')


    def _set_waiting_for_guardian_application(self, username):
        cache.set(f'guardian_application_{username}', True, timeout=3600)  # 1 час

    def _get_waiting_for_guardian_application(self, username):
        return cache.get(f'guardian_application_{username}')

    def _clear_waiting_for_guardian_application(self, username):
        cache.delete(f'guardian_application_{username}')


    def _get_quiz_rezult(self, username):
        return cache.get(f'temp_quiz_rezult_{username}')

    def _set_quiz_rezult(self, username, totems):
        cache.set(f'temp_quiz_rezult_{username}', totems, timeout=3600)  # 1 час


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

    def show_restart_prompt(self, chat_id):
        """Показать предложение перезапустить викторину"""
        text = """🎯 <b>Викторина "Тотемное животное" завершена!</b>
    
    🌿 <b>Что теперь?</b>"""

        keyboard = {
            "inline_keyboard": [
                [{"text": "🦘 Пройти викторину ещё раз", "callback_data": "restart_quiz"}],
                [{"text": "🐾 Посмотреть всех животных", "callback_data": "show_animals"}],
                [{"text": "🏛️ О зоопарке", "callback_data": "about_zoo"}],
                [{"text": "🤝 Программа опеки", "callback_data": "guardian_program"}],
                [{"text": "💬 Оставить отзыв", "callback_data": "feedback_menu"}],
                [{"text": "🔙 В главное меню", "callback_data": "main_menu"}],
            ]
        }

        self.bot.send_message(chat_id, text, keyboard)


    def handle_message(self, message):
        """Обработка текстовых сообщений"""
        try:
            chat_id = message['chat']['id']
            text = message.get('text', '')
            username = message.get('from', {}).get('username', '')

            # Проверяем, ожидаем ли мы комментарий к отзыву
            if self._get_temp_rating(chat_id):
                # Это комментарий к отзыву
                rating = self._get_temp_rating(chat_id)
                self.save_feedback(chat_id, username, rating, text)
                return

            if text == '/start':
                self.handle_start(chat_id, username)
            elif text == '/animals':
                self.handle_animals(chat_id)
            elif text == '/guardian':
                self.show_guardian_program(chat_id)
            elif text == '/become_guardian':
                self.become_guardian(chat_id)
            elif text == '/feedback':
                self.show_feedback_menu(chat_id)
            elif text == '/cancel':

                self.bot.send_message(chat_id, "Действие отменено. Возвращаюсь в главное меню.")
                self.handle_start(chat_id, username)
            else:
                self.bot.send_message(
                    chat_id,
                    "Используй /start для перехода в главное меню."
                )
        except Exception as e:
            print(f"Error handling message: {e}")

    def handle_start(self, chat_id, username):
        """Обработка команды /start"""
        try:
            session = QuizSession(chat_id, username)
            session.reset()

            welcome_text = """🐺 <b>Привет! Ты в чате московского зоопарка</b>

Хочешь, я расскажу, какое животное является твоим тотемом?

🌿 <b>Готов?</b> Нажми кнопку ниже, чтобы начать!"""

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🐻 Узнать, какое у тебя тотемное животное", "callback_data": "start_quiz"}],
                    [{"text": "🐾 Посмотреть всех животных", "callback_data": "show_animals"}],
                    [{"text": "🏛️ О зоопарке", "callback_data": "about_zoo"}],
                    [{"text": "🤝 Программа опеки", "callback_data": "guardian_program"}],
                    [{"text": "💬 Оставить отзыв", "callback_data": "feedback_menu"}],
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
                    "Животные пока не добавлены." #  Надо выполнить python manage.py init_quiz
                )
                return

            # Разбиваем животных на колонки (по 2 в ряд)
            animal_buttons = []
            row = []
            for i, animal in enumerate(animals, 1):
                row.append({"text": f"{animal.emoji} {animal.name}", "callback_data": f"animal_{animal.id}"})
                if i % 2 == 0:  # Каждые 2 кнопки в ряд
                    animal_buttons.append(row)
                    row = []

            # Добавляем оставшиеся кнопки
            if row:
                animal_buttons.append(row)

            # Добавляем кнопку для прохождения теста
            keyboard = {
                "inline_keyboard": animal_buttons + [
                    [{"text": "🐨 Пройти тест и узнать тотемное животное", "callback_data": "start_quiz"}],
                    [{"text": "🏛️ О зоопарке", "callback_data": "about_zoo"}],
                    [{"text": "🤝 Программа опеки", "callback_data": "guardian_program"}],
                    [{"text": "💬 Оставить отзыв", "callback_data": "feedback_menu"}],
                ]
            }

            self.bot.send_message(
                chat_id,
                "🐘 <b>Все тотемные животные</b>\n\nВыбери животное, чтобы узнать подробнее о нем. Или пройди викторину, чтобы узнать свое тотемное животное:",
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
            username = callback['message']['chat'].get('username', '')

            print(f"Callback received: {callback_data}")

            # Отвечаем на callback
            self.bot.answer_callback(callback_id)

            if callback_data == "start_quiz":
                session = QuizSession(chat_id)
                self.start_quiz(session, chat_id)
            elif callback_data == "restart_quiz":
                session = QuizSession(chat_id)
                session.reset()
                self.start_quiz(session, chat_id)
            elif callback_data == "show_animals":
                self.handle_animals(chat_id)
            elif callback_data == "about_zoo":
                self.show_about_zoo(chat_id)
            elif callback_data == "guardian_program":
                self.show_guardian_program(chat_id)
            elif callback_data == "feedback_menu":
                self.show_feedback_menu(chat_id)
            elif callback_data.startswith("feedback_"):
                user_input = callback_data.split('_')[1]
                if user_input in ['1', '2', '3', '4', '5']:
                    self.process_feedback_rating(chat_id, int(user_input), username)
                elif user_input == "write-comment":

                    self.ask_for_feedback_comment(chat_id)
                elif user_input == "skip":
                    rating_value = self._get_temp_rating(chat_id)
                    self.save_feedback(chat_id, username, rating_value, "")
            elif callback_data == "show_zoo_description":
                self.show_zoo_description(chat_id)
            elif callback_data == "show_zoo_photos":
                self.show_zoo_photos(chat_id)
            elif callback_data.startswith("animal_"):
                animal_id = int(callback_data.split('_')[1])
                self.show_animal_detail(chat_id, animal_id)
            elif callback_data.startswith("ans_"):
                session = QuizSession(chat_id)
                self.process_answer(session, chat_id, callback_data)
            elif callback_data == "main_menu":
                session = QuizSession(chat_id)
                session.reset()
                self.handle_start(chat_id, username)
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
                    "Ты проешл тест для определения тотема! Повторить викторину /start_quiz или выйти в главное меню /start ."
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
                "Извини, произошла ошибка при загрузке вопроса. Попробуй /start"
            )

    def restart_quiz(self, chat_id):
        """Перезапуск викторины"""
        session = QuizSession(chat_id)
        session.reset()
        self.start_quiz(session, chat_id)

    def _prepare_totems_for_caching(self, totems):

        """Подготовка топ-3 тотемов для кеширования"""
        result = {
            'primary': totems.get("primary_animal_name"),
            'secondary': totems.get("secondary_animal_name"),
            'tertiary': totems.get("tertiary_animal_name"),
            'primary_points': totems.get("primary_points", 0),
            'secondary_points': totems.get("secondary_points", 0),
            'tertiary_points': totems.get("tertiary_points", 0),
        }
        return result

    def send_result(self, session, chat_id):
        """Отправка результата теста с фото животного и топ-3 тотемов"""
        try:
            result = session.calculate_result_advanced()

            if not result or not result['primary']:
                self.bot.send_message(
                    chat_id,
                    "😕 Что-то пошло не так. Попробуй /start заново."
                )
                return

            primary_animal_name, primary_points = result['primary']
            secondary_animal_name, secondary_points = result['secondary'] if result['secondary'] else (None, 0)
            tertiary_animal_name, tertiary_points = result['tertiary'] if result['tertiary'] else (None, 0)

            totems_for_caching = self._prepare_totems_for_caching({
                "primary_animal_name": primary_animal_name,
                "secondary_animal_name": secondary_animal_name,
                "tertiary_animal_name": tertiary_animal_name,
                "primary_points": primary_points,
                "secondary_points": secondary_points,
                "tertiary_points": tertiary_points,
            })

            username = session.session.username or f"user_{chat_id}"
            self._set_quiz_rezult(username, totems_for_caching)

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
            result_text = f"""🎯 <b>Да ты - {primary_animal.name}!</b>

    📊 <b>Степень соответствия:</b> {percentage}%
    ✨ <b>Набрано очков:</b> {primary_points} из {max_points}
    {strength_message}

    📖 <b>Описание:</b>
    {primary_animal.description}

    ━━━━━━━━━━━━━━━━━━━━
    <b>🏆 Твои топ-3 тотемных животных:</b>

    1️⃣ <b>{primary_animal_name if primary_animal_name else '—'}</b> — {primary_points} очков
    2️⃣ <b>{secondary_animal_name if secondary_animal_name else '—'}</b> — {secondary_points} очков
    3️⃣ <b>{tertiary_animal_name if tertiary_animal_name else '—'}</b> — {tertiary_points} очков
    ━━━━━━━━━━━━━━━━━━━━

    💡 <b>Совет:</b> 
    {self._get_animal_advice(primary_animal.name)}
    ━━━━━━━━━━━━━━━━━━━━

    💰 <b>Почему бы тебе не взять свой тотем в опеку?</b> 
    <b>Нажми /guardian</b>


"""

            # Отправляем результат с фото животного
            if primary_animal.photo and primary_animal.photo.name:
                photo_path = os.path.join(settings.MEDIA_ROOT, primary_animal.photo.name)
                print(f"Sending animal photo from: {photo_path}")
                if os.path.exists(photo_path):
                    self.bot.send_photo(chat_id, photo_path, result_text)
                else:
                    print(f"Animal photo not found: {photo_path}")
                    self.bot.send_message(chat_id, result_text)
            else:
                self.bot.send_message(chat_id, result_text)

            session.complete()

            # После отправки результата, показываем предложение перезапустить викторину
            self.show_restart_prompt(chat_id)

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

    💡 <b>Почему бы тебе не взять его в опеку?:</b> 
    Нажмите /guardian

    """

            # Создаем клавиатуру с кнопками
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔄 Пройти викторину заново", "callback_data": "restart_quiz"}],  # <-- ДОБАВЛЕНО
                    [{"text": "🐾 Все животные", "callback_data": "show_animals"}],
                    [{"text": "🏛️ О зоопарке", "callback_data": "about_zoo"}],
                    [{"text": "🤝 Программа опеки", "callback_data": "guardian_program"}],
                    [{"text": "💬 Оставить отзыв", "callback_data": "feedback_menu"}],
                    [{"text": "🔙 В главное меню", "callback_data": "main_menu"}],
                ]
            }

            if animal.photo and animal.photo.name:
                photo_path = os.path.join(settings.MEDIA_ROOT, animal.photo.name)
                if os.path.exists(photo_path):
                    self.bot.send_photo(chat_id, photo_path, text, keyboard)
                else:
                    self.bot.send_message(chat_id, text, keyboard)
            else:
                self.bot.send_message(chat_id, text, keyboard)

        except Animal.DoesNotExist:
            self.bot.send_message(chat_id, "Животное не найдено")
        except Exception as e:
            print(f"Error in show_animal_detail: {e}")
            import traceback
            traceback.print_exc()

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
            "Волк": "Когда тебе нужна защита и верность близких",
            "Орел": "Когда ты стоишь перед важным решением",
            "Лев": "Когда нужно проявить лидерские качества",
            "Сова": "Когда ищешь ответы на сложные вопросы",
            "Медведь": "Когда нужна внутренняя сила и спокойствие",
            "Дельфин": "Когда требуется радость и легкость в жизни"
        }
        return appearances.get(animal_name, "В моменты важных жизненных выборов")

    def show_about_zoo(self, chat_id):
        """Показать меню выбора: описание или фото зоопарка"""
        text = """🏛️ <b>Информация о зоопарке</b>

Что вас интересует?"""

        keyboard = {
            "inline_keyboard": [
                [{"text": "📖 Описание и контакты", "callback_data": "show_zoo_description"}],
                [{"text": "📸 Фото зоопарка", "callback_data": "show_zoo_photos"}],
                [{"text": "🤝 Программа опеки", "callback_data": "guardian_program"}],
                [{"text": "💬 Оставить отзыв", "callback_data": "feedback_menu"}],
                [{"text": "🔙 В главное меню", "callback_data": "main_menu"}],

            ]
        }

        self.bot.send_message(chat_id, text, keyboard)

    def show_zoo_description(self, chat_id):
        """Показать описание и контакты зоопарка"""
        try:
            about = AboutZoo.objects.first()

            if not about:
                self.bot.send_message(
                    chat_id,
                    "🏛️ <b>Информация о зоопарке временно недоступна.</b>\n\nПожалуйста, зайдите позже."
                )
                return

            # Форматируем номер телефона
            formatted_phone = about.get_phone()

            # Очищаем описание - убираем пробелы в начале каждой строки
            description_lines = about.description.split('\n')
            clean_description = '\n'.join(line.strip() for line in description_lines)

            # Формируем текст (ВАЖНО: без отступов перед строками!)
            about_text = (
                "🏛️ <b>О нашем зоопарке</b>\n\n"
                "📖 <b>Описание:</b>\n"
                f"{clean_description}\n\n"
                "📞 <b>Контакты:</b>\n"
                f"• Email: {about.email}\n"
                f"• Телефон: {formatted_phone}\n\n"
                "🌍 <b>Часы работы:</b>\n"
                "Ежедневно: 9:00 - 21:00\n\n"
                "🎫 <b>Стоимость билетов:</b>\n"
                f"Взрослый: {about.adult_price} руб.\n"
                f"Льготный (дети, пенсионеры): {about.reduced_price} руб.\n\n"
                "✨ <b>Наши преимущества:</b>\n"
                "• Более 100 видов животных\n"
                "• Ежедневные шоу и кормления\n"
                "• Контактный зоопарк\n"
                "• Экскурсии для групп"
            )

            keyboard = {
                "inline_keyboard": [
                    [{"text": "📸 Смотреть фото", "callback_data": "show_zoo_photos"}],
                    [{"text": "🌿 Узнать тотемное животное", "callback_data": "start_quiz"}],
                    [{"text": "🐾 Все животные", "callback_data": "show_animals"}],
                    [{"text": "🤝 Программа опеки", "callback_data": "guardian_program"}],
                    [{"text": "💬 Оставить отзыв", "callback_data": "feedback_menu"}],
                    [{"text": "🔙 В главное меню", "callback_data": "main_menu"}]
                ]
            }

            self.bot.send_message(chat_id, about_text, keyboard)

        except Exception as e:
            print(f"Error in show_zoo_description: {e}")
            import traceback
            traceback.print_exc()
            self.bot.send_message(
                chat_id,
                "Извините, произошла ошибка при загрузке информации о зоопарке."
            )

    def show_zoo_photos(self, chat_id):
        """Показать все фото зоопарка"""
        try:
            photos = Photo.objects.all()

            if not photos:
                self.bot.send_message(
                    chat_id,
                    "📸 Фото зоопарка временно недоступны."
                )
                return

            # Отправляем все фото
            for photo in photos:
                if photo.photo and photo.photo.name:
                    photo_path = os.path.join(settings.MEDIA_ROOT, photo.photo.name)
                    if os.path.exists(photo_path):
                        caption = photo.caption if photo.caption else ""
                        self.bot.send_photo(chat_id, photo_path, caption)

            # Меню после показа фото
            menu_text = """📸 <b>Это все фото нашего зоопарка</b>

    Что бы вы хотели сделать дальше?"""

            keyboard = {
                "inline_keyboard": [
                    [{"text": "📖 Описание зоопарка", "callback_data": "show_zoo_description"}],
                    [{"text": "🌿 Узнать свое тотемное животное", "callback_data": "start_quiz"}],
                    [{"text": "🐾 Все животные", "callback_data": "show_animals"}],
                    [{"text": "🤝 Программа опеки", "callback_data": "guardian_program"}],
                    [{"text": "💬 Оставить отзыв", "callback_data": "feedback_menu"}],
                    [{"text": "🔙 В главное меню", "callback_data": "main_menu"}]
                ]
            }

            self.bot.send_message(chat_id, menu_text, keyboard)

        except Exception as e:
            print(f"Error in show_zoo_photos: {e}")
            import traceback
            traceback.print_exc()
            self.bot.send_message(
                chat_id,
                "Извините, произошла ошибка при загрузке фото."
            )

    def show_feedback_menu(self, chat_id):
        """Показать меню обратной связи"""
        text = """💬 <b>Обратная связь</b>

    Так! Не ругаться. Как тебе зоопарк?"""

        keyboard = {
            "inline_keyboard": [
                [{"text": "⭐ 5 - Отлично", "callback_data": "feedback_5"}],
                [{"text": "👍 4 - Хорошо", "callback_data": "feedback_4"}],
                [{"text": "😐 3 - Нормально", "callback_data": "feedback_3"}],
                [{"text": "😕 2 - Плохо", "callback_data": "feedback_2"}],
                [{"text": "👎 1 - Ужасно", "callback_data": "feedback_1"}],
                [{"text": "🔙 Назад", "callback_data": "main_menu"}],
            ]
        }

        self.bot.send_message(chat_id, text, keyboard)

    def process_feedback_rating(self, chat_id, rating, username):
        """Обработка оценки отзыва"""
        try:
            # Сохраняем временную оценку
            self._set_temp_rating(chat_id, rating)

            text = f"""💬 <b>Спасибо за оценку {rating}⭐!</b>

    Но она еще не сохранена. Чтобы ее сохранить, оставь комментарий или просто нажми "Пропустить".   

    Твое мнение поможет нам стать лучше!"""

            keyboard = {
                "inline_keyboard": [
                    [{"text": "✏️ Написать комментарий", "callback_data": "feedback_write-comment"}],
                    [{"text": "⏭️ Пропустить", "callback_data": "feedback_skip"}],
                    [{"text": "🔙 Назад", "callback_data": "feedback_menu"}],
                ]
            }

            self.bot.send_message(chat_id, text, keyboard)

        except Exception as e:
            print(f"Error in process_feedback_rating: {e}")

    def ask_for_feedback_comment(self, chat_id):
        """Запросить комментарий к отзыву"""
        text = """💬 <b>Напишите ваш комментарий</b>

    Пожалуйста, напиши сообщение с пожеланиями или замечаниями.

    Ты можешь написать что угодно, а я сохраню твой отзыв.

    Чтобы отменить, нажми /cancel"""

        self.bot.send_message(chat_id, text)


    def save_feedback(self, chat_id, username, rating, comment=""):
        """Сохранить отзыв в базу данных"""
        try:
            feedback = Feedback.objects.create(
                user_id=chat_id,
                username=username or f"user_{chat_id}",
                rating=rating,
                comment=comment
            )

            # Отправляем подтверждение
            text = f"""✅ <b>Спасибо за отзыв!</b>

    Твоя оценка: {rating}⭐
    Комментарий: {comment if comment else "Не оставлен"}

    Мы учтем и будем стараться стать лучше!

    Хочешь оставить еще один отзыв? Нажми /feedback"""

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🏠 В главное меню", "callback_data": "main_menu"}],
                    [{"text": "💬 Оставить еще отзыв", "callback_data": "feedback_menu"}],
                ]
            }

            self.bot.send_message(chat_id, text, keyboard)
            self._clear_temp_rating(chat_id)

        except Exception as e:
            print(f"Error saving feedback: {e}")
            self.bot.send_message(chat_id, "Извините, произошла ошибка при сохранении отзыва. Попробуйте позже.")

    def show_guardian_program(self, chat_id):
        """Показать информацию о программе опеки"""
        try:
            guardian = GuardianProgram.objects.first()

            if not guardian or not guardian.description:
                self.bot.send_message(
                    chat_id,
                    "🤝 <b>Программа опеки</b>\n\nИнформация о программе опеки временно недоступна. Пожалуйста, зайдите позже."
                )
                return

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🐘 Обратиться в зоопарк по поводу опеки", "callback_data": "become_guardian"}],
                    [{"text": "🔙 В главное меню", "callback_data": "main_menu"}]
                ]
            }

            result = guardian.description.strip()
            about = AboutZoo.objects.first()
            result += "\n\n"
            result += "📞 <b>Контакты:</b>\n"
            result += f"• Email: {about.email}\n"
            result += f"• Телефон: {about.get_phone()}\n\n"

            self.bot.send_message(chat_id, result, keyboard)

        except Exception as e:
            print(f"Error in show_guardian_program: {e}")
            import traceback
            traceback.print_exc()
            self.bot.send_message(
                chat_id,
                "Извините, произошла ошибка при загрузке информации о программе опеки."
            )

    def become_guardian(self, chat_id):
        pass


    def save_guardian_application(self, chat_id, username, message_text):
        """Сохранить заявку на опеку"""

        about_zoo = AboutZoo.objects.first()
        try:
            # Получаем результаты викторины из кеша
            quiz_result = self._get_quiz_rezult(username) or {}

            # Форматируем результат викторины для сохранения
            quiz_result_text = ""
            if quiz_result:
                quiz_result_text = f"""
    Топ-3 тотемных животных:
    1. {quiz_result.get('primary', 'Не определено')} ({quiz_result.get('primary_points', 0)} очков)
    2. {quiz_result.get('secondary', 'Не определено')} ({quiz_result.get('secondary_points', 0)} очков)
    3. {quiz_result.get('tertiary', 'Не определено')} ({quiz_result.get('tertiary_points', 0)} очков)
    """

            # Создаем запись в базе данных
            application = PotentialGuardian.objects.create(
                username=username,
                quiz_result=quiz_result_text,
                message=message_text,
                flag=False,
                handled=False
            )

            # Отправляем подтверждение пользователю
            confirmation_text = f"""✅ <b>Ты молодец!</b>
    
    Спасибо за интерес к программе опеки!
    
    Наши сотрудники свяжутся с тобой в ближайшее время
    через Telegram или удобным для тебя способом (если Вы оставили контакты в сообщении).
    
    Если у есть дополнительные вопросы, пиши на email: {about_zoo.email}
    
    Или звони: {about_zoo.get_phone()}
    
    Вернуться в главное меню: /start"""

            self.bot.send_message(chat_id, confirmation_text)

            # Очищаем состояние ожидания
            self.waiting_for_guardian_application[chat_id] = False

            # Опционально: отправить уведомление администраторам
            self.notify_admins_about_application(application)

        except Exception as e:
            print(f"Error saving guardian application: {e}")
            import traceback
            traceback.print_exc()
            self.bot.send_message(
                chat_id,
                f"Никогда такого не было и вот опять. Произошла ошибка при сохранении заявки. Попробуй позже или напиши нам на email: {about_zoo.email}"
            )


@method_decorator(csrf_exempt, name='dispatch')
class WebhookInfoView(View):
    """View для получения информации о webhook"""

    def get(self, request):
        from zoo.secret import TELEGRAM_ACCESS_TOKEN

        url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/getWebhookInfo"
        response = requests.get(url)
        return JsonResponse(response.json())


class PhotoView(TemplateView):
    template_name = "telegram/photo.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = Photo.objects.get(pk=self.kwargs["pk"])
        return context
