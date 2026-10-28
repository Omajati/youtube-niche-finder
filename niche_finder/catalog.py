"""Каталог вечнозелёных тем для автопоиска.

Каждая категория: русское название и по 2 стартовых запроса на каждом языке рынка (en, es, de, fr, ru).
К ним добавляются свои темы из «Настроек анализа» и темы, которые предложил Claude (all_categories()).
Автопоиск расширяет их подсказками YouTube, так что запросы здесь намеренно широкие.
"""
import hashlib
import json
import re

from . import config
from .words import FILLER, FORMAT

CATEGORIES = [
    {"id": "mysteries", "name": "Загадки и необъяснимое", "seeds": {
        "en": ["unsolved mysteries", "unexplained events"],
        "es": ["misterios sin resolver", "casos inexplicables"],
        "de": ["ungelöste rätsel", "mysteriöse fälle"],
        "fr": ["mystères non résolus", "affaires inexpliquées"],
        "ru": ["нераскрытые тайны", "необъяснимые случаи"]}},
    {"id": "true_stories", "name": "Невероятные реальные истории", "seeds": {
        "en": ["incredible true stories", "survival stories"],
        "es": ["historias reales increíbles", "historias de supervivencia"],
        "de": ["unglaubliche wahre geschichten", "überlebensgeschichten"],
        "fr": ["histoires vraies incroyables", "histoires de survie"],
        "ru": ["невероятные реальные истории", "истории выживания"]}},
    {"id": "ancient", "name": "Древние цивилизации", "seeds": {
        "en": ["ancient civilizations", "lost ancient cities"],
        "es": ["civilizaciones antiguas", "ciudades perdidas"],
        "de": ["antike zivilisationen", "verlorene städte"],
        "fr": ["civilisations anciennes", "cités perdues"],
        "ru": ["древние цивилизации", "затерянные города"]}},
    {"id": "history_daily", "name": "Быт людей в прошлом", "seeds": {
        "en": ["daily life in medieval times", "what life was like in history"],
        "es": ["vida cotidiana en la edad media", "cómo se vivía en la antigüedad"],
        "de": ["alltag im mittelalter", "leben in der vergangenheit"],
        "fr": ["vie quotidienne au moyen âge", "comment vivait-on autrefois"],
        "ru": ["жизнь в средневековье", "как жили люди в прошлом"]}},
    {"id": "forgotten_history", "name": "Забытые события истории", "seeds": {
        "en": ["forgotten history", "bizarre historical events"],
        "es": ["historia olvidada", "sucesos históricos extraños"],
        "de": ["vergessene geschichte", "kuriose geschichte"],
        "fr": ["histoire oubliée", "faits historiques étranges"],
        "ru": ["забытая история", "странные исторические события"]}},
    {"id": "mythology", "name": "Мифология и легенды", "seeds": {
        "en": ["mythology explained", "ancient legends"],
        "es": ["mitología explicada", "leyendas antiguas"],
        "de": ["mythologie erklärt", "alte legenden"],
        "fr": ["mythologie expliquée", "légendes anciennes"],
        "ru": ["мифология", "древние легенды"]}},
    {"id": "folklore", "name": "Фольклор и мифические существа", "seeds": {
        "en": ["folklore creatures", "folk tales from around the world"],
        "es": ["criaturas del folclore", "leyendas populares"],
        "de": ["sagengestalten", "volkssagen"],
        "fr": ["créatures du folklore", "contes et légendes"],
        "ru": ["славянская мифология", "мифические существа"]}},
    {"id": "space", "name": "Космос", "seeds": {
        "en": ["space explained", "mysteries of the universe"],
        "es": ["el universo explicado", "misterios del universo"],
        "de": ["weltall erklärt", "rätsel des universums"],
        "fr": ["l'univers expliqué", "mystères de l'univers"],
        "ru": ["космос", "тайны вселенной"]}},
    {"id": "earth", "name": "Планета и природные явления", "seeds": {
        "en": ["strange natural phenomena", "geology explained"],
        "es": ["fenómenos naturales extraños", "geología explicada"],
        "de": ["seltsame naturphänomene", "geologie erklärt"],
        "fr": ["phénomènes naturels étranges", "la géologie expliquée"],
        "ru": ["необычные явления природы", "загадки планеты земля"]}},
    {"id": "animals", "name": "Необычные животные", "seeds": {
        "en": ["strange animals", "deep sea creatures"],
        "es": ["animales extraños", "criaturas de las profundidades"],
        "de": ["seltsame tiere", "tiefseekreaturen"],
        "fr": ["animaux étranges", "créatures des abysses"],
        "ru": ["необычные животные", "обитатели глубин"]}},
    {"id": "geography", "name": "Необычные места мира", "seeds": {
        "en": ["strangest places on earth", "abandoned places history"],
        "es": ["lugares más extraños del mundo", "lugares abandonados"],
        "de": ["seltsamste orte der welt", "verlassene orte"],
        "fr": ["lieux les plus étranges du monde", "lieux abandonnés"],
        "ru": ["самые странные места на земле", "заброшенные места история"]}},
    {"id": "engineering", "name": "Как это устроено", "seeds": {
        "en": ["how it works explained", "engineering marvels"],
        "es": ["cómo funciona", "maravillas de la ingeniería"],
        "de": ["wie funktioniert", "meisterwerke der technik"],
        "fr": ["comment ça marche", "merveilles de l'ingénierie"],
        "ru": ["как это устроено", "чудеса инженерии"]}},
    {"id": "inventions", "name": "История изобретений", "seeds": {
        "en": ["history of inventions", "accidental inventions"],
        "es": ["historia de los inventos", "inventos accidentales"],
        "de": ["geschichte der erfindungen", "zufällige erfindungen"],
        "fr": ["histoire des inventions", "inventions accidentelles"],
        "ru": ["история изобретений", "изобретения случайно"]}},
    {"id": "psychology", "name": "Психология и поведение", "seeds": {
        "en": ["psychology facts", "famous psychology experiments"],
        "es": ["datos de psicología", "experimentos psicológicos"],
        "de": ["psychologie fakten", "psychologische experimente"],
        "fr": ["faits de psychologie", "expériences psychologiques"],
        "ru": ["психология человека", "психологические эксперименты"]}},
    {"id": "body", "name": "Тело человека и медицина", "seeds": {
        "en": ["human body explained", "history of medicine"],
        "es": ["el cuerpo humano explicado", "historia de la medicina"],
        "de": ["menschlicher körper erklärt", "geschichte der medizin"],
        "fr": ["le corps humain expliqué", "histoire de la médecine"],
        "ru": ["тело человека", "история медицины"]}},
    {"id": "disasters", "name": "Катастрофы и их причины", "seeds": {
        "en": ["disasters explained", "engineering failures"],
        "es": ["desastres explicados", "fallos de ingeniería"],
        "de": ["katastrophen erklärt", "technische katastrophen"],
        "fr": ["catastrophes expliquées", "échecs d'ingénierie"],
        "ru": ["катастрофы", "техногенные катастрофы"]}},
    {"id": "heists", "name": "Аферы, ограбления, мошенники", "seeds": {
        "en": ["greatest heists in history", "famous con artists"],
        "es": ["los mayores robos de la historia", "estafadores famosos"],
        "de": ["größte raubüberfälle", "berühmte betrüger"],
        "fr": ["plus grands braquages", "escrocs célèbres"],
        "ru": ["величайшие ограбления", "известные аферисты"]}},
    {"id": "royalty", "name": "Монархи и династии", "seeds": {
        "en": ["royal history", "strange kings and queens"],
        "es": ["historia de la realeza", "reyes extraños"],
        "de": ["geschichte der königshäuser", "seltsame könige"],
        "fr": ["histoire des rois", "rois et reines étranges"],
        "ru": ["история царей", "странные короли и королевы"]}},
    {"id": "exploration", "name": "Экспедиции и первооткрыватели", "seeds": {
        "en": ["famous expeditions", "explorers history"],
        "es": ["expediciones famosas", "grandes exploradores"],
        "de": ["berühmte expeditionen", "entdecker geschichte"],
        "fr": ["expéditions célèbres", "grands explorateurs"],
        "ru": ["великие экспедиции", "первооткрыватели"]}},
    {"id": "food_history", "name": "История еды и привычных вещей", "seeds": {
        "en": ["history of food", "origin of everyday things"],
        "es": ["historia de la comida", "origen de las cosas cotidianas"],
        "de": ["geschichte des essens", "herkunft alltäglicher dinge"],
        "fr": ["histoire de la nourriture", "origine des objets du quotidien"],
        "ru": ["история еды", "происхождение вещей"]}},
    {"id": "language", "name": "Языки и происхождение слов", "seeds": {
        "en": ["etymology explained", "history of languages"],
        "es": ["origen de las palabras", "historia de los idiomas"],
        "de": ["herkunft der wörter", "geschichte der sprachen"],
        "fr": ["origine des mots", "histoire des langues"],
        "ru": ["происхождение слов", "история языков"]}},
    {"id": "art_history", "name": "Искусство и его тайны", "seeds": {
        "en": ["art history explained", "hidden meanings in paintings"],
        "es": ["historia del arte", "significados ocultos en pinturas"],
        "de": ["kunstgeschichte erklärt", "versteckte botschaften in gemälden"],
        "fr": ["histoire de l'art", "secrets des tableaux"],
        "ru": ["история искусства", "тайны картин"]}},
    {"id": "philosophy", "name": "Философия простыми словами", "seeds": {
        "en": ["philosophy explained", "stoicism"],
        "es": ["filosofía explicada", "estoicismo"],
        "de": ["philosophie erklärt", "stoizismus"],
        "fr": ["philosophie expliquée", "stoïcisme"],
        "ru": ["философия простыми словами", "стоицизм"]}},
    {"id": "sleep", "name": "Истории для сна", "seeds": {
        "en": ["history for sleep", "boring history to fall asleep"],
        "es": ["historia para dormir", "documental para dormir"],
        "de": ["geschichte zum einschlafen", "doku zum einschlafen"],
        "fr": ["histoire pour s'endormir", "documentaire pour dormir"],
        "ru": ["история для сна", "документальный фильм для сна"]}},
    {"id": "economics", "name": "Деньги и экономика в истории", "seeds": {
        "en": ["economic history explained", "how money works"],
        "es": ["historia económica", "cómo funciona el dinero"],
        "de": ["wirtschaftsgeschichte", "wie geld funktioniert"],
        "fr": ["histoire économique", "comment fonctionne l'argent"],
        "ru": ["экономическая история", "как работают деньги"]}},
]


