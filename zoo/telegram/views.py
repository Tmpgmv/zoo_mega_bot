import json

import requests
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from telegram.models import TelegramSettings
from zoo.secret import TELEGRAM_ACCESS_TOKEN


# @method_decorator(csrf_exempt, name="dispatch")
# class TelegramWebhookView(View):
#     def post(self, request, *args, **kwargs):
#         # Parse incoming payload
#         data = json.loads(request.body.decode("utf-8"))
#
#         # Safely extract message details
#         message = data.get("message", {})
#         chat_id = message.get("chat", {}).get("id")
#         user_text = message.get("text")
#
#         # If it is a valid text message, reply
#         if chat_id and user_text:
#             payload = {
#                 "chat_id": chat_id,
#                 "text": f"You said: {user_text} (via CBV)"
#             }
#             url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/sendMessage"
#             requests.post(url, json=payload)
#
#         return HttpResponse("OK")



class HelpView(TemplateView):
    template_name = "telegram/webhook.html"

    def get_context_data(self, **kwargs):
        context = super(HelpView, self).get_context_data(**kwargs)
        context["BOT_TOKEN"] = TELEGRAM_ACCESS_TOKEN
        context["HTTPS_URL"] = TelegramSettings.objects.first().webhook_url
        return context


import json
import requests
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from telegram.models import Question, Answer, UserSession
from zoo.secret import TELEGRAM_ACCESS_TOKEN


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
        return requests.post(url, json=data)

    @staticmethod
    def send_photo(chat_id, photo_path, caption, reply_markup=None):
        url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/sendPhoto"
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            if reply_markup:
                data['reply_markup'] = json.dumps(reply_markup)
            return requests.post(url, files=files, data=data)

    @staticmethod
    def answer_callback(callback_id):
        url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/answerCallbackQuery"
        return requests.post(url, json={"callback_query_id": callback_id})


