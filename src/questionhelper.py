from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit import prompt
from prompt_toolkit.contrib.completers import WordCompleter
from enum import Enum


class QuestionType(Enum):
    TEXT = 1
    CONFIRM = 2
    SECRET = 3


class Question:
    def __init__(self, type, name, message=None, validate=None, default=None, ignore=None):
        self.type = type
        self.name = name
        self.message = message
        self.validate = validate
        self.default = default
        self.ignore = ignore


class QuestionValidator(Validator):
    def __init__(self, answers, validate_func):
        self.answers = answers
        self.function = validate_func

    def validate(self, document):
        current = document.text
        if not self.function(self.answers, current):
            raise ValidationError(message='Invalid input.')


def string_to_boolean(input):
    if not isinstance(input, str):
        return None
    trimmed = input.lstrip()
    if not trimmed:
        return None

    letter = trimmed[:1].lower()
    if letter == 'y':
        return True
    elif letter == 'n':
        return False
    else:
        return None


class BooleanQuestionValidator(Validator):
    def __init__(self, answers, validate_func):
        self.answers = answers
        self.function = validate_func

    def validate(self, document):
        current = string_to_boolean(document.text)

        if current is None:
            raise ValidationError(message='Please answer Yes or No.')

        if callable(self.function) and not self.function(self.answers, current):
            raise ValidationError(message='Invalid input.')


def ask(question, answers, question_len):
    # Can be ignored?
    if callable(question.ignore) and question.ignore(answers):
        # Can be ignored
        return

    # Validator
    validator = None
    if question.type is QuestionType.CONFIRM:
        validator = BooleanQuestionValidator(answers, question.validate)
    elif callable(question.validate):
        validator = QuestionValidator(answers, question.validate)

    # Default value
    default_value = None
    if callable(question.default):
        default_value = question.default(answers)
    else:
        default_value = question.default

    if default_value is not None and question.type is QuestionType.CONFIRM:
        if default_value:
            default_value = 'yes'
        else:
            default_value = 'no'

    if default_value is None:
        default_value = ''

    # Completer
    completer = None
    if question.type is QuestionType.CONFIRM:
        completer = WordCompleter(['yes', 'no'])

    # Secret?
    is_secret = question.type is QuestionType.SECRET

    # Ask the question
    message = ('{m:' + str(question_len) + '} : ').format(m=question.message)
    answer = prompt(message, validator=validator, completer=completer,
                    default=default_value, is_password=is_secret)

    if question.type is QuestionType.CONFIRM:
        answer = string_to_boolean(answer)
    answers[question.name] = answer


def interview(questions):
    answers = {}
    qlen = 4
    for q in questions:
        if not isinstance(q, Question):
            raise TypeError('To be or not to be a question.. ' + repr(q))
        qlen = max(qlen, len(str(q.message)))
    for q in questions:
        ask(q, answers, qlen)
    return answers