def _cat(cid, name, en, es, de, fr, ru):
    return {"id": cid, "name": name, "seeds": {"en": en, "es": es, "de": de, "fr": fr, "ru": ru}}


# Расширение каталога: ещё ~60 направлений, чтобы автопоиск не ходил по кругу в одних и тех же темах
CATEGORIES += [
    _cat("architecture", "Архитектура и великие постройки", ["architecture history", "megastructures"],
         ["historia de la arquitectura", "megaestructuras"], ["architekturgeschichte", "megabauwerke"],
         ["histoire de l'architecture", "mégastructures"], ["история архитектуры", "мегасооружения"]),
    _cat("ocean", "Океан и глубины", ["deep sea creatures", "ocean mysteries"],
         ["criaturas de las profundidades", "misterios del océano"], ["tiefsee lebewesen", "rätsel des ozeans"],
         ["créatures des abysses", "mystères de l'océan"], ["глубоководные существа", "тайны океана"]),
    _cat("jobs", "Необычные и опасные профессии", ["unusual jobs", "dangerous jobs in history"],
         ["trabajos extraños", "oficios peligrosos de la historia"], ["ungewöhnliche berufe", "gefährliche berufe früher"],
         ["métiers insolites", "métiers dangereux d'autrefois"], ["необычные профессии", "опасные профессии прошлого"]),
    _cat("traditions", "Происхождение традиций и обычаев", ["origin of traditions", "why do we celebrate"],
         ["origen de las tradiciones", "por qué celebramos"], ["ursprung von traditionen", "woher kommen bräuche"],
         ["origine des traditions", "d'où viennent nos coutumes"], ["происхождение традиций", "откуда взялись обычаи"]),
    _cat("espionage", "Шпионаж и спецслужбы", ["spy stories", "cold war espionage"],
         ["historias de espías", "espionaje guerra fría"], ["spionagegeschichten", "spionage im kalten krieg"],
         ["histoires d'espionnage", "espionnage guerre froide"], ["истории шпионов", "шпионаж холодной войны"]),
    _cat("prisons", "Тюрьмы и побеги", ["prison escapes", "most notorious prisons"],
         ["fugas de prisión", "cárceles más famosas"], ["gefängnisausbrüche", "berüchtigte gefängnisse"],
         ["évasions de prison", "prisons les plus célèbres"], ["побеги из тюрьмы", "самые известные тюрьмы"]),
    _cat("historic_crime", "Громкие преступления прошлого", ["historical crimes", "famous cold cases"],
         ["crímenes históricos", "casos sin resolver famosos"], ["historische kriminalfälle", "berühmte cold cases"],
         ["crimes historiques", "affaires criminelles célèbres"], ["исторические преступления", "громкие уголовные дела прошлого"]),
    _cat("military", "Военная история и сражения", ["military history explained", "famous battles"],
         ["historia militar", "batallas famosas"], ["militärgeschichte", "berühmte schlachten"],
         ["histoire militaire", "batailles célèbres"], ["военная история", "великие сражения"]),
    _cat("aviation", "Авиация и авиакатастрофы", ["aviation history", "plane crash investigations"],
         ["historia de la aviación", "investigación de accidentes aéreos"], ["luftfahrtgeschichte", "flugzeugabstürze erklärt"],
         ["histoire de l'aviation", "enquêtes crash aérien"], ["история авиации", "расследования авиакатастроф"]),
    _cat("ships", "Корабли и кораблекрушения", ["shipwrecks", "famous ships history"],
         ["naufragios", "barcos históricos"], ["schiffswracks", "berühmte schiffe"],
         ["naufrages", "navires célèbres"], ["кораблекрушения", "знаменитые корабли"]),
    _cat("railways", "Железные дороги и транспорт", ["railway history", "abandoned railways"],
         ["historia del ferrocarril", "trenes abandonados"], ["eisenbahngeschichte", "verlassene bahnstrecken"],
         ["histoire du chemin de fer", "voies ferrées abandonnées"], ["история железных дорог", "заброшенные железные дороги"]),
    _cat("abandoned", "Заброшенные места и города-призраки", ["abandoned places", "ghost towns"],
         ["lugares abandonados", "pueblos fantasma"], ["verlassene orte", "geisterstädte"],
         ["lieux abandonnés", "villes fantômes"], ["заброшенные места", "города-призраки"]),
    _cat("countries", "Как устроены страны и границы", ["countries explained", "why borders are where they are"],
         ["países explicados", "por qué las fronteras son así"], ["länder erklärt", "warum grenzen so verlaufen"],
         ["pays expliqués", "pourquoi les frontières sont ainsi"], ["как устроены страны", "почему границы такие"]),
    _cat("cities", "История городов", ["history of cities", "how cities were built"],
         ["historia de las ciudades", "cómo se construyeron las ciudades"], ["geschichte der städte", "wie städte entstanden"],
         ["histoire des villes", "comment les villes ont été construites"], ["история городов", "как строились города"]),
    _cat("maps", "Карты и картография", ["history of maps", "map facts"],
         ["historia de los mapas", "curiosidades de mapas"], ["geschichte der landkarten", "karten fakten"],
         ["histoire des cartes", "cartes étonnantes"], ["история карт", "удивительные карты"]),
    _cat("dinosaurs", "Динозавры и доисторический мир", ["dinosaurs documentary", "prehistoric animals"],
         ["documental dinosaurios", "animales prehistóricos"], ["dinosaurier doku", "urzeittiere"],
         ["documentaire dinosaures", "animaux préhistoriques"], ["динозавры документальный", "доисторические животные"]),
    _cat("evolution", "Эволюция и происхождение человека", ["human evolution", "origin of life"],
         ["evolución humana", "origen de la vida"], ["evolution des menschen", "entstehung des lebens"],
         ["évolution humaine", "origine de la vie"], ["эволюция человека", "происхождение жизни"]),
    _cat("plants", "Растения и грибы", ["strange plants", "fungi documentary"],
         ["plantas extrañas", "documental hongos"], ["seltsame pflanzen", "pilze doku"],
         ["plantes étranges", "documentaire champignons"], ["необычные растения", "грибы документальный"]),
    _cat("insects", "Насекомые", ["insects documentary", "bizarre insects"],
         ["documental insectos", "insectos extraños"], ["insekten doku", "seltsame insekten"],
         ["documentaire insectes", "insectes étranges"], ["насекомые документальный", "удивительные насекомые"]),
    _cat("weather", "Стихии: вулканы, бури, климат", ["extreme weather explained", "volcano eruptions history"],
         ["clima extremo explicado", "erupciones volcánicas históricas"], ["extremwetter erklärt", "vulkanausbrüche geschichte"],
         ["météo extrême expliquée", "éruptions volcaniques historiques"], ["экстремальная погода", "извержения вулканов в истории"]),
    _cat("physics", "Физика простыми словами", ["physics explained", "quantum physics simply explained"],
         ["física explicada", "física cuántica fácil"], ["physik erklärt", "quantenphysik einfach erklärt"],
         ["physique expliquée", "physique quantique expliquée simplement"], ["физика простыми словами", "квантовая физика просто"]),
    _cat("chemistry", "Химия и элементы", ["chemistry explained", "periodic table elements"],
         ["química explicada", "elementos de la tabla periódica"], ["chemie erklärt", "elemente des periodensystems"],
         ["chimie expliquée", "éléments du tableau périodique"], ["химия простыми словами", "элементы таблицы менделеева"]),
    _cat("math", "Математика и загадки чисел", ["math explained", "famous math problems"],
         ["matemáticas explicadas", "problemas matemáticos famosos"], ["mathematik erklärt", "berühmte mathe probleme"],
         ["mathématiques expliquées", "problèmes mathématiques célèbres"], ["математика простыми словами", "знаменитые математические задачи"]),
    _cat("scientists", "Великие учёные и открытия", ["great scientists biography", "scientific discoveries history"],
         ["biografía de científicos", "grandes descubrimientos científicos"], ["große wissenschaftler", "wissenschaftliche entdeckungen"],
         ["grands scientifiques", "grandes découvertes scientifiques"], ["великие учёные", "научные открытия истории"]),
    _cat("medicine_history", "История медицины", ["history of medicine", "medieval medicine"],
         ["historia de la medicina", "medicina medieval"], ["geschichte der medizin", "medizin im mittelalter"],
         ["histoire de la médecine", "médecine au moyen âge"], ["история медицины", "средневековая медицина"]),
    _cat("epidemics", "Эпидемии и болезни в истории", ["pandemics in history", "deadliest diseases"],
         ["pandemias de la historia", "enfermedades más mortales"], ["pandemien der geschichte", "tödlichste krankheiten"],
         ["pandémies de l'histoire", "maladies les plus mortelles"], ["эпидемии в истории", "самые опасные болезни"]),
    _cat("brain", "Мозг и сознание", ["how the brain works", "consciousness explained"],
         ["cómo funciona el cerebro", "la conciencia explicada"], ["wie das gehirn funktioniert", "bewusstsein erklärt"],
         ["comment fonctionne le cerveau", "la conscience expliquée"], ["как работает мозг", "что такое сознание"]),
    _cat("nutrition", "Питание и что происходит с телом", ["nutrition science", "what happens to your body when"],
         ["ciencia de la nutrición", "qué le pasa a tu cuerpo si"], ["ernährungswissenschaft", "was passiert mit deinem körper wenn"],
         ["science de la nutrition", "que se passe-t-il dans ton corps si"], ["наука о питании", "что будет с телом если"]),
    _cat("religions", "История религий", ["history of religions", "ancient religions"],
         ["historia de las religiones", "religiones antiguas"], ["religionsgeschichte", "alte religionen"],
         ["histoire des religions", "religions anciennes"], ["история религий", "древние религии"]),
    _cat("secret_societies", "Тайные общества и ордена", ["secret societies history", "knights templar"],
         ["sociedades secretas", "templarios"], ["geheimbünde", "tempelritter"],
         ["sociétés secrètes", "templiers"], ["тайные общества", "тамплиеры"]),
    _cat("pirates", "Пираты и разбойники", ["pirates history", "famous outlaws"],
         ["historia de los piratas", "forajidos famosos"], ["piraten geschichte", "berühmte gesetzlose"],
         ["histoire des pirates", "hors-la-loi célèbres"], ["история пиратов", "знаменитые разбойники"]),
    _cat("vikings", "Викинги и северные народы", ["vikings history", "norse history"],
         ["historia de los vikingos", "historia nórdica"], ["wikinger geschichte", "nordische geschichte"],
         ["histoire des vikings", "histoire nordique"], ["история викингов", "скандинавская история"]),
    _cat("rome_greece", "Древний Рим и Греция", ["ancient rome", "ancient greece"],
         ["antigua roma", "antigua grecia"], ["antikes rom", "antikes griechenland"],
         ["rome antique", "grèce antique"], ["древний рим", "древняя греция"]),
    _cat("egypt", "Древний Египет", ["ancient egypt", "pharaohs"],
         ["antiguo egipto", "faraones"], ["altes ägypten", "pharaonen"],
         ["egypte ancienne", "pharaons"], ["древний египет", "фараоны"]),
    _cat("asia_history", "История Китая и Японии", ["chinese history", "samurai history"],
         ["historia de china", "historia de los samuráis"], ["chinesische geschichte", "samurai geschichte"],
         ["histoire de la chine", "histoire des samouraïs"], ["история китая", "история самураев"]),
    _cat("americas_history", "Ацтеки, майя и индейцы", ["aztec history", "native american history"],
         ["historia azteca", "pueblos originarios de américa"], ["azteken geschichte", "geschichte der ureinwohner amerikas"],
         ["histoire des aztèques", "histoire des amérindiens"], ["история ацтеков", "индейцы америки"]),
    _cat("world_wars", "Мировые войны", ["world war 2 documentary", "world war 1 history"],
         ["segunda guerra mundial documental", "primera guerra mundial"], ["zweiter weltkrieg doku", "erster weltkrieg"],
         ["seconde guerre mondiale documentaire", "première guerre mondiale"], ["вторая мировая война", "первая мировая война"]),
    _cat("cold_war", "Холодная война и СССР", ["cold war history", "soviet union history"],
         ["guerra fría historia", "historia de la unión soviética"], ["kalter krieg geschichte", "geschichte der sowjetunion"],
         ["guerre froide histoire", "histoire de l'union soviétique"], ["холодная война", "история ссср"]),
    _cat("empires", "Империи: взлёт и падение", ["rise and fall of empires", "greatest empires in history"],
         ["auge y caída de imperios", "los imperios más grandes"], ["aufstieg und fall von imperien", "größte imperien der geschichte"],
         ["grandeur et chute des empires", "plus grands empires de l'histoire"], ["взлёт и падение империй", "величайшие империи"]),
    _cat("biographies", "Биографии великих людей", ["biography documentary", "life of famous people in history"],
         ["biografía documental", "vida de personajes históricos"], ["biografie doku", "leben berühmter persönlichkeiten"],
         ["biographie documentaire", "vie de personnages historiques"], ["биография документальный", "жизнь великих людей"]),
    _cat("business_stories", "Истории компаний и брендов", ["company history", "rise and fall of brands"],
         ["historia de empresas", "auge y caída de marcas"], ["firmengeschichte", "aufstieg und fall von marken"],
         ["histoire des entreprises", "ascension et chute des marques"], ["история компаний", "взлёт и падение брендов"]),
    _cat("cars", "Автомобили и их история", ["car history", "classic cars documentary"],
         ["historia del automóvil", "coches clásicos"], ["autogeschichte", "oldtimer doku"],
         ["histoire de l'automobile", "voitures anciennes"], ["история автомобилей", "классические автомобили"]),
    _cat("tech_history", "История компьютеров и интернета", ["computer history", "history of the internet"],
         ["historia de la computación", "historia de internet"], ["computergeschichte", "geschichte des internets"],
         ["histoire de l'informatique", "histoire d'internet"], ["история компьютеров", "история интернета"]),
    _cat("games_history", "История видеоигр", ["video game history", "retro gaming documentary"],
         ["historia de los videojuegos", "videojuegos retro"], ["videospiel geschichte", "retro gaming doku"],
         ["histoire du jeu vidéo", "rétro gaming"], ["история видеоигр", "ретро игры"]),
    _cat("music_history", "История музыки и песен", ["music history", "stories behind famous songs"],
         ["historia de la música", "historias detrás de canciones"], ["musikgeschichte", "geschichten hinter berühmten songs"],
         ["histoire de la musique", "histoires derrière les chansons"], ["история музыки", "истории известных песен"]),
    _cat("cinema_history", "История кино", ["film history", "behind the scenes of classic movies"],
         ["historia del cine", "detrás de cámaras películas clásicas"], ["filmgeschichte", "hinter den kulissen klassischer filme"],
         ["histoire du cinéma", "coulisses des films cultes"], ["история кино", "как снимали культовые фильмы"]),
    _cat("literature", "Литература и великие книги", ["literature explained", "classic books summary"],
         ["literatura explicada", "resumen de libros clásicos"], ["literatur erklärt", "klassiker zusammenfassung"],
         ["littérature expliquée", "résumé de classiques"], ["литература простыми словами", "краткий пересказ классики"]),
    _cat("sports_history", "История спорта", ["sports history", "olympic history"],
         ["historia del deporte", "historia de los juegos olímpicos"], ["sportgeschichte", "geschichte der olympischen spiele"],
         ["histoire du sport", "histoire des jeux olympiques"], ["история спорта", "история олимпийских игр"]),
    _cat("survival_skills", "Выживание и примитивные технологии", ["survival skills", "primitive technology"],
         ["técnicas de supervivencia", "tecnología primitiva"], ["überlebenstechniken", "primitive technik"],
         ["techniques de survie", "technologie primitive"], ["навыки выживания", "примитивные технологии"]),
    _cat("crafts", "Ремёсла и как делают вещи", ["how it's made", "traditional crafts"],
         ["cómo se hace", "oficios tradicionales"], ["wie es gemacht wird", "traditionelles handwerk"],
         ["comment c'est fait", "artisanat traditionnel"], ["как это сделано", "традиционные ремёсла"]),
    _cat("cultures", "Народы и культуры мира", ["cultures of the world", "isolated tribes"],
         ["culturas del mundo", "tribus aisladas"], ["kulturen der welt", "isolierte völker"],
         ["cultures du monde", "peuples isolés"], ["народы мира", "изолированные племена"]),
    _cat("paranormal", "Паранормальное и призраки", ["haunted places", "paranormal stories"],
         ["lugares embrujados", "historias paranormales"], ["spukorte", "paranormale geschichten"],
         ["lieux hantés", "histoires paranormales"], ["места с привидениями", "паранормальные истории"]),
    _cat("aliens", "НЛО и внеземная жизнь", ["alien life explained", "ufo cases"],
         ["vida extraterrestre", "casos ovni"], ["außerirdisches leben", "ufo fälle"],
         ["vie extraterrestre", "affaires ovni"], ["внеземная жизнь", "случаи нло"]),
    _cat("what_if", "Что если: гипотезы и будущее", ["what if scenarios", "future of humanity"],
         ["qué pasaría si", "el futuro de la humanidad"], ["was wäre wenn", "zukunft der menschheit"],
         ["et si", "futur de l'humanité"], ["что если", "будущее человечества"]),
    _cat("law", "Странные законы и громкие суды", ["strange laws", "famous trials in history"],
         ["leyes extrañas", "juicios famosos de la historia"], ["seltsame gesetze", "berühmte prozesse"],
         ["lois étranges", "procès célèbres"], ["странные законы", "знаменитые судебные процессы"]),
    _cat("personal_finance", "Личные финансы и инвестиции", ["personal finance explained", "investing for beginners"],
         ["finanzas personales", "invertir para principiantes"], ["finanzen einfach erklärt", "investieren für anfänger"],
         ["finances personnelles", "investir pour débutants"], ["личные финансы", "инвестиции для начинающих"]),
    _cat("habits", "Привычки и саморазвитие", ["habits that change your life", "productivity explained"],
         ["hábitos que cambian tu vida", "productividad"], ["gewohnheiten die dein leben verändern", "produktivität"],
         ["habitudes qui changent la vie", "productivité"], ["привычки которые меняют жизнь", "продуктивность"]),
    _cat("treasures", "Золото, сокровища, драгоценности", ["history of gold", "lost treasures"],
         ["historia del oro", "tesoros perdidos"], ["geschichte des goldes", "verschollene schätze"],
         ["histoire de l'or", "trésors perdus"], ["история золота", "потерянные сокровища"]),
    _cat("remote_places", "Острова и самые отдалённые места", ["remote islands", "most isolated places on earth"],
         ["islas remotas", "lugares más aislados del mundo"], ["abgelegene inseln", "abgelegenste orte der welt"],
         ["îles isolées", "endroits les plus isolés du monde"], ["отдалённые острова", "самые изолированные места"]),
    _cat("mountains", "Горы и альпинизм", ["mountaineering disasters", "everest stories"],
         ["tragedias en la montaña", "historias del everest"], ["bergsteiger unglücke", "everest geschichten"],
         ["drames en montagne", "histoires de l'everest"], ["трагедии в горах", "истории эвереста"]),
]

