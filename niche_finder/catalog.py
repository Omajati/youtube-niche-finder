"""Каталог вечнозелёных тем для автопоиска.

Каждая категория: русское название и по 2–3 стартовых запроса на каждом языке рынка.
Автопоиск расширяет их подсказками YouTube, так что запросы здесь намеренно широкие.
"""

CATEGORIES = [
    {"id": "mysteries", "name": "Загадки и необъяснимое", "seeds": {
        "en": ["unsolved mysteries", "unexplained events"],
        "es": ["misterios sin resolver", "casos inexplicables"],
        "de": ["ungelöste rätsel", "mysteriöse fälle"],
        "fr": ["mystères non résolus", "affaires inexpliquées"]}},
    {"id": "true_stories", "name": "Невероятные реальные истории", "seeds": {
        "en": ["incredible true stories", "survival stories"],
        "es": ["historias reales increíbles", "historias de supervivencia"],
        "de": ["unglaubliche wahre geschichten", "überlebensgeschichten"],
        "fr": ["histoires vraies incroyables", "histoires de survie"]}},
    {"id": "ancient", "name": "Древние цивилизации", "seeds": {
        "en": ["ancient civilizations", "lost ancient cities"],
        "es": ["civilizaciones antiguas", "ciudades perdidas"],
        "de": ["antike zivilisationen", "verlorene städte"],
        "fr": ["civilisations anciennes", "cités perdues"]}},
    {"id": "history_daily", "name": "Быт людей в прошлом", "seeds": {
        "en": ["daily life in medieval times", "what life was like in history"],
        "es": ["vida cotidiana en la edad media", "cómo se vivía en la antigüedad"],
        "de": ["alltag im mittelalter", "leben in der vergangenheit"],
        "fr": ["vie quotidienne au moyen âge", "comment vivait-on autrefois"]}},
    {"id": "forgotten_history", "name": "Забытые события истории", "seeds": {
        "en": ["forgotten history", "bizarre historical events"],
        "es": ["historia olvidada", "sucesos históricos extraños"],
        "de": ["vergessene geschichte", "kuriose geschichte"],
        "fr": ["histoire oubliée", "faits historiques étranges"]}},
    {"id": "mythology", "name": "Мифология и легенды", "seeds": {
        "en": ["mythology explained", "ancient legends"],
        "es": ["mitología explicada", "leyendas antiguas"],
        "de": ["mythologie erklärt", "alte legenden"],
        "fr": ["mythologie expliquée", "légendes anciennes"]}},
    {"id": "folklore", "name": "Фольклор и мифические существа", "seeds": {
        "en": ["folklore creatures", "folk tales from around the world"],
        "es": ["criaturas del folclore", "leyendas populares"],
        "de": ["sagengestalten", "volkssagen"],
        "fr": ["créatures du folklore", "contes et légendes"]}},
    {"id": "space", "name": "Космос", "seeds": {
        "en": ["space explained", "mysteries of the universe"],
        "es": ["el universo explicado", "misterios del universo"],
        "de": ["weltall erklärt", "rätsel des universums"],
        "fr": ["l'univers expliqué", "mystères de l'univers"]}},
    {"id": "earth", "name": "Планета и природные явления", "seeds": {
        "en": ["strange natural phenomena", "geology explained"],
        "es": ["fenómenos naturales extraños", "geología explicada"],
        "de": ["seltsame naturphänomene", "geologie erklärt"],
        "fr": ["phénomènes naturels étranges", "la géologie expliquée"]}},
    {"id": "animals", "name": "Необычные животные", "seeds": {
        "en": ["strange animals", "deep sea creatures"],
        "es": ["animales extraños", "criaturas de las profundidades"],
        "de": ["seltsame tiere", "tiefseekreaturen"],
        "fr": ["animaux étranges", "créatures des abysses"]}},
    {"id": "geography", "name": "Необычные места мира", "seeds": {
        "en": ["strangest places on earth", "abandoned places history"],
        "es": ["lugares más extraños del mundo", "lugares abandonados"],
        "de": ["seltsamste orte der welt", "verlassene orte"],
        "fr": ["lieux les plus étranges du monde", "lieux abandonnés"]}},
    {"id": "engineering", "name": "Как это устроено", "seeds": {
        "en": ["how it works explained", "engineering marvels"],
        "es": ["cómo funciona", "maravillas de la ingeniería"],
        "de": ["wie funktioniert", "meisterwerke der technik"],
        "fr": ["comment ça marche", "merveilles de l'ingénierie"]}},
    {"id": "inventions", "name": "История изобретений", "seeds": {
        "en": ["history of inventions", "accidental inventions"],
        "es": ["historia de los inventos", "inventos accidentales"],
        "de": ["geschichte der erfindungen", "zufällige erfindungen"],
        "fr": ["histoire des inventions", "inventions accidentelles"]}},
    {"id": "psychology", "name": "Психология и поведение", "seeds": {
        "en": ["psychology facts", "famous psychology experiments"],
        "es": ["datos de psicología", "experimentos psicológicos"],
        "de": ["psychologie fakten", "psychologische experimente"],
        "fr": ["faits de psychologie", "expériences psychologiques"]}},
    {"id": "body", "name": "Тело человека и медицина", "seeds": {
        "en": ["human body explained", "history of medicine"],
        "es": ["el cuerpo humano explicado", "historia de la medicina"],
        "de": ["menschlicher körper erklärt", "geschichte der medizin"],
        "fr": ["le corps humain expliqué", "histoire de la médecine"]}},
    {"id": "disasters", "name": "Катастрофы и их причины", "seeds": {
        "en": ["disasters explained", "engineering failures"],
        "es": ["desastres explicados", "fallos de ingeniería"],
        "de": ["katastrophen erklärt", "technische katastrophen"],
        "fr": ["catastrophes expliquées", "échecs d'ingénierie"]}},
    {"id": "heists", "name": "Аферы, ограбления, мошенники", "seeds": {
        "en": ["greatest heists in history", "famous con artists"],
        "es": ["los mayores robos de la historia", "estafadores famosos"],
        "de": ["größte raubüberfälle", "berühmte betrüger"],
        "fr": ["plus grands braquages", "escrocs célèbres"]}},
    {"id": "royalty", "name": "Монархи и династии", "seeds": {
        "en": ["royal history", "strange kings and queens"],
        "es": ["historia de la realeza", "reyes extraños"],
        "de": ["geschichte der königshäuser", "seltsame könige"],
        "fr": ["histoire des rois", "rois et reines étranges"]}},
    {"id": "exploration", "name": "Экспедиции и первооткрыватели", "seeds": {
        "en": ["famous expeditions", "explorers history"],
        "es": ["expediciones famosas", "grandes exploradores"],
        "de": ["berühmte expeditionen", "entdecker geschichte"],
        "fr": ["expéditions célèbres", "grands explorateurs"]}},
    {"id": "food_history", "name": "История еды и привычных вещей", "seeds": {
        "en": ["history of food", "origin of everyday things"],
        "es": ["historia de la comida", "origen de las cosas cotidianas"],
        "de": ["geschichte des essens", "herkunft alltäglicher dinge"],
        "fr": ["histoire de la nourriture", "origine des objets du quotidien"]}},
    {"id": "language", "name": "Языки и происхождение слов", "seeds": {
        "en": ["etymology explained", "history of languages"],
        "es": ["origen de las palabras", "historia de los idiomas"],
        "de": ["herkunft der wörter", "geschichte der sprachen"],
        "fr": ["origine des mots", "histoire des langues"]}},
    {"id": "art_history", "name": "Искусство и его тайны", "seeds": {
        "en": ["art history explained", "hidden meanings in paintings"],
        "es": ["historia del arte", "significados ocultos en pinturas"],
        "de": ["kunstgeschichte erklärt", "versteckte botschaften in gemälden"],
        "fr": ["histoire de l'art", "secrets des tableaux"]}},
    {"id": "philosophy", "name": "Философия простыми словами", "seeds": {
        "en": ["philosophy explained", "stoicism"],
        "es": ["filosofía explicada", "estoicismo"],
        "de": ["philosophie erklärt", "stoizismus"],
        "fr": ["philosophie expliquée", "stoïcisme"]}},
    {"id": "sleep", "name": "Истории для сна", "seeds": {
        "en": ["history for sleep", "boring history to fall asleep"],
        "es": ["historia para dormir", "documental para dormir"],
        "de": ["geschichte zum einschlafen", "doku zum einschlafen"],
        "fr": ["histoire pour s'endormir", "documentaire pour dormir"]}},
    {"id": "economics", "name": "Деньги и экономика в истории", "seeds": {
        "en": ["economic history explained", "how money works"],
        "es": ["historia económica", "cómo funciona el dinero"],
        "de": ["wirtschaftsgeschichte", "wie geld funktioniert"],
        "fr": ["histoire économique", "comment fonctionne l'argent"]}},
]

CATEGORY_BY_ID = {c["id"]: c for c in CATEGORIES}
