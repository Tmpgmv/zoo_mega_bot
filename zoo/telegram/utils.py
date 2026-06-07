import urllib.parse

from telegram.models import AboutZoo, TelegramSettings


class ShareUtils:
    """Утилиты для создания ссылок на шеринг в соцсети"""

    @staticmethod
    def generate_share_urls(text):
        """
        Генерирует ссылки для шаринга в соцсетях
        """
        encoded_text = urllib.parse.quote(text)

        telegram_settings = TelegramSettings.objects.first()

        encoded_bot_link = urllib.parse.quote(telegram_settings.bot_url)

        share_urls = {
            'telegram': f"https://t.me/share/url?url={encoded_bot_link}&text={encoded_text}",
            'vk': f"https://vk.com/share.php?url={encoded_bot_link}&title={encoded_text}",
            'ok': f"https://connect.ok.ru/dk?st.cmd=WidgetSharePreview&st.shareUrl={encoded_bot_link}&st.title={encoded_text}"
        }

        return share_urls

    @staticmethod
    def get_share_keyboard(share_urls, totems):
        """Создает клавиатуру для шеринга"""

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📱 Telegram", "url": share_urls['telegram']},
                    {"text": "📘 ВКонтакте", "url": share_urls['vk']},
                    {"text": "🔴 Одноклассники", "url": share_urls['ok']}
                ],
                [
                    {"text": "🔄 Пройти викторину ещё раз", "callback_data": "restart_quiz"},
                    {"text": "🔙 В главное меню", "callback_data": "main_menu"}
                ]
            ]
        }

        # Добавляем информацию о топ-3 животных
        if totems:
            top_text = f"🏆 Топ-3:\n1️⃣ {totems.get('primary', '—')}\n2️⃣ {totems.get('secondary', '—')}\n3️⃣ {totems.get('tertiary', '—')}"
            keyboard['inline_keyboard'].insert(0, [{"text": "📊 Мои результаты", "callback_data": "show_my_results"}])

        return keyboard