CATEGORY_BY_ID = {c["id"]: c for c in CATEGORIES}

# Насколько RPM категории выше или ниже среднего для познавательных роликов (грубая оценка рекламного спроса)
RPM_FACTOR = {"economics": 1.6, "body": 1.3, "psychology": 1.2, "engineering": 1.2, "inventions": 1.1,
              "space": 1.1, "mythology": 0.9, "folklore": 0.9, "sleep": 0.7,
              "personal_finance": 2.0, "business_stories": 1.4, "habits": 1.3, "nutrition": 1.2, "tech_history": 1.2,
              "cars": 1.2, "physics": 1.1, "brain": 1.2, "aviation": 1.1, "paranormal": 0.8, "aliens": 0.8}


# --- свои темы и темы от Claude ---

def load_claude_topics():
    """Направления, которые предложил Claude (кнопка «Новые темы через Claude»)."""
    try:
        return json.loads(config.TOPICS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_claude_topics(topics):
    config.TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.TOPICS_FILE.write_text(json.dumps(topics, ensure_ascii=False, indent=1), encoding="utf-8")


def custom_categories():
    """Свои темы из настроек: одна строка = одна категория. Запросы на другие языки переводятся при поиске."""
    return [{"id": "custom_" + hashlib.md5(t.lower().encode()).hexdigest()[:8], "name": t, "custom": True,
             "seeds": {"src": [t]}} for t in config.CUSTOM_TOPICS]


def all_categories():
    return CATEGORIES + custom_categories() + load_claude_topics()


def category_names():
    return {c["id"]: c["name"] for c in all_categories()}


# --- почти одинаковые запросы ---

def similar_key(query, lang=""):
    """Ключ для отсева почти одинаковых запросов: без слов-пустышек, чисел и окончаний множественного числа."""
    words = []
    for w in re.findall(r"\w+", query.lower()):
        if w in FILLER or w in FORMAT or w.isdigit():
            continue
        if len(w) > 4 and w.endswith("s"):
            w = w[:-1]
        words.append(w)
    return lang + "|" + " ".join(sorted(set(words)))
