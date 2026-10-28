"""Слова запросов и названий: что относится к теме, а что к подаче.

«ancient egypt facts» и «ancient egypt documentary» это одна тема; «explicado en 10 minutos» вообще не тема,
а формат: под него YouTube выдаёт ролики про что угодно.
"""
import re

# Слова, которые не меняют тему
FILLER = set("""
facts fact documentary documentaries full video videos story stories top best amazing interesting the a an of in
for and about to on what why how with from is are you your this that my all new
documental documentales datos curiosidades completo completa el la los las de del y en un una sobre con por para que
es lo mas más
doku dokumentation fakten ganze der die das den dem des und von im in über ein eine zum zur mit ist wie was warum
documentaire documentaires faits complet le la les de des du et en un une sur avec pour que qui est au aux
документальный документальные фильм факты простыми словами интересные интересно и в о об про на с по для что как
это все
""".split())

# Слова подачи: «за 10 минут», «объяснение», «все виды», «краткий пересказ». Запрос только из них это формат
FORMAT = set("""
explained explanation explain minutes minute seconds hours hour summary summaries recap types type kinds every
levels level ranked ranking tier list compilation part episode vs versus guide simply simple
explicado explicada explicados explicadas explicación explicacion minutos minuto segundos horas resumen resúmenes
resumenes tipos tipo niveles nivel todos todas cada parte capítulo capitulo guía guia fácil facil
erklärt erklärung minuten sekunden stunden zusammenfassung arten typen alle jeder jede stufen teil folge einfach
expliqué expliquée expliqués expliquées explication minutes secondes heures résumé resume types tous toutes chaque
niveaux partie épisode simplement
объяснение объясняю объяснил минут минуты минуту секунд часов час пересказ кратко краткий виды типы каждый уровни
часть серия выпуск
""".split())

_WORD = re.compile(r"\w+")


def words(text):
    return [w for w in _WORD.findall((text or "").lower()) if not w.isdigit()]


def stem(word):
    """Грубая основа: первые 5 букв. «terremotos» и «terremoto», «estrellas» и «estrella» совпадут."""
    return word[:5]


def topic_stems(text):
    """Основы слов темы: без пустышек, слов подачи, чисел и коротких слов."""
    return {stem(w) for w in words(text) if len(w) > 2 and w not in FILLER and w not in FORMAT}