class QuizSession:
    """Класс для управления сессией теста"""

    def __init__(self, user_id, username=None):
        self.user_id = user_id
        self.session, self.created = UserSession.objects.get_or_create(
            user_id=user_id,
            defaults={'username': username or ''}
        )

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
        """Подсчет результатов"""
        answers_data = self.session.answers or {}
        animals = {}

        for answer_id in answers_data.values():
            try:
                answer = Answer.objects.get(id=int(answer_id))
                animals[answer.animal] = animals.get(answer.animal, 0) + answer.points
            except Answer.DoesNotExist:
                continue

        if not animals:
            return None

        totem = max(animals, key=animals.get)
        points = animals[totem]

        return {
            'animal': totem,
            'points': points,
            'total_questions': len(self.get_all_questions())
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
            data = json.loads(request.body)

            # Обработка сообщений
            if 'message' in data:
                response = self.handle_message(data['message'])

            # Обработка callback запросов
            elif 'callback_query' in data:
                response = self.handle_callback(data['callback_query'])

            else:
                response = JsonResponse({"status": "ok"})

            return response

        except Exception as e:
            print(f"Error in webhook: {e}")
            return JsonResponse({"status": "error", "error": str(e)})

    def handle_message(self, message):
        """Обработка текстовых сообщений"""
        chat_id = message['chat']['id']
        text = message.get('text', '')
        username = message.get('from', {}).get('username', '')

        if text == '/start':
            return self.handle_start(chat_id, username)

        # Можно добавить другие команды
        return self.bot.send_message(chat_id, "Используйте /start чтобы начать тест")

    def handle_start(self, chat_id, username):
        """Обработка команды /start"""
        session = QuizSession(chat_id, username)
        session.reset()

        welcome_text = """🐺 <b>Добро пожаловать в тест "Тотемное животное"!</b>

Ответьте на несколько вопросов, и я расскажу, какое животное является вашим тотемом.

🌿 <b>Готовы?</b> Нажмите кнопку ниже чтобы начать!"""

        keyboard = {
            "inline_keyboard": [
                [{"text": "🌿 Начать тест", "callback_data": "start_quiz"}]
            ]
        }

        return self.bot.send_message(chat_id, welcome_text, keyboard)

    def handle_callback(self, callback):
        """Обработка callback запросов"""
        chat_id = callback['message']['chat']['id']
        callback_id = callback['id']
        callback_data = callback['data']

        # Отвечаем на callback (убираем "часики" на кнопке)
        self.bot.answer_callback(callback_id)

        session = QuizSession(chat_id)

        if callback_data == "start_quiz":
            return self.start_quiz(session, chat_id)

        elif callback_data.startswith("ans_"):
            return self.process_answer(session, chat_id, callback_data)

        return JsonResponse({"status": "ok"})

    def start_quiz(self, session, chat_id):
        """Начало теста"""
        session.reset()
        return self.send_current_question(session, chat_id)

    def process_answer(self, session, chat_id, callback_data):
        """Обработка ответа пользователя"""
        if session.is_completed():
            self.bot.send_message(chat_id, "Вы уже прошли тест! Напишите /start чтобы пройти заново.")
            return JsonResponse({"status": "ok"})

        answer_id = int(callback_data.split("_")[1])
        current_index = session.get_current_question_index()

        # Сохраняем ответ
        session.save_answer(current_index, answer_id)
        session.advance_question()

        # Проверяем есть ли еще вопросы
        next_question = session.get_current_question()

        if next_question:
            return self.send_current_question(session, chat_id)
        else:
            return self.send_result(session, chat_id)

    def send_current_question(self, session, chat_id):
        """Отправка текущего вопроса пользователю"""
        question = session.get_current_question()
        if not question:
            return self.send_result(session, chat_id)

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

        # Отправляем вопрос (с картинкой или без)
        if question.image and question.image.path:
            self.bot.send_photo(chat_id, question.image.path, caption, keyboard)
        else:
            self.bot.send_message(chat_id, caption, keyboard)

        return JsonResponse({"status": "ok"})

    def send_result(self, session, chat_id):
        """Отправка результата теста"""
        result = session.calculate_result()

        if not result:
            self.bot.send_message(chat_id, "😕 Что-то пошло не так. Попробуйте /start заново.")
            return JsonResponse({"status": "ok"})

        result_text = f"""🎯 <b>Ваше тотемное животное - {result['animal']}!</b>

✨ Набрано очков: {result['points']}
📊 Пройдено вопросов: {result['total_questions']}

🌿 Это животное отражает вашу сущность и внутреннюю силу.

Хотите пройти тест заново? Нажмите /start"""

        self.bot.send_message(chat_id, result_text)
        session.complete()

        return JsonResponse({"status": "ok"})

#
# @method_decorator(csrf_exempt, name='dispatch')
# class SetWebhookView(View):
#     """View для установки webhook (удобно для дебага)"""
#
#     def get(self, request):
#         from zoo.secret import TELEGRAM_ACCESS_TOKEN
#
#         # Получаем текущий URL из запроса
#         webhook_url = request.build_absolute_uri('/webhook/')
#
#         url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/setWebhook"
#         response = requests.post(url, json={"url": webhook_url})
#
#         return JsonResponse(response.json())
#
#     def delete(self, request):
#         """Удаление webhook"""
#         from zoo.secret import TELEGRAM_ACCESS_TOKEN
#
#         url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/deleteWebhook"
#         response = requests.post(url)
#
#         return JsonResponse(response.json())


@method_decorator(csrf_exempt, name='dispatch')
class WebhookInfoView(View):
    """View для получения информации о текущем webhook"""

    def get(self, request):
        from zoo.secret import TELEGRAM_ACCESS_TOKEN

        url = f"https://api.telegram.org/bot{TELEGRAM_ACCESS_TOKEN}/getWebhookInfo"
        response = requests.get(url)

        return JsonResponse(response.json())