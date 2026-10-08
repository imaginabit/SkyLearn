from modeltranslation.translator import register, TranslationOptions
from .models import EssayQuestion, Quiz, Question, Choice, MCQuestion


@register(Quiz)
class QuizTranslationOptions(TranslationOptions):
    fields = (
        "title",
        "description",
    )
    empty_values = None


@register(Question)
class QuestionTranslationOptions(TranslationOptions):
    fields = (
        "content",
        "explanation",
    )
    empty_values = None


@register(Choice)
class ChoiceTranslationOptions(TranslationOptions):
    fields = ("choice_text",)
    empty_values = None


@register(MCQuestion)
class MCQuestionTranslationOptions(TranslationOptions):
    pass


# Sin campos propios: se registra solo para que `loaddata` acepte los
# `content_es` / `explanation_es` que hereda de Question. Sin esto, cargar un
# fixture con preguntas de desarrollo peta con
# «EssayQuestion() got an unexpected keyword argument 'content_es'».
@register(EssayQuestion)
class EssayQuestionTranslationOptions(TranslationOptions):
    pass
