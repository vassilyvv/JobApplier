from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import Select

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram import ForceReply, Update, InlineKeyboardMarkup, InlineKeyboardButton

from datetime import datetime

job_appliers = dict() # chat_id to applier
user_replies = dict()


def run_tg_bot_and_loop(_telegram_bot_token):
    print('starting telegram bot')

    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message_parts = update.message.text.split()[1:]
        if len(message_parts) != 3:
            await update.effective_chat.send_message('Invalid number of arguments. Expected email, password, jobs list url')
            return
        email, password, url = message_parts
        job_appliers[update.effective_chat.id] = JobApplier(
            tg_update=update,
            email=email, 
            password=password, 
            jobs_list_url=url
        ).apply_for_jobs()
        await anext(job_appliers[update.effective_chat.id])

    async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(f'Accepted')
        user_replies[update.effective_chat.id] = update.message.text
        await anext(job_appliers[update.effective_chat.id])

    async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.callback_query.edit_message_text(f'Accepted')
        user_replies[update.effective_chat.id] = int(update.callback_query.data.split('#')[1])
        await anext(job_appliers[update.effective_chat.id])

    tg_bot_app = ApplicationBuilder().token(_telegram_bot_token).build()
    tg_bot_app.add_handler(CommandHandler("start", start_command))
    tg_bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    tg_bot_app.add_handler(CallbackQueryHandler(button_handler))
    tg_bot_app.run_polling()
    return tg_bot_app

class JobApplier(object):
    LOGIN_URL = 'https://www.linkedin.com/home'
    LOGIN_BUTTON_LOCATOR = (By.XPATH, '//*[@id="main-content"]/section[1]/div/div/form/button')
    EMAIL_INPUT_LOCATOR = (By.XPATH, '//*[@id="session_key"]')
    PASSWORD_INPUT_LOCATOR = (By.XPATH, '//*[@id="session_password"]')
    PROFILE_DATA_LOCATOR = (By.XPATH, '/html/body/div[4]')
    JOBS_LIST_LOCATOR = (By.XPATH, '//*[@id="main"]/div/section[1]/div/ul')
    APPLY_BUTTON_LOCATOR = (By.XPATH, '//*[@id="main"]/div/section[2]/div/div[2]/div[1]/div/div[1]/div/div[1]/div[1]/div[3]/div/div/div/button')
    JOB_ITEM_LOCATOR_TEMPLATE = '//*[@id="main"]/div/section[1]/div/ul/li[{}]'
    APPLICATION_FORM_INPUT_LOCATOR = (By.CSS_SELECTOR, '.jobs-easy-apply-form-section__grouping')
    NEXT_APPLICATION_PAGE_BUTTON_CONTAINER_LOCATOR = (By.XPATH, '//*[@id="artdeco-modal-outlet"]/div/div/div[2]/div/div[2]/form/footer/div[2]')
    DONT_FOLLOW_COMPANY_CHECKBOX_LOCATOR = (By.XPATH, '//*[@id="artdeco-modal-outlet"]/div/div/div[2]/div/div[2]/div/footer/div[1]/label')
    SUBMIT_APPLICATION_BUTTON_LOCATOR = (By.XPATH, '//*[@id="artdeco-modal-outlet"]/div/div/div[2]/div/div[2]/div/footer/div[3]/button[2]')
    DISMISS_APPLICATION_SUCCESS_MODAL_LOCATOR = (By.XPATH, '/html/body/div[3]/div/div/button')
    NEXT_JOBS_PAGE_BUTTON_LOCATOR = (By.XPATH, "/html/body/div[5]/div[3]/div[4]/div/div/main/div/section[1]/div/div[6]/ul/li[contains(@class, 'selected')]/following-sibling/button")
    CHOOSE_RESUME_BUTTON_LOCATOR = (By.XPATH, '//*[@id="artdeco-modal-outlet"]/div/div/div[2]/div/div[2]/form/div/div/div/div[1]/div/div[2]/div/div[2]/button[1]')

    def __init__(self, tg_update, email, password, jobs_list_url):
        self.tg_update = tg_update
        self.email = email
        self.password = password
        self.jobs_list_url = jobs_list_url

    def is_radio(self, _form_input):
        return len(_form_input.find_elements(By.CSS_SELECTOR, 'legend')) > 0

    def is_text(self, _form_input):
        return len(_form_input.find_elements(By.CSS_SELECTOR, '.artdeco-text-input')) > 0

    def is_dropdown(self, _form_input):
        return len(_form_input.find_elements(By.CSS_SELECTOR, 'label')) > 0

    def radio_choices(self, _form_input):
        if not self.is_radio(_form_input):
            raise ValueError('not a radio question')
        return _form_input.find_elements(By.CSS_SELECTOR, 'div.fb-text-selectable__option')

    def dropdown_choices(self, _form_input):
        if not self.is_dropdown(_form_input):
            raise ValueError('not a dropdown question')
        return _form_input.find_elements(By.CSS_SELECTOR, 'option')[1:]

    def question_text(self, _form_input):
        if self.is_text(_form_input):
            return _form_input.find_element(By.CSS_SELECTOR, '.artdeco-text-input--label').text
        elif self.is_radio(_form_input):
            return _form_input.find_element(By.CSS_SELECTOR, 'legend').text
        elif self.is_dropdown(_form_input):
            return _form_input.find_element(By.CSS_SELECTOR, 'label').text
        raise ValueError("Can't recognize type of question")


    def is_filled(self, _form_input):
        if self.is_text(_form_input):
            return len(_form_input.find_element(By.CSS_SELECTOR, 'input').get_attribute("value")) > 0
        elif self.is_radio(_form_input):
            return len(_form_input.find_elements(By.CSS_SELECTOR, 'input[type=radio]:checked')) == 1
        elif self.is_dropdown(_form_input):
            fis = Select(_form_input.find_element(By.CSS_SELECTOR, 'select'))
            return fis.first_selected_option.get_attribute('value') != fis.options[0].get_attribute('value')
        raise ValueError("Can't recognize type of question")

    def get_choices_keyboard(self, _form_input):
        if self.is_radio(_form_input):
            print('radio choices: ')
            return [
                [InlineKeyboardButton(choice.text, callback_data='radio#%s' % index)]
                for index, choice in enumerate(self.radio_choices(_form_input))
            ]
        elif self.is_dropdown(_form_input):
            return [
                [InlineKeyboardButton(choice.text, callback_data='select#%s' % index)]
                for index, choice in enumerate(self.dropdown_choices(_form_input))
            ]
        raise ValueError("Not a choice question")

    async def apply_for_jobs(self):
        browser = webdriver.Chrome()
        browser.get(self.LOGIN_URL)
        login_button = WebDriverWait(browser, 20).until(EC.element_to_be_clickable(self.LOGIN_BUTTON_LOCATOR))
        browser.find_element(*self.EMAIL_INPUT_LOCATOR).send_keys(self.email)
        browser.find_element(*self.PASSWORD_INPUT_LOCATOR).send_keys(self.password)
        login_button.click()
        WebDriverWait(browser, 60).until(EC.presence_of_element_located(self.PROFILE_DATA_LOCATOR))
        browser.get(self.jobs_list_url)
        WebDriverWait(browser, 20).until(EC.presence_of_element_located(self.JOBS_LIST_LOCATOR))
        # apply for jobs
        for _ in range(10): # first ten pages
            for i in range(1, 26): # 25 jobs per page
                try:
                    WebDriverWait(browser, 5).until(EC.element_to_be_clickable((By.XPATH, self.JOB_ITEM_LOCATOR_TEMPLATE.format(i)))).click()
                    try:
                        WebDriverWait(browser, 5).until(EC.element_to_be_clickable(self.APPLY_BUTTON_LOCATOR)).click()
                    except:
                        continue
                    while True:
                        if len(choose_resume_buttons := browser.find_elements(*self.CHOOSE_RESUME_BUTTON_LOCATOR)) > 0:
                            choose_resume_buttons[0].click()
                        else:
                            form_inputs = browser.find_elements(*self.APPLICATION_FORM_INPUT_LOCATOR)
                            for form_input in form_inputs:
                                if self.is_filled(form_input):
                                    continue
                                if self.is_text(form_input):
                                    await self.tg_update.effective_chat.send_message(
                                        text=self.question_text(form_input)
                                    )
                                    yield
                                    text_input = form_input.find_element(By.CSS_SELECTOR, 'input')
                                    text_input.clear()
                                    text_input.send_keys(user_replies[self.tg_update.effective_chat.id])
                                elif self.is_radio(form_input):
                                    await self.tg_update.effective_chat.send_message(
                                        text=self.question_text(form_input),
                                        reply_markup=InlineKeyboardMarkup(self.get_choices_keyboard(form_input))
                                    )
                                    yield
                                    form_input.find_elements(By.CSS_SELECTOR, 'label')[user_replies[self.tg_update.effective_chat.id]].click()
                                elif self.is_dropdown(form_input):
                                    await self.tg_update.effective_chat.send_message(
                                        text=self.question_text(form_input),
                                        reply_markup=InlineKeyboardMarkup(self.get_choices_keyboard(form_input))
                                    )
                                    yield
                                    form_input.find_elements(By.CSS_SELECTOR, 'option')[user_replies[self.tg_update.effective_chat.id]].click()
                            if len(next_buttons_wrappers := browser.find_elements(*self.NEXT_APPLICATION_PAGE_BUTTON_CONTAINER_LOCATOR)) > 0:
                                next_buttons_wrappers[0].find_elements(By.CSS_SELECTOR, 'button')[-1].click()
                                browser.implicitly_wait(2) # seconds
                            elif len((submit_buttons := browser.find_elements(*self.SUBMIT_APPLICATION_BUTTON_LOCATOR))) > 0:
                                browser.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.PAGE_DOWN)
                                browser.find_element(*self.DONT_FOLLOW_COMPANY_CHECKBOX_LOCATOR).click()
                                submit_buttons[0].click()
                                WebDriverWait(browser, 7).until(EC.element_to_be_clickable(self.DISMISS_APPLICATION_SUCCESS_MODAL_LOCATOR)).click()
                                # if i < 25:
                                #     WebDriverWait(browser, 5).until(EC.element_to_be_clickable((By.XPATH, self.JOB_ITEM_LOCATOR_TEMPLATE.format(i + 1))))
                                break
                except Exception as e:
                    await self.tg_update.effective_chat.send_message(text=str(e))
            WebDriverWait(browser, 3).until(EC.element_to_be_clickable(self.NEXT_JOBS_PAGE_BUTTON_LOCATOR)).click()
            browser.implicitly_wait(1) # seconds
        browser.close()

#if __name__ == '__main__':
if True:
    run_tg_bot_and_loop("2002035919:AAEb_PIitwz0xxnOoy6J3Mh1uF_4Pv8ZTwA")
